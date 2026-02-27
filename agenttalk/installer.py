"""
AgentTalk installer module.

Provides:
  - download_model(): Download Kokoro ONNX model files to the platform config dir
  - create_shortcut(): Create AgentTalk.lnk on the Windows desktop (Windows-only)
  - register_autostart(): Register the service for auto-start on the current platform

Platforms:
  Windows  — Task Scheduler XML task (or startup folder .lnk fallback)
  macOS    — ~/Library/LaunchAgents/ai.agenttalk.plist (launchd)
  Linux    — ~/.config/systemd/user/agenttalk.service (systemd --user)

Requirements: INST-02, INST-04, INST-05, INST-06
Called by: agenttalk.cli._cmd_setup()
"""
import os
import platform
import subprocess
import sys
import xml.sax.saxutils
from pathlib import Path

import requests
from tqdm import tqdm

from agenttalk.config_loader import _config_dir

# ---------------------------------------------------------------------------
# Paths  (cross-platform via _config_dir())
# ---------------------------------------------------------------------------

CONFIG_DIR = _config_dir()
MODELS_DIR = CONFIG_DIR / "models"

# Kokoro v1.0 model files — hosted on GitHub releases under the stable tag
# model-files-v1.0 tag is the stable v1 release (see Phase 6 research pitfall 6)
MODEL_FILES: dict[str, str] = {
    "kokoro-v1.0.onnx": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.0/kokoro-v1.0.onnx"
    ),
    "voices-v1.0.bin": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.0/voices-v1.0.bin"
    ),
}


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------

def download_model() -> None:
    """
    Download Kokoro ONNX model files to the platform-appropriate models directory.

    Skips files that already exist (idempotent).
    Uses streaming HTTP with tqdm progress bar.
    Raises requests.HTTPError on non-200 responses (e.g., HTTP 404 if URL changes).

    INST-02: Downloads kokoro-v1.0.onnx (~310MB) and voices-v1.0.bin to config models dir.
    INST-06: User-level paths require no admin rights on all platforms.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in MODEL_FILES.items():
        dest = MODELS_DIR / filename
        if dest.exists():
            print(f"  {filename}: already present, skipping.")
            continue

        print(f"\nDownloading {filename}...")
        try:
            response = requests.get(url, stream=True, allow_redirects=True, timeout=30)
            response.raise_for_status()
        except requests.HTTPError as exc:
            print(
                f"\nERROR: Failed to download {filename}: {exc}\n"
                "If you see HTTP 404, the model URL may have changed.\n"
                "Check https://github.com/thewh1teagle/kokoro-onnx/releases for the latest URL."
            )
            raise
        except requests.ConnectionError as exc:
            print(
                f"\nERROR: Cannot connect to download {filename}: {exc}\n"
                "Check your internet connection and firewall settings."
            )
            raise
        except requests.Timeout as exc:
            print(
                f"\nERROR: Connection timed out while downloading {filename}: {exc}\n"
                "Check your internet connection and try again."
            )
            raise

        # NOTE: timeout=30 only covers connection + headers; the streaming body
        # has no per-chunk timeout. A stalled mid-stream transfer will hang
        # indefinitely. Use a requests-toolbelt or urllib3 workaround if needed.
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        total = int(response.headers.get("content-length", 0))
        try:
            with (
                open(tmp, "wb") as f,
                tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=filename,
                ) as bar,
            ):
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bar.update(len(chunk))
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        tmp.replace(dest)
        print(f"  Saved to {dest}")


# ---------------------------------------------------------------------------
# Icon file generation
# ---------------------------------------------------------------------------

ICON_PATH = CONFIG_DIR / "icon.ico"


def generate_icon_file() -> Path:
    """
    Generate AgentTalk.ico to the config directory (Windows-only path for the .ico format).

    Creates a multi-resolution .ico from the idle tray image at sizes
    [16, 32, 48, 64, 128, 256] so Windows displays a crisp icon at every DPI.
    Returns the path to the generated file.
    """
    from agenttalk.tray import create_image_idle  # deferred — avoids circular import at module load

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    images = [create_image_idle(size=s) for s in sizes]
    images[0].save(
        str(ICON_PATH),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    return ICON_PATH


# ---------------------------------------------------------------------------
# Auto-start registration (cross-platform)
# ---------------------------------------------------------------------------

# launchd plist template for macOS
_LAUNCHD_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.agenttalk</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>agenttalk.service</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_dir}/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/launchd_stderr.log</string>
</dict>
</plist>
"""

# systemd --user unit template for Linux
_SYSTEMD_UNIT = """\
[Unit]
Description=AgentTalk TTS Service
After=network.target

[Service]
Type=simple
ExecStart="{python}" -m agenttalk.service
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def register_autostart(no_autostart: bool = False) -> None:
    """
    Register AgentTalk to start automatically when the user logs in.

    Platform dispatch:
      Windows — schtasks.exe XML task (no admin required, Task Scheduler)
      macOS   — ~/Library/LaunchAgents/ai.agenttalk.plist (launchd)
      Linux   — ~/.config/systemd/user/agenttalk.service (systemd --user)

    Args:
        no_autostart: When True, skip auto-start registration entirely.
                      Equivalent to passing --no-autostart on the CLI.
    """
    if no_autostart:
        print("  Auto-start registration skipped (--no-autostart).")
        return

    system = platform.system()
    if system == "Windows":
        _register_autostart_windows()
    elif system == "Darwin":
        _register_autostart_macos()
    else:
        _register_autostart_linux()


def _register_autostart_windows() -> None:
    """Register via Windows Task Scheduler (no admin rights required)."""
    python_exe = sys.executable
    task_name = "AgentTalk"

    # XML-escape the executable path so characters like &, <, > in paths
    # (unusual but possible) do not corrupt the Task Scheduler XML document.
    python_exe_xml = xml.sax.saxutils.escape(python_exe)

    # Build a minimal Task Scheduler XML
    task_xml = f"""\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe_xml}</Command>
      <Arguments>-m agenttalk.service</Arguments>
    </Exec>
  </Actions>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
</Task>
"""
    xml_path = CONFIG_DIR / "agenttalk_task.xml"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    xml_path.write_text(task_xml, encoding="utf-16")

    try:
        subprocess.run(
            ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"  Windows Task Scheduler task '{task_name}' created.")
    except subprocess.CalledProcessError as exc:
        print(
            f"WARNING: schtasks failed: {exc.stderr.strip()}\n"
            "You can start AgentTalk manually from the desktop shortcut or by running:\n"
            f"  {python_exe} -m agenttalk.service"
        )
    except FileNotFoundError:
        print(
            "WARNING: schtasks.exe not found — skipping Task Scheduler registration.\n"
            f"Start manually: {python_exe} -m agenttalk.service"
        )


def _register_autostart_macos() -> None:
    """Register via launchd plist in ~/Library/LaunchAgents/."""
    python_exe = sys.executable
    log_dir = CONFIG_DIR

    log_dir.mkdir(parents=True, exist_ok=True)

    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    plist_path = agents_dir / "ai.agenttalk.plist"
    # XML-escape path values so special characters (&, <, >) in unusual
    # installation paths do not produce malformed plist XML.
    plist_content = _LAUNCHD_PLIST.format(
        python=xml.sax.saxutils.escape(python_exe),
        log_dir=xml.sax.saxutils.escape(str(log_dir)),
    )
    plist_path.write_text(plist_content, encoding="utf-8")
    print(f"  LaunchAgent plist written to {plist_path}")

    # Load the agent immediately (also runs at next login automatically)
    try:
        subprocess.run(
            ["launchctl", "load", str(plist_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        print("  AgentTalk registered with launchd and started.")
    except subprocess.CalledProcessError as exc:
        print(
            f"WARNING: launchctl load failed: {exc.stderr.strip()}\n"
            "The plist is installed and will auto-start at next login.\n"
            f"To start now: launchctl load {plist_path}"
        )
    except FileNotFoundError:
        print(
            "WARNING: launchctl not found — plist is installed but service not yet loaded.\n"
            f"To load manually: launchctl load {plist_path}"
        )


def _register_autostart_linux() -> None:
    """Register via systemd --user in ~/.config/systemd/user/."""
    python_exe = sys.executable

    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_user_dir.mkdir(parents=True, exist_ok=True)

    unit_path = systemd_user_dir / "agenttalk.service"
    unit_content = _SYSTEMD_UNIT.format(python=python_exe)
    unit_path.write_text(unit_content, encoding="utf-8")
    print(f"  systemd unit written to {unit_path}")

    # Enable and start the service
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "agenttalk"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("  AgentTalk registered with systemd --user and started.")
    except subprocess.CalledProcessError as exc:
        print(
            f"WARNING: systemctl command failed: {exc.stderr.strip()}\n"
            "The unit file is installed. To enable manually:\n"
            "  systemctl --user daemon-reload\n"
            "  systemctl --user enable --now agenttalk"
        )
    except FileNotFoundError:
        print(
            "WARNING: systemctl not found — unit file is installed but service not enabled.\n"
            "To enable manually:\n"
            "  systemctl --user daemon-reload\n"
            "  systemctl --user enable --now agenttalk"
        )


# ---------------------------------------------------------------------------
# Desktop shortcut (Windows-only)
# ---------------------------------------------------------------------------

def create_shortcut() -> None:
    """
    Create AgentTalk.lnk on the Windows desktop targeting pythonw.exe + service.py.

    Uses winshell.desktop() to resolve the true desktop path via Win32
    SHGetFolderPath — handles GPO-redirected desktops correctly.
    Falls back to python.exe if pythonw.exe is not found.
    Idempotent: overwrites existing shortcut on re-run.

    Windows-only: silently skips on macOS/Linux (no .lnk format).

    INST-04: Desktop shortcut creation.
    INST-05: Absolute path to venv's pythonw.exe embedded in the shortcut.
    INST-06: winshell creates .lnk files without admin rights.
    """
    if platform.system() != "Windows":
        print("  Desktop shortcut: skipped (Windows-only feature).")
        return

    try:
        import winshell  # type: ignore[import]
    except ImportError:
        print(
            "WARNING: winshell not available — skipping desktop shortcut creation.\n"
            "Install winshell with: pip install winshell pywin32"
        )
        return

    # Detect pythonw.exe alongside the current python.exe (venv-aware)
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if not pythonw.exists():
        # Fallback: no pythonw.exe in this environment (e.g., conda, some venvs)
        pythonw = python_exe
        print(f"  NOTE: pythonw.exe not found; shortcut will use {pythonw.name}")

    # service.py lives in the same directory as this installer.py (agenttalk/)
    service_py = Path(__file__).parent / "service.py"
    if not service_py.exists():
        print(f"WARNING: service.py not found at {service_py} — shortcut may not work.")

    desktop = Path(winshell.desktop())
    shortcut_path = desktop / "AgentTalk.lnk"

    icon_path = None
    try:
        icon_path = generate_icon_file()
    except Exception as exc:
        print(f"  NOTE: Could not generate icon file: {exc}")

    try:
        with winshell.shortcut(str(shortcut_path)) as link:
            link.path = str(pythonw.resolve())
            link.arguments = f'"{service_py.resolve()}"'
            link.working_directory = str(service_py.parent.resolve())
            link.description = "AgentTalk TTS Service"
            if icon_path and icon_path.exists():
                link.icon_location = (str(icon_path), 0)
    except Exception as exc:
        # pywin32 post-install script may not have run — give actionable guidance
        print(
            f"WARNING: Could not create desktop shortcut: {exc}\n"
            "If you see a COM/DLL error, run: python -m pywin32_postinstall -install"
        )
        return

    print(f"  Desktop shortcut created: {shortcut_path}")

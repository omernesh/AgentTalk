"""
AgentTalk installer module.

Provides:
  - download_model(): Download Kokoro ONNX model files to %APPDATA%\\AgentTalk\\models\\
  - create_shortcut(): Create AgentTalk.lnk on the Windows desktop

Requirements: INST-02, INST-04, INST-05, INST-06
Called by: agenttalk.cli._cmd_setup()
"""
import os
import sys
from pathlib import Path

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APPDATA = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
MODELS_DIR = APPDATA / "AgentTalk" / "models"

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
    Download Kokoro ONNX model files to %APPDATA%\\AgentTalk\\models\\.

    Skips files that already exist (idempotent).
    Uses streaming HTTP with tqdm progress bar.
    Raises requests.HTTPError on non-200 responses (e.g., HTTP 404 if URL changes).

    INST-02: Downloads kokoro-v1.0.onnx (~310MB) and voices-v1.0.bin to APPDATA models dir.
    INST-06: APPDATA paths require no admin rights on Windows 11.
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

        tmp.rename(dest)
        print(f"  Saved to {dest}")


# ---------------------------------------------------------------------------
# Desktop shortcut
# ---------------------------------------------------------------------------

def create_shortcut() -> None:
    """
    Create AgentTalk.lnk on the Windows desktop targeting pythonw.exe + service.py.

    Uses winshell.desktop() to resolve the true desktop path via Win32
    SHGetFolderPath — handles GPO-redirected desktops correctly.
    Falls back to python.exe if pythonw.exe is not found.
    Idempotent: overwrites existing shortcut on re-run.

    INST-04: Desktop shortcut creation.
    INST-05: Absolute path to venv's pythonw.exe embedded in the shortcut.
    INST-06: winshell creates .lnk files without admin rights.
    """
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

    try:
        with winshell.shortcut(str(shortcut_path)) as link:
            link.path = str(pythonw.resolve())
            link.arguments = f'"{service_py.resolve()}"'
            link.working_directory = str(service_py.parent.resolve())
            link.description = "AgentTalk TTS Service"
    except Exception as exc:
        # pywin32 post-install script may not have run — give actionable guidance
        print(
            f"WARNING: Could not create desktop shortcut: {exc}\n"
            "If you see a COM/DLL error, run: python -m pywin32_postinstall -install"
        )
        return

    print(f"  Desktop shortcut created: {shortcut_path}")

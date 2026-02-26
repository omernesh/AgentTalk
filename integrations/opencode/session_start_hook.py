"""
AgentTalk opencode SessionStart hook.

Mirror of agenttalk/hooks/session_start_hook.py for opencode.
Checks PID file and launches the AgentTalk service if not running.

Usage: Register this file in opencode config as a SessionStart hook.

See integrations/opencode/README.md for registration instructions.
"""
import sys
import json
import os
import platform
import subprocess
from pathlib import Path

# Import _config_dir for cross-platform config directory resolution.
try:
    from agenttalk.config_loader import _config_dir
    CONFIG_DIR = _config_dir()
except Exception:
    # Fallback: compute without importing agenttalk
    _system = platform.system()
    if _system == "Windows":
        _appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        CONFIG_DIR = Path(_appdata) / "AgentTalk"
    elif _system == "Darwin":
        CONFIG_DIR = Path.home() / "Library" / "Application Support" / "AgentTalk"
    else:
        _xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        CONFIG_DIR = Path(_xdg) / "AgentTalk"

PID_FILE = CONFIG_DIR / "service.pid"
SERVICE_PATH_FILE = CONFIG_DIR / "service_path.txt"
PYTHONW_PATH_FILE = CONFIG_DIR / "pythonw_path.txt"


def _service_is_running() -> bool:
    """Return True if the service PID file points to a live process."""
    if not PID_FILE.exists():
        return False
    try:
        pid_text = PID_FILE.read_text(encoding='utf-8').strip()
        if not pid_text:
            return False
        pid = int(pid_text)
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except ValueError as exc:
        print(f"[agenttalk opencode hook] Corrupt PID file — ignoring: {exc}", file=sys.stderr)
        return False
    except Exception:
        return False


def main() -> None:
    # Binary read + explicit UTF-8 decode.
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[agenttalk opencode hook] Failed to parse stdin: {exc}", file=sys.stderr)
        sys.exit(0)

    # Only auto-launch on fresh sessions.
    # opencode hook events may use 'type', 'event', or 'source' key.
    event_type = (
        payload.get('type', '') or
        payload.get('event', '') or
        payload.get('source', '')
    )
    # Accept 'startup', 'session_start', 'start', or empty (assume startup)
    if event_type and event_type not in ('startup', 'session_start', 'start', 'new'):
        sys.exit(0)

    if _service_is_running():
        sys.exit(0)

    # Launch service as a fully detached subprocess.
    try:
        pythonw = Path(PYTHONW_PATH_FILE.read_text(encoding='utf-8').strip())
        service_py = Path(SERVICE_PATH_FILE.read_text(encoding='utf-8').strip())

        if platform.system() == "Windows":
            subprocess.Popen(
                [str(pythonw), str(service_py)],
                creationflags=(
                    subprocess.DETACHED_PROCESS |
                    subprocess.CREATE_NEW_PROCESS_GROUP
                ),
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [str(pythonw), str(service_py)],
                start_new_session=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError as exc:
        print(f"[agenttalk opencode hook] Setup files missing — run 'agenttalk setup': {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"[agenttalk opencode hook] Failed to launch service: {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()

"""
AgentTalk SessionStart hook.
Checks PID file and launches service if not running.

Requirements: HOOK-02, HOOK-03, HOOK-04
Called by Claude Code on new session startup.
Registered in ~/.claude/settings.json with async: true by agenttalk setup.
"""
import sys
import json
import os
import subprocess
from pathlib import Path

APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
PID_FILE = APPDATA / 'AgentTalk' / 'service.pid'
# These two files are written by `agenttalk setup` (Plan 02).
# They contain absolute paths so the hook works regardless of cwd.
SERVICE_PATH_FILE = APPDATA / 'AgentTalk' / 'service_path.txt'
PYTHONW_PATH_FILE = APPDATA / 'AgentTalk' / 'pythonw_path.txt'


def _service_is_running() -> bool:
    """Return True if the service PID file points to a live process."""
    if not PID_FILE.exists():
        return False
    try:
        pid_text = PID_FILE.read_text(encoding='utf-8').strip()
        if not pid_text:
            return False
        pid = int(pid_text)
        # os.kill(pid, 0) — signal 0 tests existence without sending a real signal.
        # Raises ProcessLookupError if no such PID exists.
        # Raises PermissionError if process exists but we cannot signal it
        # (treat as running — conservative; PID lock prevents duplicate instances anyway).
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists — we just don't have permission to signal it
    except ValueError as exc:
        print(f"[agenttalk session_start_hook] Corrupt PID file — ignoring: {exc}", file=sys.stderr)
        return False
    except Exception:
        return False


def main() -> None:
    # HOOK-04: Binary read + explicit UTF-8 decode — CP1252 safe.
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[agenttalk session_start_hook] Failed to parse stdin: {exc}", file=sys.stderr)
        sys.exit(0)

    # HOOK-02: Only auto-launch on fresh sessions.
    # source values: 'startup' (new session), 'resume', 'clear', 'compact'.
    # Service may already be running for resume/clear — PID check handles that,
    # but filtering here avoids the overhead for non-startup events.
    source = payload.get('source', '')
    if source != 'startup':
        sys.exit(0)

    if _service_is_running():
        sys.exit(0)

    # Launch service as a fully detached subprocess.
    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP fully separates the child from
    # the hook's process tree — essential so Claude Code doesn't own the service process.
    try:
        pythonw = Path(PYTHONW_PATH_FILE.read_text(encoding='utf-8').strip())
        service_py = Path(SERVICE_PATH_FILE.read_text(encoding='utf-8').strip())

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
    except FileNotFoundError as exc:
        print(f"[agenttalk session_start_hook] Setup files missing — run 'agenttalk setup': {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"[agenttalk session_start_hook] Failed to launch service: {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()

"""
AgentTalk setup module.
Registers Claude Code hooks and writes path files for hook scripts.

Requirements: HOOK-05
Called by: agenttalk setup CLI command (Phase 6) or directly: python -m agenttalk.setup
"""
import json
import os
import sys
from pathlib import Path

# ~/.claude/settings.json — user-scope hooks apply to all Claude Code projects
SETTINGS_PATH = Path.home() / '.claude' / 'settings.json'

# %APPDATA%\AgentTalk\ — service runtime directory (created by Phase 1)
APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
AGENTTALK_DIR = APPDATA / 'AgentTalk'

# Hook scripts live in agenttalk/hooks/ relative to this file
_THIS_DIR = Path(__file__).parent
HOOKS_DIR = _THIS_DIR / 'hooks'
STOP_HOOK_PATH = HOOKS_DIR / 'stop_hook.py'
SESSION_START_HOOK_PATH = HOOKS_DIR / 'session_start_hook.py'
SERVICE_PATH = _THIS_DIR / 'service.py'


def _get_pythonw_path() -> Path:
    """
    Return the absolute path to pythonw.exe in the current Python environment.
    pythonw.exe lives in the same directory as python.exe (Scripts/ in a venv).
    Falls back to 'pythonw' (PATH lookup) if pythonw.exe is not found beside python.exe.
    """
    python_exe = Path(sys.executable)
    pythonw_candidate = python_exe.parent / 'pythonw.exe'
    if pythonw_candidate.exists():
        return pythonw_candidate
    # Fallback: try same name pattern on non-standard installations
    return Path('pythonw')


def _write_path_files(pythonw: Path) -> None:
    """
    Write absolute paths into %APPDATA%\\AgentTalk\\ so session_start_hook.py
    can find pythonw.exe and service.py without importing from the agenttalk package.
    """
    AGENTTALK_DIR.mkdir(parents=True, exist_ok=True)
    pythonw_txt = AGENTTALK_DIR / 'pythonw_path.txt'
    service_txt = AGENTTALK_DIR / 'service_path.txt'
    try:
        pythonw_txt.write_text(str(pythonw.resolve()), encoding='utf-8')
    except OSError as exc:
        raise OSError(
            f"Cannot write {pythonw_txt}: {exc}\n"
            "Check that the AgentTalk directory is writable."
        ) from exc
    try:
        service_txt.write_text(str(SERVICE_PATH.resolve()), encoding='utf-8')
    except OSError as exc:
        raise OSError(
            f"Cannot write {service_txt}: {exc}\n"
            "Check that the AgentTalk directory is writable."
        ) from exc


def _build_hook_command(pythonw: Path, hook_script: Path) -> str:
    """
    Build the hook command string with absolute paths, quoted for Windows shell.
    Format: "C:\\path\\pythonw.exe" "C:\\path\\hook.py"
    """
    return f'"{pythonw.resolve()}" "{hook_script.resolve()}"'


def _is_agenttalk_hook_present(inner_hooks: list, hook_filename: str) -> bool:
    """
    Return True if any existing hook command references agenttalk and the hook filename.
    Case-insensitive to handle mixed-case Windows paths.
    Idempotency: prevents duplicate registration.
    """
    for hook in inner_hooks:
        cmd = hook.get('command', '').lower()
        if 'agenttalk' in cmd and hook_filename.lower() in cmd:
            return True
    return False


def _merge_hook_into_array(
    matcher_groups: list,
    hook_entry: dict,
    hook_filename: str,
) -> None:
    """
    Append hook_entry into the inner hooks array of the FIRST matcher group,
    unless an agenttalk entry for this hook is already present (idempotent).

    The settings.json structure is:
      "Stop": [                          <- matcher_groups (list of matcher objects)
        {                                <- matcher_groups[0]
          "hooks": [                     <- inner hooks array
            { "type": "command", ... }   <- individual hook entries
          ]
        }
      ]
    """
    if not matcher_groups:
        # No existing matcher group — create one
        matcher_groups.append({'hooks': [hook_entry]})
        return

    first_group = matcher_groups[0]
    inner_hooks = first_group.setdefault('hooks', [])

    if _is_agenttalk_hook_present(inner_hooks, hook_filename):
        return  # Already registered — skip

    inner_hooks.append(hook_entry)


def register_hooks(
    pythonw: 'Path | None' = None,
    settings_path: 'Path | None' = None,
) -> None:
    """
    Merge AgentTalk hooks into ~/.claude/settings.json without overwriting
    existing hook entries. Idempotent: running twice produces exactly one entry.

    Args:
        pythonw: Override pythonw.exe path (for testing). Defaults to auto-detected path.
        settings_path: Override settings.json path (for testing). Defaults to ~/.claude/settings.json.
    """
    if pythonw is None:
        pythonw = _get_pythonw_path()
    if settings_path is None:
        settings_path = SETTINGS_PATH

    # Write path files for session_start_hook.py to consume at runtime
    _write_path_files(pythonw)

    # Load existing settings (or start from empty dict if file doesn't exist)
    settings: dict = {}
    if settings_path.exists():
        raw = settings_path.read_text(encoding='utf-8')
        try:
            settings = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Cannot parse {settings_path}: {exc}\n"
                "The file contains invalid JSON. Back it up, fix the syntax, "
                "then re-run 'agenttalk setup'."
            ) from exc

    hooks_section = settings.setdefault('hooks', {})

    # Build hook entries
    stop_entry = {
        'type': 'command',
        'command': _build_hook_command(pythonw, STOP_HOOK_PATH),
        'async': True,
        'timeout': 10,
    }
    session_entry = {
        'type': 'command',
        'command': _build_hook_command(pythonw, SESSION_START_HOOK_PATH),
        'async': True,
        'timeout': 10,
    }

    # Merge into existing Stop and SessionStart arrays
    stop_groups = hooks_section.setdefault('Stop', [])
    _merge_hook_into_array(stop_groups, stop_entry, 'stop_hook.py')

    session_groups = hooks_section.setdefault('SessionStart', [])
    _merge_hook_into_array(session_groups, session_entry, 'session_start_hook.py')

    # Atomic write — write to .tmp then replace to avoid half-written settings.json
    # CRITICAL: encoding='utf-8' (NOT 'utf-8-sig') — BOM breaks Claude Code JSON parser
    tmp_path = settings_path.with_suffix('.json.tmp')
    try:
        tmp_path.write_text(json.dumps(settings, indent=2), encoding='utf-8')
        tmp_path.replace(settings_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    print(f"AgentTalk hooks registered in {settings_path}")
    print(f"  Stop hook: {STOP_HOOK_PATH.resolve()}")
    print(f"  SessionStart hook: {SESSION_START_HOOK_PATH.resolve()}")


if __name__ == '__main__':
    register_hooks()

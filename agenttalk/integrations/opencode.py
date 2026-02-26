"""
AgentTalk opencode integration helper.

Provides register_opencode_hooks() which registers the AgentTalk hooks
in the opencode configuration file.

Called by: agenttalk setup --opencode
"""
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from agenttalk.config_loader import _config_dir


# ---------------------------------------------------------------------------
# opencode config directory discovery
# ---------------------------------------------------------------------------

def _opencode_config_dir() -> Path:
    """
    Return the opencode configuration directory for the current platform.

    opencode uses ~/.opencode/ on all platforms, but respects XDG_CONFIG_HOME
    on Linux.
    """
    system = platform.system()
    if system == "Windows":
        # opencode on Windows typically uses %APPDATA%\opencode\ or ~/.opencode/
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = Path(appdata) / "opencode"
            if candidate.exists():
                return candidate
    elif system != "Darwin":  # Linux
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            candidate = Path(xdg) / "opencode"
            if candidate.exists():
                return candidate

    # Default: ~/.opencode/ on all platforms
    return Path.home() / ".opencode"


# ---------------------------------------------------------------------------
# Hook script paths
# ---------------------------------------------------------------------------

def _hook_script_src_dir() -> Path:
    """Return the path to the opencode hook scripts in the installed package."""
    # When installed via pip, the hook scripts live alongside installer.py
    # in the agenttalk package. We ship them as data files.
    # First try: relative to this file (agenttalk/integrations/opencode.py)
    pkg_dir = Path(__file__).parent.parent  # agenttalk/
    hooks_src = pkg_dir.parent / "integrations" / "opencode"
    if hooks_src.exists():
        return hooks_src
    # Fallback: use the agenttalk hooks directory (Claude Code hooks as template)
    return pkg_dir / "hooks"


def _get_hook_scripts() -> dict[str, Path]:
    """
    Return paths to the hook scripts, copying them to the AgentTalk config dir
    if the integration scripts are not available.
    """
    src_dir = _hook_script_src_dir()
    config_dir = _config_dir()
    opencode_hooks_dir = config_dir / "opencode_hooks"
    opencode_hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts = {}

    # Session start hook
    session_src = src_dir / "session_start_hook.py"
    if not session_src.exists():
        # Fall back to Claude Code session_start_hook with opencode compatible stdin parsing
        session_src = Path(__file__).parent.parent / "hooks" / "session_start_hook.py"

    session_dest = opencode_hooks_dir / "session_start_hook.py"
    if session_src.exists():
        shutil.copy2(session_src, session_dest)
        scripts["session_start"] = session_dest

    # Stop / post-response hook
    stop_src = src_dir / "stop_hook.py"
    if not stop_src.exists():
        stop_src = Path(__file__).parent.parent / "hooks" / "stop_hook.py"

    stop_dest = opencode_hooks_dir / "stop_hook.py"
    if stop_src.exists():
        shutil.copy2(stop_src, stop_dest)
        scripts["stop"] = stop_dest

    return scripts


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_opencode_hooks() -> None:
    """
    Register AgentTalk hooks in the opencode configuration.

    Writes hook entries to ~/.opencode/config.json (or creates it if absent).
    The hooks are registered for SessionStart and PostResponse events.

    Idempotent: re-running will update the hook paths if they changed.
    """
    python_exe = sys.executable

    # Copy hook scripts to AgentTalk config dir
    scripts = _get_hook_scripts()
    if not scripts:
        print("WARNING: Could not locate opencode hook scripts.")
        return

    session_start_script = scripts.get("session_start")
    stop_script = scripts.get("stop")

    # Find or create opencode config directory
    opencode_dir = _opencode_config_dir()
    opencode_dir.mkdir(parents=True, exist_ok=True)

    config_path = opencode_dir / "config.json"

    # Load existing config (if any)
    config: dict = {}
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            config = json.loads(text)
            if not isinstance(config, dict):
                config = {}
        except Exception:
            config = {}

    # Build hook entries
    if "hooks" not in config or not isinstance(config["hooks"], dict):
        config["hooks"] = {}

    if session_start_script:
        config["hooks"]["SessionStart"] = [
            {
                "command": python_exe,
                "args": [str(session_start_script)],
                "async": True,
            }
        ]

    if stop_script:
        config["hooks"]["PostResponse"] = [
            {
                "command": python_exe,
                "args": [str(stop_script)],
                "async": True,
            }
        ]

    # Write config atomically
    tmp = config_path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
        tmp.replace(config_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    print(f"  opencode hooks registered in {config_path}")
    if session_start_script:
        print(f"    SessionStart -> {session_start_script}")
    if stop_script:
        print(f"    PostResponse -> {stop_script}")
    print("\n  To verify, run opencode and check that AgentTalk speaks responses.")
    print("  For manual setup instructions: integrations/opencode/README.md")

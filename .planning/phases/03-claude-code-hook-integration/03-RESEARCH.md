# Phase 3: Claude Code Hook Integration - Research

**Researched:** 2026-02-26
**Domain:** Claude Code hooks (Stop + SessionStart), Python hook scripts, settings.json registration
**Confidence:** HIGH — core hook schema verified against official live docs; Windows-specific behavior verified from Phase 1/2 accumulated decisions

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HOOK-01 | `Stop` hook reads `last_assistant_message` from stdin JSON and POSTs to `/speak` endpoint | Official docs confirm `last_assistant_message` field exists directly in Stop hook stdin payload — no transcript parsing needed |
| HOOK-02 | `SessionStart` hook checks PID file and launches the service if not already running | Official docs confirm `source: "startup"` matcher; `DETACHED_PROCESS` pattern validated in Phase 1; PID file at `%APPDATA%\AgentTalk\service.pid` already implemented |
| HOOK-03 | Both hooks configured with `"async": true` so they never block Claude Code's UI | Official docs confirm `async: true` field on `type: "command"` hooks; async hooks cannot block/control Claude but that is intentional for AgentTalk |
| HOOK-04 | Hook scripts read stdin as `sys.stdin.buffer.read().decode('utf-8')` to handle non-ASCII | Windows CP1252 vs UTF-8 pitfall confirmed from research; stdlib `sys.stdin.buffer` pattern is correct |
| HOOK-05 | Hook registration automated by `agenttalk setup` — no manual JSON editing required | User already has existing hooks in `~/.claude/settings.json`; setup must merge new hooks into existing array without overwriting |
</phase_requirements>

---

## Summary

Phase 3 connects the working AgentTalk service (POST /speak live after Phase 2) to Claude Code via two hook scripts. The Stop hook reads the `last_assistant_message` field from stdin JSON and POSTs it to `http://localhost:5050/speak`. The SessionStart hook checks the PID lock file and launches the service detached if it is not running. Both hooks use `async: true` so Claude Code's UI is never blocked.

The official Claude Code hooks documentation (fetched live at https://code.claude.com/docs/en/hooks) confirms all the specific JSON schemas, field names, and async behavior needed for this phase. The `last_assistant_message` field is present directly in the Stop hook's stdin payload — no transcript parsing is required. The `source` field in SessionStart enables matching on `"startup"` to launch the service only on fresh sessions.

A critical constraint for HOOK-05: the user already has hooks in `~/.claude/settings.json` (existing Stop hook playing a sound, existing SessionStart hook for gsd-check-update.js). The `agenttalk setup` command must merge the new AgentTalk hooks into the existing arrays without overwriting them. Hook registration must be idempotent (running setup twice should not duplicate hooks).

**Primary recommendation:** Write two standalone Python hook scripts, register them in `~/.claude/settings.json` with `async: true`, and implement `agenttalk setup` as a Python function that reads, merges, and writes the settings JSON atomically.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (sys, json, os, subprocess) | 3.12 (current dev machine) | Hook scripts — read stdin, parse JSON, launch service | Zero dependencies; hook scripts must be self-contained and launch quickly |
| requests | (already installed in venv) | HTTP POST from Stop hook to /speak endpoint | Simpler than urllib for a one-shot POST; httpx also works but requests is already installed |
| subprocess | stdlib | SessionStart hook — launch service via pythonw.exe | DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP flags required to fully detach from hook's process tree |
| psutil | >=5.9 (in requirements.txt) | SessionStart hook — verify PID from lock file is still alive | Already in project; provides cross-platform `pid_exists()` and `Process.name()` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | Parse settings.json during setup | Merging hook configuration into existing settings file |
| pathlib.Path | stdlib | Construct %APPDATA% paths to PID file, settings.json | Clean Windows path handling without string manipulation |
| urllib.request | stdlib | Alternative to requests for hook POST | Use if requests is not importable in the hook's environment; urllib is always available |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| requests in hook | urllib.request | urllib is always available (no venv dependency); requests is already installed but the hook script must resolve the correct venv. Use urllib.request for maximum portability |
| pythonw.exe for hook | python.exe | pythonw.exe suppresses console windows but its path must be absolute; python.exe is simpler but flashes a console on each response |
| ~/.claude/settings.json (user scope) | .claude/settings.json (project scope) | User scope applies to all projects; project scope is per-repo. HOOK-05 specifies `agenttalk setup` writes to `~/.claude/settings.json` (user scope, per INST-03) |

**No pip install for hook scripts.** Hook scripts are standalone Python files using only stdlib + requests (or urllib.request). They do not import from the agenttalk package to avoid import path resolution issues.

---

## Architecture Patterns

### File Locations

```
~/.claude/
└── settings.json                  # User-scope hooks (modified by agenttalk setup)

agenttalk/
├── hooks/
│   ├── stop_hook.py               # Stop hook script (speaks last_assistant_message)
│   └── session_start_hook.py      # SessionStart hook script (auto-launch service)
├── setup.py                       # agenttalk setup command (hook registration)
├── service.py                     # Already exists (Phase 1/2)
├── tts_worker.py                  # Already exists (Phase 2)
└── preprocessor.py                # Already exists (Phase 2)

%APPDATA%\AgentTalk\
├── service.pid                    # PID lock file (Phase 1)
└── agenttalk.log                  # Service log (Phase 1)
```

### Pattern 1: Stop Hook — Read stdin, POST to /speak

**What:** Hook script receives Stop event JSON on stdin, extracts `last_assistant_message`, POSTs to `http://localhost:5050/speak`, exits 0 immediately.
**When to use:** Every assistant response — this is the core TTS trigger.

```python
# Source: https://code.claude.com/docs/en/hooks (Stop event schema)
# agenttalk/hooks/stop_hook.py
import sys
import json
import urllib.request

def main():
    # HOOK-04: Read stdin as raw bytes, decode as UTF-8.
    # sys.stdin on Windows defaults to CP1252 — must use buffer for non-ASCII safety.
    raw = sys.stdin.buffer.read()
    payload = json.loads(raw.decode('utf-8'))

    # Guard: do not trigger if a Stop hook is already running (prevents loop)
    if payload.get('stop_hook_active', False):
        sys.exit(0)

    text = payload.get('last_assistant_message', '').strip()
    if not text:
        sys.exit(0)

    # POST to the local /speak endpoint (service running on localhost:5050)
    body = json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:5050/speak',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            pass  # 202 Queued or 200 Skipped — both are fine
    except Exception:
        pass  # Service not running — silent fail; SessionStart handles restart

    sys.exit(0)

if __name__ == '__main__':
    main()
```

### Pattern 2: SessionStart Hook — Check PID, Launch Service

**What:** Hook script checks if service is running via PID lock file. If not running, launches `pythonw.exe service.py` as a fully detached subprocess.
**When to use:** On session startup only (matcher: `"startup"`).

```python
# Source: https://code.claude.com/docs/en/hooks (SessionStart event schema)
# agenttalk/hooks/session_start_hook.py
import sys
import json
import os
import subprocess
from pathlib import Path

APPDATA = Path(os.environ['APPDATA'])
PID_FILE = APPDATA / 'AgentTalk' / 'service.pid'
# Absolute path to service.py resolved at setup time — written by agenttalk setup
SERVICE_SCRIPT = APPDATA / 'AgentTalk' / 'service_path.txt'

def service_is_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        import psutil
        pid = int(PID_FILE.read_text(encoding='utf-8').strip())
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if 'python' in proc.name().lower():
                return True
    except Exception:
        pass
    return False

def main():
    raw = sys.stdin.buffer.read()
    payload = json.loads(raw.decode('utf-8'))

    # Only auto-start on new sessions, not resume/clear/compact
    source = payload.get('source', '')
    if source != 'startup':
        sys.exit(0)

    if service_is_running():
        sys.exit(0)

    # Read absolute service.py path stored by agenttalk setup
    try:
        service_py = Path(SERVICE_SCRIPT.read_text(encoding='utf-8').strip())
        pythonw = service_py.parent.parent / '.venv' / 'Scripts' / 'pythonw.exe'
        if not pythonw.exists():
            # Fallback: search PATH for pythonw.exe
            import shutil
            pythonw = shutil.which('pythonw') or 'pythonw'

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
    except Exception:
        pass  # Silent fail — don't block Claude Code session startup

    sys.exit(0)

if __name__ == '__main__':
    main()
```

### Pattern 3: Hook Registration (agenttalk setup)

**What:** Python function reads `~/.claude/settings.json`, merges AgentTalk hooks into existing arrays, writes back atomically.
**Critical:** Must not overwrite existing hooks (gsd hooks, sound player hook, etc.).

```python
# Source: Official Claude Code settings.json format verified from live docs
# agenttalk/setup.py (hook registration portion)
import json
import os
from pathlib import Path

SETTINGS_PATH = Path.home() / '.claude' / 'settings.json'

STOP_HOOK_ENTRY = {
    "type": "command",
    "command": None,  # filled at runtime with absolute path
    "async": True,
    "timeout": 10,
}

SESSION_START_HOOK_ENTRY = {
    "type": "command",
    "command": None,  # filled at runtime with absolute path
    "async": True,
    "timeout": 10,
}

def register_hooks(pythonw_path: str, hooks_dir: str) -> None:
    """
    Merge AgentTalk hooks into ~/.claude/settings.json without overwriting
    existing hook entries. Idempotent: running twice does not duplicate entries.
    """
    # Load existing settings
    settings = {}
    if SETTINGS_PATH.exists():
        settings = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))

    hooks = settings.setdefault('hooks', {})

    stop_cmd = f'"{pythonw_path}" "{hooks_dir}/stop_hook.py"'
    session_cmd = f'"{pythonw_path}" "{hooks_dir}/session_start_hook.py"'

    # Stop hook: append to existing Stop array if not already present
    stop_hooks = hooks.setdefault('Stop', [{'hooks': []}])
    stop_entry = {**STOP_HOOK_ENTRY, 'command': stop_cmd}
    _add_hook_if_absent(stop_hooks, stop_entry)

    # SessionStart hook: append to existing SessionStart array
    session_hooks = hooks.setdefault('SessionStart', [{'hooks': []}])
    session_entry = {**SESSION_START_HOOK_ENTRY, 'command': session_cmd}
    _add_hook_if_absent(session_hooks, session_entry)

    # Atomic write
    tmp = SETTINGS_PATH.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    tmp.replace(SETTINGS_PATH)
    print(f"Hooks registered in {SETTINGS_PATH}")

def _add_hook_if_absent(matcher_groups: list, new_entry: dict) -> None:
    """Add hook entry to the first matcher group if command not already present."""
    first_group = matcher_groups[0]
    inner_hooks = first_group.setdefault('hooks', [])
    cmd = new_entry['command']
    existing_cmds = [h.get('command', '') for h in inner_hooks]
    if not any('stop_hook.py' in c or 'session_start_hook.py' in c
               for c in existing_cmds if 'agenttalk' in c.lower()):
        inner_hooks.append(new_entry)
```

### Settings.json Structure (Verified)

The user's existing `~/.claude/settings.json` has this hook structure:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -Command \"...\""
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"C:/Users/omern/.claude/hooks/gsd-check-update.js\""
          }
        ]
      }
    ]
  }
}
```

AgentTalk hooks must be appended to the inner `hooks` arrays, not as new top-level matcher groups. The correct merged result:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -Command \"...\""
          },
          {
            "type": "command",
            "command": "\"C:\\...\\pythonw.exe\" \"C:\\...\\stop_hook.py\"",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### Anti-Patterns to Avoid

- **Reading transcript file:** `transcript_path` JSONL parsing is fragile and slow. Use `last_assistant_message` directly.
- **Blocking hooks:** Omitting `"async": true` causes Claude Code's UI to freeze during TTS playback (violates HOOK-03).
- **stop_hook_active guard missing:** If the Stop hook itself triggers a Claude Code continuation, the Stop hook fires again, causing infinite TTS loop. Always check `stop_hook_active`.
- **sys.stdin.read() on Windows:** Defaults to CP1252 encoding — must use `sys.stdin.buffer.read().decode('utf-8')`.
- **Overwriting settings.json:** `json.dump()` on the full settings object destroys existing hooks. Must merge, not replace.
- **Using relative paths in hook commands:** Hook commands execute with Claude Code's cwd, not the project root. All paths must be absolute.
- **SessionStart matching all sources:** Running `resume` and `compact` triggers too. Only `"startup"` source should launch the service — it may already be running for resume/clear sessions.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PID alive check in session_start_hook | Custom pid_exists() via os.kill or psutil-less logic | `psutil.pid_exists()` + `Process.name()` | Already in requirements.txt; handles edge cases (PID reuse, access denied, stale file) |
| HTTP POST from hook | Raw socket or urllib.urlopen | `urllib.request.urlopen` (stdlib) or `requests` | urllib is zero-dependency, already available; requests already installed in venv |
| JSON merge for settings.json | String replacement or regex patching | Load JSON → mutate dict → dump JSON | JSON is structured data; string manipulation breaks on special chars, formatting differences |
| Service path resolution | Hard-coded path in hook | Absolute path written by `agenttalk setup` into `%APPDATA%\AgentTalk\service_path.txt` | User's venv location varies; setup knows the exact pythonw.exe path at install time |

**Key insight:** Hook scripts are the most fragile part of this integration — they execute in Claude Code's environment, not the project's venv. Keep them minimal, use only stdlib where possible, and fail silently so they never block Claude Code.

---

## Common Pitfalls

### Pitfall 1: stop_hook_active Not Checked (Infinite Loop)

**What goes wrong:** The Stop hook fires, POSTs text to /speak, and exits 0. If the Stop hook also outputs a `systemMessage` or other JSON that causes Claude to continue, a second Stop hook fires on that continuation, triggering a second TTS POST — and so on indefinitely.
**Why it happens:** Claude Code re-runs Stop hooks when conversation continues as a result of a hook action.
**How to avoid:** Always check `payload.get('stop_hook_active', False)` at the start of the Stop hook and exit 0 immediately if True.
**Warning signs:** TTS speaks the same message repeatedly; service queue hits 429 (full) immediately after first response.

### Pitfall 2: Windows stdin Encoding (UnicodeDecodeError)

**What goes wrong:** `json.loads(sys.stdin.read())` raises `UnicodeDecodeError: 'charmap' codec can't decode byte` when assistant message contains non-ASCII characters (em dash, smart quotes, accented letters, etc.).
**Why it happens:** Python's `sys.stdin` on Windows defaults to the system code page (CP1252 or similar), not UTF-8. Claude Code sends hook payloads as UTF-8.
**How to avoid:** Always use `sys.stdin.buffer.read().decode('utf-8')`. This is HOOK-04's explicit requirement.
**Warning signs:** Hook works for ASCII-only messages; crashes silently on messages with any special character.

### Pitfall 3: Hook Command Path Resolution Fails

**What goes wrong:** Hook script in `~/.claude/settings.json` is specified as `python agenttalk/hooks/stop_hook.py` (relative path). Claude Code executes hooks with the current working directory of the Claude Code session, which varies per project. The relative path fails.
**Why it happens:** Hook `command` strings are executed as shell commands; relative paths resolve against the session's cwd, not any fixed location.
**How to avoid:** `agenttalk setup` must write the absolute path to both `pythonw.exe` and the hook scripts. Use `INST-05`'s requirement: "writes hook scripts using the absolute path to the venv's pythonw.exe."
**Warning signs:** Hook shows no error in Claude Code's verbose mode; service is never launched; no audio plays.

### Pitfall 4: SessionStart source Field Verification

**What goes wrong:** Prior research flagged that `source: "startup"` matcher syntax "should be verified against live Claude Code version." The live docs confirm: `source` values are `startup`, `resume`, `clear`, `compact`. The SessionStart matcher matches on the `source` field value.
**Resolution:** VERIFIED against official docs. `matcher: "startup"` on SessionStart fires only for new sessions. However, note from the docs: `Stop` and several other events do NOT support matchers — they always fire on every occurrence. This means the Stop hook cannot filter by session source; it must guard internally.
**Warning signs:** None if implemented correctly; risk of over-triggering if the SessionStart hook launches the service on resume (service already running, PID check handles this gracefully anyway).

### Pitfall 5: settings.json Write Race / UTF-8 BOM

**What goes wrong:** If `agenttalk setup` writes `settings.json` with `utf-8-sig` encoding (UTF-8 with BOM), Claude Code fails to parse the file with `SyntaxError: Unexpected token 'C', "Claude con..."` (confirmed Claude Code bug with BOM).
**Why it happens:** Python's `open(path, encoding='utf-8-sig')` or certain editors add a BOM. Claude Code's JSON parser rejects BOM-prefixed files.
**How to avoid:** Always write with `encoding='utf-8'` (not `utf-8-sig`). Verify the written file is BOM-free.
**Warning signs:** Claude Code shows JSON parse error on startup; hooks stop firing; `settings.json` first bytes are `EF BB BF` (BOM).

### Pitfall 6: async Hook Cannot Block

**What goes wrong:** Developer wants the Stop hook to block Claude Code until TTS finishes (ensuring user hears the response before typing). Sets `"async": false` to achieve this. This works — but violates HOOK-03, which explicitly requires non-blocking behavior.
**Why it matters:** Synchronous Stop hooks block Claude Code's UI for the entire TTS duration. A 30-second response takes 30 seconds of TTS. The terminal is frozen.
**How to avoid:** Always use `"async": true` for both hooks. TTS plays in the background via the service's audio queue. The hooks just submit the request and exit.
**Warning signs:** Terminal appears frozen after receiving assistant response; user cannot type while audio plays.

### Pitfall 7: Service Not Ready When Stop Hook Fires

**What goes wrong:** Opening Claude Code triggers SessionStart hook, which launches the service. The service takes ~5 seconds to warm up (Kokoro model load + warmup synthesis). If the user immediately types a message and gets a response, the Stop hook fires before the service is ready. The POST to /speak returns 503.
**Why it happens:** Service warmup is intentionally slow (TTS-02 requirement); hooks fire on the first response.
**How to avoid:** The Stop hook should handle 503 silently — log and exit 0. The `/health` endpoint returns 503 while initializing. The stop_hook.py should not retry. The missed first response is acceptable behavior for v1.
**Warning signs:** No audio on first response after a fresh session open; subsequent responses speak correctly.

---

## Code Examples

### Complete Stop Hook Script

```python
# Source: https://code.claude.com/docs/en/hooks
# agenttalk/hooks/stop_hook.py
"""
AgentTalk Stop hook.
Reads last_assistant_message from stdin JSON and POSTs to /speak endpoint.

Requirements: HOOK-01, HOOK-03, HOOK-04
Called by Claude Code after every assistant response.
"""
import sys
import json
import urllib.request
import urllib.error

SERVICE_URL = 'http://localhost:5050/speak'
TIMEOUT_SECS = 3  # Do not block for more than 3 seconds

def main() -> None:
    # HOOK-04: Binary read + explicit UTF-8 decode — CP1252 safe
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        sys.exit(0)  # Malformed input — silent fail

    # HOOK-01: Guard against infinite loop
    if payload.get('stop_hook_active', False):
        sys.exit(0)

    text = payload.get('last_assistant_message', '').strip()
    if not text:
        sys.exit(0)

    # HOOK-01: POST text to /speak endpoint
    body = json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(
        SERVICE_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as _:
            pass  # 202 queued or 200 skipped — both fine
    except urllib.error.URLError:
        pass  # Service not running or overloaded — silent fail
    except Exception:
        pass  # Any other error — silent fail

    sys.exit(0)  # HOOK-03: Exit immediately; async handles non-blocking

if __name__ == '__main__':
    main()
```

### Complete SessionStart Hook Script

```python
# Source: https://code.claude.com/docs/en/hooks
# agenttalk/hooks/session_start_hook.py
"""
AgentTalk SessionStart hook.
Checks PID file and launches service if not running.

Requirements: HOOK-02, HOOK-03, HOOK-04
Called by Claude Code on new session startup.
"""
import sys
import json
import os
import subprocess
from pathlib import Path

APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
PID_FILE = APPDATA / 'AgentTalk' / 'service.pid'
SERVICE_PATH_FILE = APPDATA / 'AgentTalk' / 'service_path.txt'
PYTHONW_PATH_FILE = APPDATA / 'AgentTalk' / 'pythonw_path.txt'

def _service_is_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid_text = PID_FILE.read_text(encoding='utf-8').strip()
        if not pid_text:
            return False
        pid = int(pid_text)
        # Use os.kill(pid, 0) as lightweight existence check — avoids psutil import
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except Exception:
        return False

def main() -> None:
    # HOOK-04: Binary read + explicit UTF-8 decode
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except Exception:
        sys.exit(0)

    # HOOK-02: Only auto-launch on fresh sessions, not resume/clear/compact
    source = payload.get('source', '')
    if source not in ('startup',):
        sys.exit(0)

    if _service_is_running():
        sys.exit(0)

    # Launch service as fully detached subprocess
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
    except Exception:
        pass  # HOOK-03: Never block Claude Code session startup

    sys.exit(0)

if __name__ == '__main__':
    main()
```

### Correct settings.json Hook Format (Verified)

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "C:\\...existing hooks...",
          },
          {
            "type": "command",
            "command": "\"C:\\path\\to\\pythonw.exe\" \"C:\\path\\to\\stop_hook.py\"",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"C:/Users/omern/.claude/hooks/gsd-check-update.js\""
          },
          {
            "type": "command",
            "command": "\"C:\\path\\to\\pythonw.exe\" \"C:\\path\\to\\session_start_hook.py\"",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hooks required user to manually edit settings.json | `/hooks` menu in Claude Code for interactive management; `agenttalk setup` CLI for automated registration | 2025 | Setup is now fully automatable |
| 7 hook events | 17 hook events (SessionStart, Stop, PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, Notification, SubagentStart, SubagentStop, TeammateIdle, TaskCompleted, ConfigChange, WorktreeCreate, WorktreeRemove, PreCompact, SessionEnd, UserPromptSubmit) | Jan 2026 | Async hooks added Jan 2026 |
| Hooks always blocked UI | `"async": true` field added | Jan 2026 | AgentTalk's core non-blocking requirement is now officially supported |
| Hook scripts required jq/bash | Full Python scripts supported as commands | Always | Cleaner, portable, handles encoding properly |

**Key confirmed fact:** The `Stop` event does NOT support matchers. It fires on every assistant response. The `stop_hook_active` guard is the only way to prevent loops. `SessionStart` DOES support matchers on `source` field.

**Verified schemas:**
- Stop stdin: `{session_id, transcript_path, cwd, permission_mode, hook_event_name, stop_hook_active, last_assistant_message}`
- SessionStart stdin: `{session_id, transcript_path, cwd, permission_mode, hook_event_name, source, model}`

---

## Open Questions

1. **SessionStart source: "startup" vs all sources**
   - What we know: Matcher `"startup"` fires only for new sessions. Resume/clear/compact use different source values.
   - What's unclear: Should the service also auto-start on `"resume"` (user uses `--resume` flag)? The service may have stopped since the previous session.
   - Recommendation: Match ONLY `"startup"` for HOOK-02 as specified. If the service is dead on resume, the Stop hook will silently fail on that session. Future improvement could check all sources. Keep it simple for v1.

2. **os.kill(pid, 0) vs psutil on Windows**
   - What we know: `os.kill(pid, 0)` on Windows tests process existence. It raises `ProcessLookupError` if the process doesn't exist, `PermissionError` if it exists but access is denied.
   - What's unclear: Does `PermissionError` mean the service IS running but we can't signal it? If so, `_service_is_running()` should return True on PermissionError.
   - Recommendation: Return True on PermissionError (conservative: if we can't kill it, assume it's running). The PID file will still prevent duplicate instances via the service's own `acquire_pid_lock()`.

3. **Stop hook timeout for async**
   - What we know: Async hooks with `timeout: 10` will be cancelled after 10 seconds. The Stop hook's POST takes <1 second to submit (no wait for TTS).
   - What's unclear: Does Claude Code cancel async hooks mid-run? If the hook is cancelled, does it leave the POST incomplete?
   - Recommendation: 10-second timeout is safe. The POST completes in <1 second; the hook exits immediately. No partial-completion risk.

---

## Validation Architecture

No `workflow.nyquist_validation` in `.planning/config.json` (field absent — defaults to false). Skipping formal Validation Architecture section.

**Existing test infrastructure:** pytest 8.3.4, `tests/test_preprocessor.py`. Run with `python -m pytest tests/ -x`.

**Manual test sequence for this phase (cannot be automated without real Claude Code session):**

| Req ID | Test | Type | How to Test |
|--------|------|------|-------------|
| HOOK-01 | Stop hook POSTs last_assistant_message to /speak | Integration | Start service; run `python stop_hook.py` with mock stdin JSON; verify /speak receives correct body |
| HOOK-02 | SessionStart launches service when not running | Integration | Kill service; run `python session_start_hook.py` with `{"source": "startup", ...}` on stdin; verify service starts within 10 seconds |
| HOOK-03 | Neither hook blocks — exits quickly | Manual/Timing | Time `python stop_hook.py` execution; must complete in <1s regardless of TTS duration |
| HOOK-04 | Non-ASCII handled without UnicodeDecodeError | Unit | Run stop_hook.py with `{"last_assistant_message": "café naïve résumé"}` on stdin; verify no crash |
| HOOK-05 | setup merges hooks without overwriting | Unit | Call `register_hooks()` on existing settings.json fixture; assert all existing hooks preserved + AgentTalk hooks added |

Unit tests that CAN be automated (add to `tests/test_hooks.py`):
- `test_stop_hook_guard_stop_hook_active`: with `stop_hook_active: true`, hook exits without POST
- `test_stop_hook_empty_message`: with empty `last_assistant_message`, hook exits without POST
- `test_stop_hook_non_ascii_payload`: accented chars in message, no UnicodeDecodeError
- `test_register_hooks_idempotent`: running register_hooks twice produces exactly one AgentTalk entry
- `test_register_hooks_preserves_existing`: existing hooks survive registration

---

## Sources

### Primary (HIGH confidence)
- https://code.claude.com/docs/en/hooks — live official docs fetched 2026-02-26. Confirms: Stop/SessionStart JSON schemas, `last_assistant_message`, `stop_hook_active`, `source` matcher values, `async: true` field, settings.json structure, hook location scopes.
- `~/.claude/settings.json` (user's machine, read directly) — confirms existing Stop and SessionStart hooks that must be preserved.
- Phase 1/2 accumulated decisions (`.planning/STATE.md`) — confirms: PID file at `%APPDATA%\AgentTalk\service.pid`, DETACHED_PROCESS pattern, pythonw.exe path resolution, Windows encoding issues.

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` (project research, 2026-02-26) — hook JSON schemas, DETACHED_PROCESS subprocess pattern, Windows encoding pitfall. All cross-verified against official docs above.
- `.planning/research/PITFALLS.md` (project research, 2026-02-26) — encoding pitfall, hook scope, PowerShell execution policy, zombie process prevention.

### Tertiary (LOW confidence)
- None — all critical claims verified against official docs or direct code inspection.

---

## Metadata

**Confidence breakdown:**
- Hook JSON schemas (Stop, SessionStart): HIGH — fetched from official live docs 2026-02-26
- async: true behavior: HIGH — explicitly documented in official docs
- Windows encoding (sys.stdin.buffer): HIGH — confirmed from official docs pitfall + Phase 2 accumulated decision
- settings.json merge strategy: HIGH — direct inspection of user's actual settings.json
- os.kill(pid, 0) on Windows: MEDIUM — stdlib behavior, broadly documented but Windows edge cases possible
- SessionStart source matching on "startup": HIGH — confirmed from official docs matcher table

**Research date:** 2026-02-26
**Valid until:** 2026-03-30 (30 days — Claude Code hook docs are relatively stable; async hooks added Jan 2026 are now established)

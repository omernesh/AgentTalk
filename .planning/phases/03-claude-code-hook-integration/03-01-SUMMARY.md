---
phase: 03-claude-code-hook-integration
plan: "01"
subsystem: hooks
tags: [hooks, claude-code, urllib, subprocess, stdin, utf-8]

# Dependency graph
requires:
  - phase: 02-fastapi-http-server-and-tts-queue
    provides: POST /speak endpoint at localhost:5050 that hooks POST to
provides:
  - stop_hook.py: fires on every Claude Code assistant response, POSTs text to /speak
  - session_start_hook.py: fires on session startup, auto-launches service if not running
  - tests/test_hooks.py: 7 unit tests covering all hook behaviors
affects:
  - 03-02-claude-code-hook-integration (setup.py writes path files consumed by session_start_hook)
  - 06-installation (hook scripts are registered by agenttalk setup CLI)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - stdlib-only hook scripts (no agenttalk imports, no third-party deps)
    - sys.stdin.buffer.read().decode('utf-8') for CP1252-safe stdin on Windows
    - importlib.util.spec_from_file_location for loading hooks as test modules
    - patch.object on module-level Path constants (not Path instance methods) for testability

key-files:
  created:
    - agenttalk/hooks/__init__.py
    - agenttalk/hooks/stop_hook.py
    - agenttalk/hooks/session_start_hook.py
    - tests/test_hooks.py

key-decisions:
  - "patch.object on module-level Path constants (PID_FILE, PYTHONW_PATH_FILE, SERVICE_PATH_FILE) using real tmp_path files — WindowsPath instance attributes are read-only and cannot be patched with patch.object"
  - "All hook scripts use sys.stdin.buffer.read().decode('utf-8') — Windows CP1252 default encoding would corrupt non-ASCII characters"
  - "stop_hook_active guard exits before any network call — prevents infinite loop when Claude Code re-fires Stop hook on hook continuations"

patterns-established:
  - "Hook test pattern: _load_hook(name) via importlib.util + _make_stdin(payload) mock + patch module-level Path vars with real tmp_path files"
  - "Hook script pattern: stdlib only, binary stdin read, sys.exit(0) at end, silent fail on all exceptions"

requirements-completed: [HOOK-01, HOOK-02, HOOK-03, HOOK-04]

# Metrics
duration: 8min
completed: 2026-02-26
---

# Plan 03-01: Hook Scripts + Unit Tests Summary

**Two stdlib-only Claude Code hook scripts (stop_hook.py, session_start_hook.py) with 7 passing unit tests for CP1252-safe stdin, stop_hook_active guard, UTF-8 non-ASCII forwarding, and DETACHED_PROCESS service launch**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-26T02:00:00Z
- **Completed:** 2026-02-26T02:08:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- stop_hook.py: reads last_assistant_message from stdin JSON (binary buffer for CP1252 safety), guards stop_hook_active, POSTs to /speak using urllib.request (stdlib only)
- session_start_hook.py: filters on source='startup', checks PID via os.kill(pid, 0), launches service with DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP flags
- tests/test_hooks.py: 7 passing tests covering all HOOK-01..HOOK-04 behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1: create-hook-scripts** - `448f9f4` (feat)
2. **Task 2: write-hook-unit-tests** - `0b1d8fb` (test)

## Files Created/Modified
- `agenttalk/hooks/__init__.py` - Empty package marker
- `agenttalk/hooks/stop_hook.py` - Stop hook: reads stdin, guards active flag, POSTs to /speak
- `agenttalk/hooks/session_start_hook.py` - SessionStart hook: checks PID, launches detached service
- `tests/test_hooks.py` - 7 unit tests for both hooks

## Decisions Made
- `patch.object` on module-level `Path` constants (not instance methods) — WindowsPath instance attributes are read-only in Python 3.13; real `tmp_path` files used instead of mocking path methods
- Tests use `importlib.util.spec_from_file_location` to load hooks directly, avoiding sys.path pollution

## Deviations from Plan

### Auto-fixed Issues

**1. Test approach — WindowsPath attributes read-only**
- **Found during:** Task 2 (write-hook-unit-tests)
- **Issue:** Plan suggested `patch.object(session_hook.PID_FILE, 'exists', ...)` but `WindowsPath` instance attributes are read-only in Python 3.13 — `AttributeError: 'WindowsPath' object attribute 'exists' is read-only`
- **Fix:** Patched module-level constants (`patch.object(session_hook, 'PID_FILE', real_tmp_path_file)`) with actual `tmp_path` files instead of mocking Path methods
- **Files modified:** tests/test_hooks.py
- **Verification:** All 7 tests pass with `python -m pytest tests/test_hooks.py -v`
- **Committed in:** `0b1d8fb` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (test implementation approach adjusted for Python 3.13 WindowsPath constraints)
**Impact on plan:** Fix necessary for test correctness on Python 3.13. No functional changes to hook scripts.

## Issues Encountered
- Python 3.13 `WindowsPath` instance attributes are read-only — `patch.object` on `Path` instance methods fails. Resolved by patching module-level `Path` constants with real temporary files.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Hook scripts ready for use; Plan 03-02 (setup.py) writes `pythonw_path.txt` and `service_path.txt` which session_start_hook.py reads at runtime
- All HOOK-01..HOOK-04 requirements satisfied

---
*Phase: 03-claude-code-hook-integration*
*Completed: 2026-02-26*

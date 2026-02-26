---
phase: 03-claude-code-hook-integration
plan: "02"
subsystem: hooks
tags: [hooks, claude-code, settings.json, json-merge, idempotent, atomic-write]

# Dependency graph
requires:
  - phase: 03-claude-code-hook-integration
    provides: stop_hook.py and session_start_hook.py (hook scripts that setup registers)
provides:
  - register_hooks(): merges AgentTalk hooks into ~/.claude/settings.json idempotently
  - _write_path_files(): writes pythonw_path.txt and service_path.txt to %APPDATA%\AgentTalk\
  - tests/test_setup.py: 8 unit tests covering all HOOK-05 behaviors
affects:
  - 06-installation (register_hooks is the foundation for `agenttalk setup` CLI in Phase 6)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - atomic write: write to .json.tmp then Path.replace() — prevents half-written settings.json
    - idempotency via inner hooks array scan (case-insensitive, 'agenttalk' + filename)
    - BOM-free UTF-8 write (encoding='utf-8' not 'utf-8-sig')
    - patch('agenttalk.setup.AGENTTALK_DIR', tmp_path) for test isolation

key-files:
  created:
    - agenttalk/setup.py
    - tests/test_setup.py

key-decisions:
  - "Append into inner hooks array of FIRST matcher group (not create new top-level matcher group) — preserves Claude Code's hook structure where a single matcher group holds multiple commands"
  - "BOM-free UTF-8 write is critical — 'utf-8-sig' adds \\xef\\xbb\\xbf BOM that causes Claude Code JSON parse failure"
  - "Atomic tmp+replace write prevents race condition where settings.json is partially written if interrupted"
  - "Idempotency check: case-insensitive search for 'agenttalk' AND hook filename — handles mixed-case Windows paths"

patterns-established:
  - "Setup test pattern: patch('agenttalk.setup.AGENTTALK_DIR', tmp_path/appdata) + settings_path=tmp_path/'settings.json' for full isolation"
  - "Atomic JSON write pattern: tmp_path.write_text() + tmp_path.replace(target_path)"

requirements-completed: [HOOK-05]

# Metrics
duration: 7min
completed: 2026-02-26
---

# Plan 03-02: Setup Module + Settings.json Registration Summary

**Idempotent register_hooks() merges AgentTalk Stop/SessionStart entries into ~/.claude/settings.json via atomic BOM-free UTF-8 write, preserving all existing hook entries**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-26T02:08:00Z
- **Completed:** 2026-02-26T02:15:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- agenttalk/setup.py: register_hooks() merges hooks idempotently (no duplicates on second run), preserves existing Stop/SessionStart hooks, atomic write, BOM-free UTF-8
- _write_path_files(): writes pythonw_path.txt + service_path.txt to %APPDATA%\AgentTalk\ for session_start_hook.py runtime use
- tests/test_setup.py: 8 passing tests — all HOOK-05 behaviors verified including BOM absence, JSON validity, idempotency, and existing hook preservation

## Task Commits

Each task was committed atomically:

1. **Task 1: create-setup-module** - `be6e688` (feat)
2. **Task 2: write-setup-unit-tests** - `661ce00` (test)

## Files Created/Modified
- `agenttalk/setup.py` - Setup module with register_hooks(), _write_path_files(), and helpers
- `tests/test_setup.py` - 8 unit tests for setup module

## Decisions Made
- Append into inner hooks array of FIRST matcher group rather than creating new top-level matcher group — matches the user's existing settings.json structure
- BOM-free UTF-8 is critical and tested explicitly — Claude Code JSON parser fails on BOM

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 3 complete: all 5 hook requirements (HOOK-01..HOOK-05) satisfied
- End-to-end integration layer is in place: hook scripts receive Claude Code events, POST to /speak, and setup.py registers them non-destructively
- Phase 4 (system tray, audio ducking) can build on the running service

---
*Phase: 03-claude-code-hook-integration*
*Completed: 2026-02-26*

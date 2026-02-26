---
phase: quick-1
plan: 1
subsystem: speech-control
tags: [speech-mode, semi-auto, slash-commands, stop-hook, config]
dependency_graph:
  requires: []
  provides: [speech_mode-toggle, /agenttalk:speak, /agenttalk:mode, config-speech-mode-option]
  affects: [stop_hook, service-config-api, tts-state, slash-commands]
tech_stack:
  added: []
  patterns: [fail-open-guard, stdlib-only-hook, optional-pydantic-field]
key_files:
  created:
    - agenttalk/commands/speak.md
    - agenttalk/commands/mode.md
  modified:
    - agenttalk/tts_worker.py
    - agenttalk/config_loader.py
    - agenttalk/service.py
    - agenttalk/hooks/stop_hook.py
    - agenttalk/commands/config.md
    - tests/test_hooks.py
decisions:
  - "Fail-open in stop_hook: if GET /config is unreachable, fall through to auto behavior so audio still plays when service is starting up or temporarily unavailable"
  - "2-second timeout on GET /config in stop_hook to avoid blocking Claude Code when service is not running"
metrics:
  duration: 4 min
  completed_date: "2026-02-26"
  tasks_completed: 3
  files_changed: 8
---

# Quick Task 1: Semi-Automatic Speech Mode with /speak Command Summary

**One-liner:** speech_mode toggle ("auto"/"semi-auto") with GET /config guard in stop_hook, /agenttalk:speak and /agenttalk:mode slash commands, and option 6 in /agenttalk:config menu.

## What Was Built

Semi-automatic speech mode gives users control over when audio plays. In `auto` mode (default), the Stop hook speaks every reply as before. In `semi-auto` mode, the Stop hook exits silently and the user can run `/agenttalk:speak` to hear any reply on demand.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | speech_mode to STATE, config, API, stop_hook | 5f53484 | tts_worker.py, config_loader.py, service.py, stop_hook.py |
| 2 | /agenttalk:speak and /agenttalk:mode commands | ba8eff7 | commands/speak.md, commands/mode.md |
| 3 | speech_mode option 6 in /agenttalk:config | fe764c3 | commands/config.md |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] stop_hook tests broke due to double urlopen call**
- **Found during:** Task 3 full verification suite
- **Issue:** `test_stop_hook_non_ascii_payload` asserted `called_once` but the new semi-auto guard makes a GET /config call before the POST /speak call — urlopen is now called twice in the happy path
- **Fix:** Updated `test_stop_hook_non_ascii_payload` to assert `call_count == 2`; updated `test_stop_hook_posts_correct_body` to capture both calls and verify GET /config is first (correct URL + method) and POST /speak is second (correct body)
- **Files modified:** tests/test_hooks.py
- **Commit:** e4c6d25

## Key Decisions

1. **Fail-open guard in stop_hook:** If GET /config fails (URLError, parse error, missing field), the hook falls through to the existing POST /speak behavior. This ensures audio still plays when the service is starting up or temporarily unreachable — only an explicit `"semi-auto"` response suppresses speech.

2. **2-second timeout on GET /config:** Short timeout avoids blocking Claude Code when the AgentTalk service is not running. The TIMEOUT_SECS constant (3s) still applies to the POST /speak call.

## Implementation Notes

- The existing `POST /config` handler body needed no changes — the `STATE[key] = value` loop automatically handles `speech_mode` once the key exists in STATE and the field is in ConfigRequest.
- Both new command files (`speak.md`, `mode.md`) are auto-discovered by `register_commands()` which globs `agenttalk/commands/*.md`.

## Self-Check: PASSED

All created/modified files exist on disk. All task commits verified in git log:
- 5f53484: feat(quick-1): add speech_mode toggle to STATE, config, API, and stop_hook
- ba8eff7: feat(quick-1): add /agenttalk:speak and /agenttalk:mode slash commands
- fe764c3: feat(quick-1): add speech_mode as option 6 in /agenttalk:config menu
- e4c6d25: fix(quick-1): update stop_hook tests to account for GET /config semi-auto guard

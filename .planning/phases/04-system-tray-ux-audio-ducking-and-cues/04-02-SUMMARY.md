---
phase: 04-system-tray-ux-audio-ducking-and-cues
plan: "02"
subsystem: ui
tags: [pystray, pycaw, winsound, system-tray, audio-ducking, cues, config]

requires:
  - phase: 04-01
    provides: "tray.py, audio_duck.py — the standalone modules this plan wires in"
  - phase: 02-fastapi-http-server-and-tts-queue
    provides: "service.py main(), _lifespan(), tts_worker.py STATE/TTS_QUEUE/start_tts_worker"

provides:
  - "service.py: icon.run(setup=_setup) replaces threading.Event().wait() — main thread owned by pystray"
  - "service.py: _setup() sets icon.visible=True, stores _tray_icon, starts HTTP server"
  - "service.py: _on_quit() calls _ducker.unduck() then os._exit(0)"
  - "service.py: atexit.register(_ducker.unduck) for crash safety"
  - "tts_worker.py: ducking, pre/post cues, speaking state flag, icon image swapping"
  - "config_loader.py: load_config() reading %APPDATA%/AgentTalk/config.json"

affects:
  - phase-05
  - service.py
  - tts_worker.py
  - config_loader.py

tech-stack:
  added: [winsound (stdlib), comtypes (via pycaw)]
  patterns:
    - "pystray main thread pattern: icon.run(setup=_setup) blocks main thread; HTTP/TTS started inside setup"
    - "_tray_icon module-level variable bridges _setup callback to async _lifespan"
    - "Best-effort cue: winsound errors log warning, do not propagate"
    - "os._exit(0) for tray Quit: terminates daemon threads immediately"

key-files:
  created:
    - agenttalk/config_loader.py
  modified:
    - agenttalk/service.py
    - agenttalk/tts_worker.py

key-decisions:
  - "_tray_icon module-level bridge: _setup sets it, _lifespan reads it — solves async/sync boundary"
  - "start_tts_worker moved from _lifespan direct call to passing _tray_icon from _setup context"
  - "os._exit(0) in _on_quit: sys.exit raises SystemExit that daemon threads can swallow"
  - "atexit handler for unduck: covers crashes and SIGTERM even before icon.stop()"
  - "winsound.SND_FILENAME (synchronous): cue must complete before TTS begins to avoid overlap"
  - "Muted batch: entire batch skipped before duck/cue — no ducking, no cues, no synthesis"

patterns-established:
  - "pystray pattern: build Icon → pass to icon.run(setup=fn) → fn sets icon.visible=True and starts services"
  - "Icon reference flow: main() → _setup(icon) → _tray_icon → _lifespan → start_tts_worker(..., icon=_tray_icon)"
  - "try/finally in TTS worker ensures task_done() and speaking=False even on error"

requirements-completed: [SVC-04, TRAY-03, CUE-01, CUE-02, CUE-03, CUE-04]

duration: 15min
completed: 2026-02-26
---

# Plan 04-02: Service Wiring Summary

**pystray main-thread ownership wired into service.py; TTS worker gains ducking, pre/post cues, speaking state, and icon swap; config_loader.py reads cue paths from config.json**

## Performance

- **Duration:** 15 min
- **Started:** 2026-02-26T02:40:00Z
- **Completed:** 2026-02-26T02:55:00Z
- **Tasks:** 3
- **Files modified:** 3 (1 new, 2 updated)

## Accomplishments
- Replaced `threading.Event().wait()` with `icon.run(setup=_setup)` — pystray owns main thread (SVC-04)
- `_setup()` callback sets `icon.visible=True`, stores `_tray_icon` reference, starts HTTP server
- `_lifespan` passes `_tray_icon` to `start_tts_worker(_kokoro_engine, icon=_tray_icon)` after Kokoro loads — solving the async/sync race condition cleanly
- TTS worker updated with full Phase 4 sequence: mute → speaking=True → icon swap → pre-cue → duck → synthesize → unduck → post-cue → finally: speaking=False, icon swap, task_done
- `config_loader.py` created: reads `%APPDATA%/AgentTalk/config.json`, returns {} on missing/invalid file, never raises
- `atexit.register(_ducker.unduck)` registered for crash safety — volumes restored even on abnormal exit
- All 40 tests pass (regression clean)

## Task Commits

1. **Task 2: Update tts_worker.py** - `6904bba` (feat)
2. **Task 1+3: Create config_loader.py + update service.py** - `f774865` (feat)

Note: Tasks 1 and 3 were committed together as they are tightly coupled (service.py imports config_loader).

## Files Created/Modified
- `agenttalk/config_loader.py` - load_config() reading %APPDATA%/AgentTalk/config.json (CUE-04)
- `agenttalk/service.py` - icon.run integration, _setup, _on_quit, atexit, config seeding (SVC-04)
- `agenttalk/tts_worker.py` - ducking, cues, speaking state, icon swap, expanded start_tts_worker

## Decisions Made
- Tasks 1 and 3 implemented together: service.py imports config_loader; both needed at once
- `_tray_icon` module-level bridge variable: avoids threading complexity of passing icon through function calls across async/sync boundary
- `os._exit(0)` in `_on_quit`: `sys.exit()` raises `SystemExit` which uvicorn's daemon thread can catch and swallow; `os._exit(0)` terminates immediately
- TTS worker muted path: entire batch skipped (not per-sentence) — cleaner and avoids unnecessary ducking/cue overhead
- Tasks 1 and 3 committed together since service.py cannot import config_loader before config_loader exists

## Deviations from Plan
None - plan executed exactly as written. The ordering (Task 2 before Tasks 1+3) was chosen so service.py could import _ducker from tts_worker.

## Issues Encountered
None — all imports resolved cleanly. No circular imports despite the mutual dependency between service.py and tts_worker.py (tts_worker doesn't import service).

## User Setup Required
None - no external service configuration required.
The tray live test (step 7 in plan verification) requires running the full service with Kokoro models present — this is a manual integration test, not required for plan completion.

## Next Phase Readiness
- Phase 5 can import `load_config` from `agenttalk.config_loader` and add `save_config` for write support
- Phase 5 slash command can write `pre_cue_path`/`post_cue_path` to config.json
- All Phase 4 requirements closed: SVC-04, TRAY-01–06, AUDIO-07, CUE-01–04
- Service is ready for tray icon testing once Kokoro models are present

---
*Phase: 04-system-tray-ux-audio-ducking-and-cues*
*Completed: 2026-02-26*

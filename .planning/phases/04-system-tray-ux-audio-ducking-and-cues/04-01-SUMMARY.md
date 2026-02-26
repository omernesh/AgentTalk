---
phase: 04-system-tray-ux-audio-ducking-and-cues
plan: "01"
subsystem: ui
tags: [pystray, pycaw, com, windows, system-tray, audio-ducking, pillow]

requires:
  - phase: 02-fastapi-http-server-and-tts-queue
    provides: STATE dict, TTS pipeline — audio_duck.py integrates with the same pipeline

provides:
  - "agenttalk/tray.py: build_tray_icon(), create_image_idle(), create_image_speaking(), KOKORO_VOICES"
  - "agenttalk/audio_duck.py: AudioDucker class with duck(), unduck(), is_ducked"

affects:
  - 04-02-wiring
  - service.py (icon.run integration)
  - tts_worker.py (duck/unduck integration)

tech-stack:
  added: [pystray>=0.19.5, pycaw>=20251023, comtypes]
  patterns:
    - Tray icon builds Icon object without calling run() — deferred to service.py setup callback
    - COM initialization per-call pattern for non-main thread pycaw access
    - Best-effort audio ducking — pycaw errors log warning, do not propagate

key-files:
  created:
    - agenttalk/tray.py
    - agenttalk/audio_duck.py
  modified:
    - requirements.txt

key-decisions:
  - "pystray GIL compatibility tested on current Python — passed (no crash), Python 3.11 not needed"
  - "on_quit injected as callable parameter so tray.py stays decoupled from audio_duck.py"
  - "Disabled menu item uses lambda no-op action (not None) to avoid pystray TypeError (pitfall #3)"
  - "unduck() early-returns when nothing ducked to skip unnecessary COM init"
  - "Session keyed by process name — sessions created/destroyed between duck/unduck accepted as edge case"

patterns-established:
  - "64px minimum icon size: smaller sizes cause WinError 0 in pystray LoadImage"
  - "COM pattern: CoInitialize/CoUninitialize wrapping every pycaw call in daemon threads"
  - "Best-effort pattern: pycaw errors caught, logged as warning, never re-raised"

requirements-completed: [TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05, TRAY-06, AUDIO-07]

duration: 10min
completed: 2026-02-26
---

# Plan 04-01: System Tray Modules Summary

**pystray tray icon with dynamic menu and pycaw COM-safe AudioDucker — both self-contained modules ready for Plan 04-02 integration**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-26T02:30:00Z
- **Completed:** 2026-02-26T02:40:00Z
- **Tasks:** 2
- **Files modified:** 3 (2 new, 1 updated)

## Accomplishments
- Created `agenttalk/tray.py` with `create_image_idle()` (64x64 blue circle), `create_image_speaking()` (64x64 orange circle), and `build_tray_icon(state, on_quit)` returning a full-featured pystray.Icon with Mute, Voice submenu, Active info item, and Quit
- Created `agenttalk/audio_duck.py` with `AudioDucker` class implementing COM-safe duck()/unduck() that lowers other Windows audio sessions to 50% during TTS playback and restores them after
- pystray GIL compatibility test passed on current Python version — Python 3.11 upgrade not required
- All 33 pre-existing tests continue to pass (regression clean)

## Task Commits

1. **Task 1: Create agenttalk/tray.py** - `be7f8ae` (feat)
2. **Task 2: Create agenttalk/audio_duck.py** - `22c3024` (feat)

## Files Created/Modified
- `agenttalk/tray.py` - pystray icon module with create_image_idle/speaking and build_tray_icon
- `agenttalk/audio_duck.py` - AudioDucker class with COM-safe duck/unduck/is_ducked
- `requirements.txt` - Added pystray>=0.19.5 and pycaw>=20251023

## Decisions Made
- pystray compatibility test run first: `icon.run(setup=lambda ic: ic.stop())` printed "pystray OK" — no GIL crash on current Python. Proceeded without Python 3.11 upgrade.
- `on_quit` is injected as a callable parameter (not imported) to keep tray.py and audio_duck.py fully decoupled
- Disabled menu item uses `lambda icon, item: None` instead of `action=None` to avoid pystray TypeError pitfall
- `unduck()` early-returns if `_saved` is empty to avoid unnecessary COM initialization overhead

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None — pystray, pycaw, and comtypes all installed cleanly and imported without issues.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 04-02 can now import `build_tray_icon`, `create_image_idle`, `create_image_speaking` from `agenttalk.tray`
- Plan 04-02 can now import `AudioDucker` from `agenttalk.audio_duck`
- Both modules fully tested in isolation via import checks
- No blockers — all TRAY-* and AUDIO-07 interfaces are ready for wiring

---
*Phase: 04-system-tray-ux-audio-ducking-and-cues*
*Completed: 2026-02-26*

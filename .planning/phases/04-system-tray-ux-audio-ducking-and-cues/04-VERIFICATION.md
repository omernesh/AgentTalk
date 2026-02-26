---
phase: "04"
phase_name: system-tray-ux-audio-ducking-and-cues
status: passed
verified: 2026-02-26
---

# Phase 04: System Tray UX, Audio Ducking, and Cues — Verification

## Phase Goal

The service shows a visible tray icon while running; the icon changes when speaking; right-clicking reveals mute, voice selection, and quit; other audio streams duck during TTS; and optional pre/post audio cues play around each utterance.

## Score: 12/12 must-haves verified

## Requirement Verification

### SVC-04: pystray tray icon runs on main thread
**Status: PASSED**
- `threading.Event().wait()` is absent from service.py (only appears in a comment referencing the Phase 1 approach)
- `icon.run(setup=_setup)` is present at line 386 of service.py
- Verified: `grep -n "icon.run" agenttalk/service.py` → shows `icon.run(setup=_setup)`

### TRAY-01: Service icon visible in system tray
**Status: PASSED (code verified; live visual requires running service)**
- `_setup()` callback sets `icon.visible = True` as first operation (before HTTP server starts)
- Build pattern is correct: `icon = build_tray_icon(state=STATE, on_quit=_on_quit)` → `icon.run(setup=_setup)` → `_setup` sets `icon.visible=True`
- icon starts hidden by default in pystray; visible=True in setup is the correct pattern

### TRAY-02: Mute/Unmute toggle with checkmark
**Status: PASSED**
- `pystray.MenuItem("Mute", _toggle_mute, checked=lambda item: state["muted"])` in tray.py
- `_toggle_mute` flips `state["muted"]` and calls `icon.update_menu()`
- Checkmark reflects live state

### TRAY-03: Tray icon changes while speaking
**Status: PASSED (code verified; live visual requires running service)**
- `_icon_ref.icon = create_image_speaking()` called after `STATE["speaking"] = True` when TTS starts
- `_icon_ref.icon = create_image_idle()` called in `finally` block when TTS finishes
- `start_tts_worker(kokoro_engine, icon=_tray_icon)` passes icon reference through

### TRAY-04: Voice submenu with all Kokoro voices
**Status: PASSED**
- `KOKORO_VOICES` has 11 entries: af_heart, af_bella, af_nicole, af_sarah, af_sky, am_adam, am_michael, bf_emma, bf_isabella, bm_george, bm_lewis
- Voice submenu uses `radio=True` and `checked=lambda item, v=voice: state["voice"] == v`
- `_set_voice(voice)` updates `state["voice"]` and calls `icon.update_menu()`

### TRAY-05: Quit cleanly shuts down service
**Status: PASSED**
- `_on_quit()` calls `_ducker.unduck()` then `os._exit(0)`
- `atexit.register(_ducker.unduck)` handles crash/SIGTERM path
- `os._exit(0)` vs `sys.exit()`: correct choice — `sys.exit()` raises `SystemExit` which daemon threads can swallow

### TRAY-06: Active voice as disabled info item
**Status: PASSED**
- `pystray.MenuItem(lambda item: f'Active: {state["voice"]}', lambda icon, item: None, enabled=False)` in tray.py
- Dynamic title reflects current voice
- Action is `lambda icon, item: None` (not `None`) — avoids pystray TypeError pitfall

### AUDIO-07: Audio ducking during TTS
**Status: PASSED (code verified; live audio requires running service with other audio playing)**
- `AudioDucker.duck()` enumerates sessions, skips python.exe/pythonw.exe, saves volumes, sets to 50%
- `AudioDucker.unduck()` restores saved volumes
- COM initialized per-call via `comtypes.CoInitialize/CoUninitialize` (daemon thread safe)
- Both methods wrapped in `try/except Exception` — pycaw errors log warning, do not crash TTS worker
- `_ducker.duck()` called before synthesis loop, `_ducker.unduck()` after all sentences finish
- Error path: `if _ducker.is_ducked: _ducker.unduck()` prevents stuck volumes on exception

### CUE-01: Pre-speech audio cue
**Status: PASSED**
- `play_cue(STATE.get("pre_cue_path"))` called after icon swap and before `_ducker.duck()`
- `winsound.SND_FILENAME` (synchronous) — cue completes before TTS begins
- Timing: pre-cue plays before ducking so cue volume is not reduced

### CUE-02: Post-speech audio cue
**Status: PASSED**
- `play_cue(STATE.get("post_cue_path"))` called after `_ducker.unduck()` and after all sentences finish
- `winsound.SND_FILENAME` (synchronous) — not async

### CUE-03: Optional cues (no sound when unset)
**Status: PASSED**
- `play_cue(None)` returns immediately with no winsound call
- `play_cue('')` returns immediately with no winsound call
- `STATE["pre_cue_path"] = None` and `STATE["post_cue_path"] = None` by default
- Verified: `play_cue(None); play_cue('')` executes silently

### CUE-04: Cue paths configurable via config.json
**Status: PASSED**
- `agenttalk/config_loader.py` exports `load_config()` reading `%APPDATA%/AgentTalk/config.json`
- Returns `{}` on missing file or invalid JSON — never raises
- `service.py` calls `load_config()` at startup, seeds `STATE["pre_cue_path"]` and `STATE["post_cue_path"]`
- Config is loaded BEFORE `icon.run()` — cue paths in STATE before any TTS request served
- Config write support deferred to Phase 5 (slash commands)

## Automated Test Results

```
40 passed in 0.65s
```

All 40 tests pass including 33 pre-existing tests (preprocessor, setup, hooks) and regression suite.

## What Was Built

- `agenttalk/tray.py`: pystray icon module — `build_tray_icon()`, `create_image_idle()`, `create_image_speaking()`, `KOKORO_VOICES`
- `agenttalk/audio_duck.py`: `AudioDucker` class with COM-safe `duck()`/`unduck()`/`is_ducked`
- `agenttalk/config_loader.py`: `load_config()` reading `%APPDATA%/AgentTalk/config.json`
- `agenttalk/service.py`: Updated `main()` with `icon.run(setup=_setup)`, `_on_quit`, `atexit`, config seeding
- `agenttalk/tts_worker.py`: Updated with ducking, cues, speaking state, icon swap, expanded `start_tts_worker`
- `requirements.txt`: Added `pystray>=0.19.5` and `pycaw>=20251023`

## Human Verification Items

The following require running the live service (Kokoro models must be present):

1. **TRAY-01 live**: `python agenttalk/service.py` → AgentTalk icon appears in Windows system tray
2. **TRAY-02 live**: Right-click tray → Mute (checkmark), Voice submenu, Active: af_heart, Quit
3. **TRAY-03 live**: Send `curl -X POST http://127.0.0.1:5050/speak -d '{"text":"Test."}'` → icon turns orange during speech
4. **AUDIO-07 live**: With Spotify/browser audio playing → volume drops to 50% during TTS, restores after
5. **TRAY-05 live**: Click Quit → service terminates, icon disappears

These items are blocked by Kokoro model availability, not code quality. All code paths are verified through static analysis and import checks.

## Self-Check: PASSED

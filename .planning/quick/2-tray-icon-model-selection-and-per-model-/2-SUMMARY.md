---
phase: quick
plan: 2
subsystem: tray
tags: [tray, pystray, model-selection, piper, kokoro, voice-menu]
dependency_graph:
  requires: []
  provides: [tray-model-submenu, context-aware-voice-submenu, on-config-change-callback]
  affects: [agenttalk/tray.py, agenttalk/service.py]
tech_stack:
  added: []
  patterns:
    - pystray callable Menu generator for dynamic submenus
    - factory closure pattern (_set_model, _set_piper_voice) mirroring existing _set_voice
    - on_config_change callback with None default for backward-compatible call sites
key_files:
  created: []
  modified:
    - agenttalk/tray.py
    - agenttalk/service.py
decisions:
  - _voice_items defined as nested function inside build_tray_icon to capture on_config_change closure
  - _piper_dir() at module level (no state dependency, only reads APPDATA env var)
  - pystray.Menu(_voice_items) called without lambda wrapper; pystray accepts callable directly
  - on_config_change defaults to None so existing service.py call sites without it compile unchanged
metrics:
  duration: 8 min
  completed: "2026-02-26"
  tasks_completed: 2
  files_modified: 2
---

# Quick Task 2: Tray Icon Model Selection and Per-Model Voice Submenu Summary

**One-liner:** Model submenu (kokoro/piper radio items) added to tray; Voice submenu is now dynamic, showing Kokoro voice IDs or scanned Piper .onnx stems based on active engine, with on_config_change wired to persist selections.

## What Was Built

### Task 1: Model Submenu and on_config_change Callback

Added a Model submenu to the tray right-click menu positioned between the existing Mute toggle and the Voice submenu.

Changes to `agenttalk/tray.py`:
- Added `os` and `pathlib.Path` imports.
- Added `on_config_change: Callable[[], None] | None = None` parameter to `build_tray_icon()` with full docstring documentation.
- Added `_set_model(model)` factory function (same closure pattern as `_set_voice`). Mutates `state["model"]` and fires `on_config_change` then `icon.update_menu()`.
- Added Model submenu with `kokoro` and `piper` as radio items. `checked` lambda reads `state["model"]` at render time.
- Updated menu structure docstring to reflect the new 6-item ordering.

Changes to `agenttalk/service.py`:
- Added `_on_config_change()` function that calls `save_config(STATE)` with OSError guard.
- Updated `build_tray_icon()` call to pass `on_config_change=_on_config_change`.

### Task 2: Context-Aware Voice Submenu

Replaced the static Kokoro-only Voice submenu with a dynamic generator that inspects `state["model"]` at menu render time.

Changes to `agenttalk/tray.py`:
- Added `_piper_dir()` module-level helper returning `%APPDATA%/AgentTalk/models/piper`.
- Added `_set_piper_voice(stem, full_path)` factory inside `build_tray_icon` — sets `piper_model_path`, switches `model` to `piper`, calls `on_config_change`.
- Added `_voice_items()` generator (nested inside `build_tray_icon` to close over `on_config_change`, `_set_voice`, `_set_piper_voice`):
  - When `model == "piper"`: scans `_piper_dir()` for `*.onnx` files, yields radio items per stem. If none found yields a disabled "No Piper models found" item.
  - When `model == "kokoro"` (default): yields radio items for each `KOKORO_VOICES` entry.
- Updated Voice submenu to use `pystray.Menu(_voice_items)` (callable, evaluated at render time).
- Updated Active info label lambda to show `.stem` of `piper_model_path` when piper is active and a path is set, otherwise shows `state["voice"]`.

## Final Menu Structure

```
1. Mute          — checkmark toggle (state["muted"])
2. Model         — submenu: kokoro / piper radio buttons (state["model"])
3. Voice         — submenu: KOKORO_VOICES (kokoro) | .onnx stems (piper)
4. Active: ...   — read-only label (stem for piper, voice ID for kokoro)
5. ---           — separator
6. Quit          — calls on_quit() then icon.stop()
```

## Verification Results

All three plan verification commands passed:

```
python -c "from agenttalk.tray import build_tray_icon; b = build_tray_icon({'muted': False, 'voice': 'af_heart', 'model': 'kokoro', 'piper_model_path': None, 'speaking': False}); print('ok')"
# => ok

python -c "from agenttalk.tray import build_tray_icon; b = build_tray_icon({'muted': False, 'voice': 'af_heart', 'model': 'piper', 'piper_model_path': None, 'speaking': False}); print('ok')"
# => ok  (graceful "No Piper models found" item, no crash)

python -c "from agenttalk import service; print('service import ok')"
# => service import ok
```

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash    | Description                                             |
|---------|---------------------------------------------------------|
| 0e7ab0f | feat(quick-2): add Model submenu and context-aware Voice submenu to tray |

## Self-Check: PASSED

- `agenttalk/tray.py` — exists and imports cleanly
- `agenttalk/service.py` — exists and imports cleanly
- Commit `0e7ab0f` — present in git log

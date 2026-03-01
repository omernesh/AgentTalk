---
phase: quick-8
plan: 8
subsystem: agenttalk/tts
tags: [hebrew-tts, tts-engine, piper, docker, onnx, config]
dependency_graph:
  requires: [tts_worker, piper_engine, config_loader, service]
  provides: [hebrewpiper_engine, lightblue_engine, hebrew-voices-endpoint]
  affects: [tts_worker._get_active_engine, service.ConfigRequest, config_loader.save_config]
tech_stack:
  added: [Light-BlueTTS (optional, hebrew_inference_helper), PiperStream (Docker REST API)]
  patterns: [lazy-engine-loading, engine-dispatch-by-model-name, atomic-config-persistence]
key_files:
  created:
    - agenttalk/hebrewpiper_engine.py
    - agenttalk/lightblue_engine.py
    - docs/hebrew-tts-setup.md
  modified:
    - agenttalk/tts_worker.py
    - agenttalk/service.py
    - agenttalk/config_loader.py
    - agenttalk/commands/model.md
decisions:
  - HebrewPiperEngine uses /synthesize/audio (complete WAV) not /synthesize/stream — simpler parsing with wave module
  - LightBlueTTSEngine defers all heavy imports to __init__ so module imports clean without torch
  - Speed changes in LightBlueTTSEngine trigger engine reload (log warning) — speed is baked into TTSConfig
  - /hebrew-voices scans lightblue_voice_path parent directory for *.json — no hardcoded voice list
metrics:
  duration: 5 min
  completed: "2026-03-01"
  tasks_completed: 3
  files_created: 3
  files_modified: 4
---

# Quick Task 8: Hebrew TTS Support Summary

Hebrew TTS added to AgentTalk via two new pluggable engines: HebrewPiperEngine (Docker REST API, simpler setup) and LightBlueTTSEngine (local Python inference, better quality, optional torch dependency).

## What Was Built

### New Engine Files

**agenttalk/hebrewpiper_engine.py** — `HebrewPiperEngine`
- Wraps the PiperStream REST API at `POST /synthesize/audio`
- No new Python deps (uses existing `requests`)
- Lazy network: `__init__` does no network calls; first call happens in `create()`
- Speed mapped to `length_scale = 1/speed` (identical to PiperEngine)
- Returns `(np.ndarray[float32], 22050)` — WAV header parsed with `wave` module

**agenttalk/lightblue_engine.py** — `LightBlueTTSEngine`
- Wraps Light-BlueTTS `HebrewTTS.infer()` for local Hebrew inference
- All heavy imports deferred to `__init__` — module imports cleanly without torch
- Speed change detection: reloads engine with new TTSConfig if speed differs (logs warning)
- Returns `(np.ndarray[float32], 44100)` — Light-BlueTTS always outputs 44100 Hz

### Updated Files

**agenttalk/tts_worker.py**
- `STATE` dict: 5 new keys (`hebrewpiper_host`, `hebrewpiper_voice`, `lightblue_onnx_dir`, `lightblue_phonikud_path`, `lightblue_voice_path`)
- Engine cache: `_hebrewpiper_engine/_hebrewpiper_loaded_key` and `_lightblue_engine/_lightblue_loaded_key`
- `_get_active_engine()`: dispatches `model == "hebrewpiper"` and `model == "lightblue"` to new engines

**agenttalk/service.py**
- `ConfigRequest`: extended model Literal to `["kokoro", "piper", "lightblue", "hebrewpiper"]`
- New optional fields: `hebrewpiper_host`, `hebrewpiper_voice`, `lightblue_onnx_dir`, `lightblue_phonikud_path`, `lightblue_voice_path`
- `GET /config`: includes all 5 new Hebrew keys in response
- `GET /hebrew-voices`: new endpoint returning `{"hebrewpiper": ["male", "female"], "lightblue": [...]}`
- Startup restore loop: extended to restore all 5 Hebrew keys from config.json

**agenttalk/config_loader.py**
- `save_config()`: persists all 5 Hebrew keys (14 total fields, up from 9)
- Docstring updated: "Persists all 14 settings fields"

**agenttalk/commands/model.md**
- Resolution clause updated: "resolve it to one of: kokoro, piper, lightblue, hebrewpiper"
- Pick list: expanded from 2 to 4 options with descriptions
- Examples added for `hebrewpiper` and `lightblue` model switches

**docs/hebrew-tts-setup.md**
- Comparison table: setup effort, Docker, GPU, voices, sample rate, quality
- Option A (HebrewPiper): full Docker setup + curl test commands
- Option B (Light-BlueTTS): pip install, PYTHONPATH, model download, configure steps
- Switching back to English section
- Troubleshooting section: Docker, ImportError, onnx_dir not configured, encoding issues

## Config Keys Added

| Key                     | Default                    | Description                              |
|-------------------------|----------------------------|------------------------------------------|
| `hebrewpiper_host`      | `http://localhost:8000`    | PiperStream Docker service base URL      |
| `hebrewpiper_voice`     | `female`                   | PiperStream voice: "male" or "female"   |
| `lightblue_onnx_dir`    | `None`                     | Path to onnx_models/ directory           |
| `lightblue_phonikud_path` | `None`                   | Path to phonikud-1.0.onnx               |
| `lightblue_voice_path`  | `None`                     | Path to a voices/*.json style file       |

## API Changes

- `POST /config`: accepts `model: "lightblue" | "hebrewpiper"` + 5 Hebrew config keys
- `GET /config`: returns all 5 Hebrew config keys in response
- `GET /hebrew-voices`: new endpoint (returns static hebrewpiper list + scanned lightblue voices)

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit  | Description                                               |
|------|---------|-----------------------------------------------------------|
| 1    | 8ba4136 | feat(quick-8): add HebrewPiperEngine and LightBlueTTSEngine wrappers |
| 2    | 9e78038 | feat(quick-8): wire Hebrew engines into tts_worker, service, and config_loader |
| 3    | ece02cf | docs(quick-8): add Hebrew TTS setup guide for PiperStream and Light-BlueTTS |

## Self-Check: PASSED

- agenttalk/hebrewpiper_engine.py: FOUND
- agenttalk/lightblue_engine.py: FOUND
- docs/hebrew-tts-setup.md: FOUND
- Commit 8ba4136: FOUND
- Commit 9e78038: FOUND
- Commit ece02cf: FOUND
- STATE['hebrewpiper_host'] default verified: OK
- All imports verified: OK

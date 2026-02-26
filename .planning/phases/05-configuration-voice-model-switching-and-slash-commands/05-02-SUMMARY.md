---
plan: 05-02
status: complete
completed: 2026-02-26
requirements: TTS-04, CMD-04
---

# Plan 05-02: Piper Engine Wrapper and Engine Dispatcher

## What Was Built

Created the PiperEngine class (Kokoro-compatible interface) and wired it into tts_worker via a lazy-loading engine dispatcher. Runtime engine switching now works without service restart.

## Tasks Completed

| Task | Status | Commits |
|------|--------|---------|
| Task 1: Create agenttalk/piper_engine.py — PiperEngine wrapper | Complete | feat(05-02): add PiperEngine wrapper... |
| Task 2: Add _get_active_engine() dispatcher and _piper_engine to tts_worker | Complete | feat(05-02): add _get_active_engine dispatcher... |

## Key Files

### Created/Modified
- `agenttalk/piper_engine.py` — New file. PiperEngine class with Kokoro-compatible `create(text, voice, speed, lang) -> (float32 ndarray, int sample_rate)` interface. Deferred imports of PiperVoice/SynthesisConfig inside methods; module-level import safe without piper-tts installed. Speed maps to `length_scale=1.0/speed`, clamped at 0.1.
- `agenttalk/tts_worker.py` — Added `_piper_engine = None` module-level variable. Added `_get_active_engine(kokoro)` function. Replaced direct `kokoro_engine.create()` call in synthesis loop with `_get_active_engine(kokoro_engine).create()`.

## Self-Check: PASSED

- piper_engine.py imports cleanly without piper-tts installed ✓
- PiperEngine class importable, create() has text/voice/speed/lang params ✓
- _piper_engine is None at module startup ✓
- _get_active_engine returns kokoro sentinel when STATE['model'] == 'kokoro' ✓
- _get_active_engine raises RuntimeError when model == 'piper' and piper_model_path is None ✓
- Direct kokoro_engine.create() call replaced in synthesis loop ✓
- sd.play() uses returned rate (not hardcoded) — Piper 22050 Hz honoured ✓
- All 40 existing tests pass (no regression) ✓

## Decisions

- Deferred import of PiperVoice inside `__init__` (not at module level) — prevents 2-5s startup cost when Kokoro is active
- `_piper_engine` is NOT reset when switching back to 'kokoro' — once loaded, reused for free on next switch
- RuntimeError from `_get_active_engine` is caught by the existing exception handler in `_tts_worker()` and logged — batch skipped, worker continues

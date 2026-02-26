---
plan: 05-01
status: complete
completed: 2026-02-26
requirements: CFG-01, CFG-02, CFG-03, CMD-02, CMD-03
---

# Plan 05-01: Config Persistence and Service Control Endpoints

## What Was Built

Added config write support (save_config), engine-switching STATE keys, and two new FastAPI endpoints (/config, /stop) to close the Phase 5 service-side requirements.

## Tasks Completed

| Task | Status | Commits |
|------|--------|---------|
| Task 1: Add save_config() and _CONFIG_LOCK to config_loader.py | Complete | feat(05-01): add save_config()... |
| Task 2: Extend STATE, add /config + /stop, fix startup hydration | Complete | feat(05-01): add STATE engine keys... |

## Key Files

### Created/Modified
- `agenttalk/config_loader.py` — Added `threading` import, `_CONFIG_LOCK`, and `save_config(state)`. Atomic write via `.json.tmp` + `Path.replace()`. Thread-safe via module-level lock.
- `agenttalk/tts_worker.py` — Added `STATE['model']` (default `'kokoro'`) and `STATE['piper_model_path']` (default `None`) for engine switching.
- `agenttalk/service.py` — Added `Optional` import, `save_config` import, `ConfigRequest` Pydantic model, `POST /config` endpoint, `POST /stop` endpoint, replaced Phase 4 partial hydration with full 7-key for-loop.

## Self-Check: PASSED

- save_config() exists in config_loader, exports confirmed ✓
- _CONFIG_LOCK is threading.Lock() instance ✓
- Round-trip save/load test: all 7 CFG-02 fields persist correctly ✓
- .json.tmp cleaned up after atomic write ✓
- STATE['model'] == 'kokoro' (default) ✓
- STATE['piper_model_path'] is None (default) ✓
- /config and /stop routes registered in FastAPI app ✓
- service.py startup uses 7-key for-loop (old Phase 4 partial block removed) ✓
- All 40 existing tests pass (no regression) ✓

## Decisions

- Used `Path.with_suffix('.json.tmp')` for temp file — same filesystem as destination, guarantees atomic replace on Windows
- /stop uses 0.1s delayed daemon thread so HTTP response is delivered before process exits (avoids curl exit code 52/56)
- Full 7-key hydration loop replaces the Phase 4 cue-only block — simpler and covers all CFG-02 fields

## Interfaces Produced for Wave 2

Plans 05-02 and 05-03 can now rely on:
- `save_config(STATE)` callable from service.py /config handler (already wired)
- `STATE['model']` and `STATE['piper_model_path']` present in tts_worker STATE
- `POST /config` endpoint accepting `{"model": "piper"}` to trigger engine switch

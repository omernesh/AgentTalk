---
phase: 02-fastapi-http-server-and-tts-queue
plan: 02
subsystem: audio
tags: [tts, queue, threading, sounddevice, fastapi, wasapi, kokoro, pydantic]

# Dependency graph
requires:
  - phase: 01-service-skeleton-and-core-audio
    provides: agenttalk/service.py with FastAPI app, Kokoro engine, _lifespan, play_audio
  - phase: 02-01
    provides: agenttalk/preprocessor.py with preprocess() function

provides:
  - "agenttalk/tts_worker.py: TTS_QUEUE (threading.Queue maxsize=3), STATE dict, start_tts_worker(), _tts_worker()"
  - "agenttalk/service.py: POST /speak endpoint, WASAPI-conditional _configure_audio(), TTS worker started in lifespan"
  - "Full HTTP → preprocess → queue → synthesis → playback pipeline operational"

affects:
  - Phase 3 (Claude Code hook wiring — will POST to /speak)
  - Phase 4 (mute toggle will flip STATE['muted'])
  - Phase 5 (volume/speed control will update STATE['volume']/STATE['speed'])

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "threading.Queue(maxsize=3) as thread-safe bridge between async FastAPI handler and blocking daemon thread"
    - "STATE dict read at synthesis time — runtime volume/speed changes take effect on next sentence"
    - "Conditional WASAPI detection: query host API → apply WasapiSettings only if WASAPI (not MME/DirectSound)"
    - "Pydantic BaseModel for POST body validation (SpeakRequest)"

key-files:
  created:
    - agenttalk/tts_worker.py
  modified:
    - agenttalk/service.py

key-decisions:
  - "threading.Queue not asyncio.Queue: asyncio.Queue is not thread-safe across async handler ↔ blocking thread boundary"
  - "Kokoro.create() runs only in _tts_worker(): CPU-blocking synthesis must not run in async event loop"
  - "WasapiSettings applied conditionally: detect host API at startup, only WASAPI devices get auto_convert=True"
  - "start_tts_worker() called in _lifespan after is_ready=True: worker needs Kokoro engine warmed up before consuming queue"

requirements-completed:
  - SVC-02
  - SVC-03
  - AUDIO-01
  - AUDIO-04
  - AUDIO-05
  - AUDIO-06
  - TTS-05

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 02 Plan 02: TTS Worker and /speak Endpoint Summary

**threading.Queue(maxsize=3) TTS daemon thread + POST /speak endpoint completing full HTTP-to-audio pipeline with WASAPI-conditional audio configuration**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T01:46:02Z
- **Completed:** 2026-02-26T01:48:33Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `agenttalk/tts_worker.py`: bounded queue (maxsize=3), STATE dict for runtime volume/speed/voice/mute, daemon TTS thread synthesizing sentences via Kokoro and playing via sounddevice
- Updated `agenttalk/service.py`: WASAPI-conditional `_configure_audio()`, TTS worker startup in lifespan, `SpeakRequest` Pydantic model, `POST /speak` endpoint with 202/200/429/503 responses
- All preprocessor tests still passing (25/25) — no regression
- Full HTTP → preprocess → queue → synthesis → playback pipeline wired

## Task Commits

1. **Task 1: tts_worker.py** - `12e610a` (feat)
   - TTS_QUEUE, STATE, start_tts_worker(), _tts_worker()
2. **Task 2: service.py /speak + WASAPI** - `6a22e92` (feat)
   - _configure_audio() WASAPI detection, SpeakRequest, _lifespan extension, POST /speak

## Files Created/Modified

- `agenttalk/tts_worker.py` — TTS queue, state dict, daemon worker thread
- `agenttalk/service.py` — Added /speak endpoint, WASAPI detection, TTS worker startup

## Decisions Made

1. **threading.Queue (not asyncio.Queue)**: asyncio.Queue is not thread-safe and cannot bridge async FastAPI handlers with blocking threading.Thread worker. Research pitfall #1 explicitly called out.

2. **Kokoro.create() only in _tts_worker()**: Blocking CPU synthesis must never run in the async event loop. Research pitfall #2.

3. **Conditional WASAPI detection**: Phase 1 empirical finding (WasapiSettings causes PaErrorCode -9984 on MME) is respected. Phase 2 queries host API at startup and only applies WasapiSettings when the output device is WASAPI.

4. **Worker started after Kokoro warmup**: `start_tts_worker(_kokoro_engine)` is called after `is_ready = True` in `_lifespan()` — ensures the worker has a fully warmed-up engine reference before it begins consuming queue items.

## Deviations from Plan

None — plan executed exactly as written. All patterns from the `<interfaces>` block were used verbatim. The sounddevice==0.5.5 package was not installed in the active Python environment (it's pinned in requirements.txt but the environment hadn't installed it). Installed via pip as a Rule 3 (blocking) auto-fix.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] sounddevice not installed in active Python environment**
- **Found during:** Task 1 verification (import check failed)
- **Issue:** `import sounddevice` raised ModuleNotFoundError despite being in requirements.txt
- **Fix:** `pip install sounddevice==0.5.5`
- **Files modified:** None (environment fix only)
- **Verification:** `from agenttalk.tts_worker import TTS_QUEUE, STATE, start_tts_worker` prints correctly

---

**Total deviations:** 1 auto-fixed (Rule 3 - Blocking: missing installed dependency)
**Impact on plan:** Dependency install is environment maintenance, not a code change. No scope creep.

## Issues Encountered

None — no problems with the implementation logic. All verification steps passed.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Full Phase 2 pipeline operational: POST /speak → preprocess → TTS_QUEUE → _tts_worker → synthesis → audio
- Service ready for Phase 3: Claude Code hook that POSTs assistant text to http://127.0.0.1:5050/speak
- STATE dict ready for Phase 4 mute toggle (STATE["muted"]) and Phase 5 volume/speed control (STATE["volume"], STATE["speed"])
- Backpressure operational: 10 rapid requests → at most 3 queued, rest return 429

---
*Phase: 02-fastapi-http-server-and-tts-queue*
*Completed: 2026-02-26*

## Self-Check: PASSED

- [x] `agenttalk/tts_worker.py` exists on disk
- [x] `agenttalk/service.py` modified with /speak route
- [x] Git commits: `12e610a` (Task 1), `6a22e92` (Task 2) both present
- [x] `python -c "import agenttalk.service; print('service imports OK')"` → prints OK
- [x] Routes include `/speak`: confirmed via app.routes inspection
- [x] TTS_QUEUE.maxsize == 3, STATE has 4 keys
- [x] 25 preprocessor tests still passing (no regression)

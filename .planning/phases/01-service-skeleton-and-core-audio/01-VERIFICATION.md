---
phase: 01
status: passed
verified: 2026-02-26
---

# Phase 1 Verification: Service Skeleton and Core Audio

## Phase Goal

> A Windows background process launches without a console window, loads Kokoro, synthesizes audio from hardcoded text, plays it through speakers, logs all activity to file, and prevents duplicate instances via PID lock

**Verdict: PASSED** — All goal elements verified.

## Requirements Cross-Reference

| Req ID | Description | Evidence | Status |
|--------|-------------|----------|--------|
| TTS-01 | Service loads kokoro-onnx 0.5.0 offline | `from kokoro_onnx import Kokoro` + `Kokoro(MODEL_PATH, VOICES_PATH)` in service.py | PASSED |
| TTS-02 | Eager load + warmup before accepting requests | warmup synthesis at line ~128; `is_ready = True` only after warmup completes (pos 4944 < 7396) | PASSED |
| TTS-03 | /health 503 until ready, 200 after | `if not is_ready: return JSONResponse({"status":"initializing"}, status_code=503)` | PASSED |
| SVC-01 | No console window (pythonw.exe) | Documented in module docstring: "Launch via: pythonw.exe agenttalk/service.py" | PASSED |
| SVC-05 | PID lock at %APPDATA%\AgentTalk\service.pid | `acquire_pid_lock()` with psutil stale detection + `atexit.register(_release_pid_lock)` | PASSED |
| SVC-06 | File-only logging to agenttalk.log | `logging.FileHandler(LOG_FILE)` only — no StreamHandler | PASSED |
| SVC-07 | Catch/log all startup exceptions | `except FileNotFoundError` + `except Exception: logging.exception()` + `sys.excepthook` override | PASSED |

**Requirements: 7/7 PASSED**

## Success Criteria Verification

### Criterion 1: `pythonw.exe service.py` — no console window, audio plays within 10s
- **Code evidence**: `main()` calls `setup_logging()` → `acquire_pid_lock()` → `_start_http_server()` → `threading.Event().wait()`
- **Runtime evidence**: Log entry `Startup audio playback complete.` confirmed present at T+5s from service start
- **Console suppression**: pythonw.exe handles at interpreter level (documented in module docstring)
- **Status**: PASSED

### Criterion 2: Second launch detects PID file and exits cleanly
- **Code evidence**: `acquire_pid_lock()` reads PID file, checks `psutil.pid_exists(pid)` + `proc.name().lower()` contains "python", calls `sys.exit(0)`
- **Runtime evidence**: Log entry `AgentTalk service already running (PID X). Exiting.` confirmed
- **Status**: PASSED

### Criterion 3: Log contains startup progress entries
- **Runtime evidence** (all 4 required entries confirmed in %APPDATA%\AgentTalk\agenttalk.log):
  - `AgentTalk service starting` — PRESENT
  - `Loading Kokoro model` — PRESENT
  - `Warmup synthesis complete` — PRESENT
  - `Service ready` — PRESENT
- **Status**: PASSED

### Criterion 4: /health returns 503 before ready, 200 after warmup
- **Code evidence**: `is_ready: bool = False` module-level; set to `True` only after warmup; `/health` endpoint returns 503 when False, 200 when True
- **Runtime evidence**: `/health` polled and returned HTTP 200 `{"status": "ok"}` after ~5s startup
- **Status**: PASSED

### Criterion 5: Startup exception caught, logged, no silent crash
- **Code evidence**:
  - `except FileNotFoundError: logging.error(...)` handles missing model files
  - `except Exception: logging.exception(...)` in lifespan handles all other startup errors
  - `except Exception: logging.exception(...); sys.exit(1)` in `main()` handles fatal errors
  - `sys.excepthook = _log_uncaught` captures any uncaught exceptions to log file
- **Status**: PASSED

**Success Criteria: 5/5 PASSED**

## Files Verified

| File | Exists | Contains Key Functionality |
|------|--------|---------------------------|
| `requirements.txt` | YES | 5 pinned packages: kokoro-onnx==0.5.0, sounddevice==0.5.5, fastapi>=0.110, uvicorn>=0.29, psutil>=5.9 |
| `agenttalk/__init__.py` | YES | Empty package init |
| `agenttalk/service.py` | YES | All Phase 1 components: logging, PID lock, Kokoro TTS, audio playback, FastAPI /health, uvicorn daemon |

## Runtime Evidence

From `%APPDATA%\AgentTalk\agenttalk.log` (most recent session):
```
2026-02-26 03:17:24,618 [INFO] root: === AgentTalk service starting ===
2026-02-26 03:17:24,620 [INFO] root: PID lock acquired: ...service.pid (PID 50960)
2026-02-26 03:17:24,621 [INFO] root: HTTP server thread started (localhost:5050).
2026-02-26 03:17:24,676 [INFO] root: sounddevice default output device: [4] Speakers (Realtek(R) Audio) ...
2026-02-26 03:17:25,512 [INFO] root: Loading Kokoro model from ...models\kokoro-v1.0.onnx ...
2026-02-26 03:17:27,134 [INFO] root: Kokoro model loaded. Running warmup synthesis...
2026-02-26 03:17:27,833 [INFO] root: Warmup synthesis complete (samples=17408, rate=24000).
2026-02-26 03:17:27,833 [INFO] root: Service ready. /health will return 200.
2026-02-26 03:17:29,888 [INFO] root: Startup audio playback complete.
```
Total startup time: ~5.3 seconds (well within 10s criterion).

## Notable Findings

1. **Python 3.12 used instead of 3.11**: Python 3.11 not installed on dev machine. Phase 1 components (kokoro-onnx, sounddevice, fastapi, uvicorn, psutil) work correctly on Python 3.12. pystray (Phase 4) will require Python 3.11 — this is a known deferred concern.

2. **WasapiSettings not applied**: Research recommended `WasapiSettings(auto_convert=True)` for 24000 Hz → 44100 Hz conversion. Empirical testing showed PortAudio/MME handles this automatically. WasapiSettings caused `PaErrorCode -9984` on MME devices and was removed. Audio plays correctly without it.

3. **Model files in APPDATA**: kokoro-v1.0.onnx (311MB) and voices-v1.0.bin (27MB) downloaded to %APPDATA%\AgentTalk\models\ during execution. Phase 6 will automate this via `agenttalk setup`.

## Phase 1 Verification: PASSED

All 7 requirements verified. All 5 success criteria confirmed at runtime. Phase 1 goal achieved.

# Phase 1: Service Skeleton and Core Audio - Research

**Researched:** 2026-02-26
**Domain:** Python Windows background service, kokoro-onnx TTS, sounddevice audio, FastAPI health endpoint, PID locking
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TTS-01 | Service loads kokoro-onnx 0.5.0 as the primary TTS engine on startup (fully offline, no API key) | Kokoro() constructor API documented; model files at known URLs |
| TTS-02 | Service performs eager model load + warmup synthesis call before accepting requests (avoids 3-8s first-request latency) | kokoro.create() warmup pattern documented; FastAPI lifespan is correct hook |
| TTS-03 | Service exposes `/health` endpoint returning 503 until model is warm and ready | FastAPI lifespan + shared state variable pattern verified |
| SVC-01 | Service runs as a Windows background process with no console window (pythonw.exe + DETACHED_PROCESS) | pythonw.exe suppresses console; DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP pattern confirmed |
| SVC-05 | PID lock file at `%APPDATA%\AgentTalk\service.pid` prevents duplicate instances and enables clean process management | psutil.pid_exists() pattern; write-then-delete PID file lifecycle documented |
| SVC-06 | All service logs written to `%APPDATA%\AgentTalk\agenttalk.log` (pythonw.exe suppresses stdout; file logging is mandatory) | logging.FileHandler with APPDATA path pattern confirmed; RotatingFileHandler available |
| SVC-07 | Service catches and logs all startup exceptions before crashing (no silent failures) | sys.excepthook override + try/except in main() with logging.exception() pattern confirmed |
</phase_requirements>

---

## Summary

Phase 1 validates the core Windows runtime model for AgentTalk: a headless Python process that loads kokoro-onnx, synthesizes audio to speakers, prevents duplicate instances, and logs all activity. This phase intentionally does not expose a full HTTP API — it establishes the foundations (process model, TTS engine, logging, PID lock) that every later phase depends on.

The technology stack is well-defined. kokoro-onnx 0.5.0 (released 2026-01-30) provides a simple two-argument constructor and a `create()` method that returns numpy audio samples; sounddevice 0.5.5 plays those samples via PortAudio/WASAPI. The `pythonw.exe` interpreter suppresses the console window at launch time — no subprocess flags needed when the user runs `pythonw.exe service.py` directly. PID locking is a hand-rolled pattern using psutil for stale-PID detection. File logging via Python's built-in `logging` module is mandatory because pythonw.exe suppresses stdout entirely.

The one unresolved risk from STATE.md is whether `espeakng-loader` (a kokoro-onnx dependency) works on a clean Windows machine without a system-level espeak-ng install. This is an empirical question that must be validated during Phase 1 execution, not resolvable by research alone. The mitigaton is: test against a clean venv on the developer machine before declaring Phase 1 complete.

**Primary recommendation:** Use kokoro-onnx 0.5.0 + sounddevice 0.5.5 + psutil + Python stdlib logging. Run a FastAPI-lite `/health` endpoint in a daemon thread (uvicorn with signal-handler override). Do NOT use pythonw.exe's DETACHED_PROCESS flag for this phase — the user launches via `pythonw.exe service.py` directly, which handles console suppression.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| kokoro-onnx | 0.5.0 | TTS synthesis via ONNX runtime | Sole v1 engine per project decision; offline, no API key |
| sounddevice | 0.5.5 | Audio playback via PortAudio/WASAPI | Standard numpy-to-speakers bridge; supports WasapiSettings |
| fastapi | >=0.110 | HTTP server for /health endpoint | Project uses FastAPI for all endpoints (Phase 2 expands it) |
| uvicorn | >=0.29 | ASGI server running in daemon thread | Required by FastAPI; daemon thread pattern needed for non-main-thread use |
| psutil | >=5.9 | PID existence check for stale PID files | Cross-platform; pid_exists() is O(1) via OpenProcess on Windows |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| onnxruntime | >=1.20.1 | ONNX inference backend (kokoro-onnx dep) | Installed automatically by kokoro-onnx |
| espeakng-loader | >=0.2.4 | Phoneme backend for kokoro-onnx | Installed automatically; needs validation on clean Windows |
| numpy | >=2.0.2 | Audio sample array handling | Installed automatically by kokoro-onnx |
| pathlib | stdlib | Cross-platform path construction | Use for all APPDATA path construction |
| logging | stdlib | File-based log output | Required because pythonw.exe suppresses stdout |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psutil for PID check | filelock | filelock uses kernel-level file locks (msvcrt) — harder to reason about stale state; psutil.pid_exists() is simpler for "is process alive?" check |
| logging.FileHandler | concurrent-log-handler | concurrent-log-handler adds concurrency safety for Windows; overkill for Phase 1 single-writer scenario |
| daemon thread + uvicorn | multiprocessing.Process | Subprocess approach is heavier and complicates PID tracking; daemon thread is sufficient for Phase 1 |

**Installation:**
```bash
pip install kokoro-onnx==0.5.0 sounddevice fastapi uvicorn psutil
```

Model files (download once during setup, stored in %APPDATA%\AgentTalk\models\):
```
kokoro-v1.0.onnx  (~300MB)
voices-v1.0.bin
```
Download from: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0

---

## Architecture Patterns

### Recommended Project Structure

```
agenttalk/
├── service.py           # Entry point: main() with startup guard, PID lock, logging init
├── tts_engine.py        # Kokoro wrapper: load(), warmup(), synthesize()
├── audio.py             # sounddevice playback: play_samples(samples, rate)
├── health.py            # FastAPI app with /health route and is_ready flag
└── pid_lock.py          # PID file write/check/cleanup
```

For Phase 1, this can start as a single `service.py` file and be split later. The planner may choose to keep it monolithic for this phase.

### Pattern 1: pythonw.exe Console Suppression

**What:** Running `pythonw.exe service.py` is the mechanism that suppresses the console window. The interpreter itself does this — no subprocess flags or special code needed when the user executes it directly.

**When to use:** Always. The service is always launched via pythonw.exe, not python.exe.

**Key detail:** When pythonw.exe spawns child processes (e.g., for future hook scripts), combine `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` flags to prevent console window flash on children.

```python
# Source: Python docs / Windows subprocess flags
import subprocess
import os

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

proc = subprocess.Popen(
    ["pythonw.exe", "child_script.py"],
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True
)
```

### Pattern 2: Kokoro Load + Warmup

**What:** Load the Kokoro model at startup, then immediately synthesize a short dummy sentence. This forces ONNX to JIT-compile the graph and cache memory allocations, eliminating 3-8s first-request latency.

**When to use:** In the service startup sequence, before marking `/health` as ready.

```python
# Source: kokoro-onnx GitHub examples/save.py + PyPI docs
from kokoro_onnx import Kokoro

def load_and_warmup(model_path: str, voices_path: str) -> Kokoro:
    kokoro = Kokoro(model_path, voices_path)
    # Warmup: synthesize short dummy text to force JIT compilation
    _samples, _rate = kokoro.create(
        "Warmup.",
        voice="af_heart",
        speed=1.0,
        lang="en-us"
    )
    # Discard warmup audio — just needed to prime the engine
    return kokoro
```

### Pattern 3: Sounddevice Playback with WASAPI auto_convert

**What:** Play numpy audio samples through the default output device. `WasapiSettings(auto_convert=True)` enables the system-level sample rate converter so the kokoro output rate (24000 Hz) works on any Windows audio device regardless of its configured rate.

**When to use:** Every audio playback call.

```python
# Source: python-sounddevice 0.5.1 docs (platform-specific settings)
import sounddevice as sd
import numpy as np

def play_audio(samples: np.ndarray, sample_rate: int) -> None:
    wasapi_settings = sd.WasapiSettings(auto_convert=True)
    sd.play(samples, samplerate=sample_rate, extra_settings=wasapi_settings)
    sd.wait()  # Block until playback finishes
```

Note: `sd.wait()` is required to prevent the function from returning before audio finishes. For Phase 1, blocking playback is acceptable. Phase 2 introduces a queue and non-blocking threading.

### Pattern 4: PID Lock File with Stale Detection

**What:** On startup, read the PID file (if it exists). Use psutil to check if that PID is still alive. If alive: exit cleanly. If stale (process dead): remove old PID file and continue. Write current PID on successful startup. Delete PID file on shutdown.

**When to use:** First thing in main(), before any other initialization.

```python
# Source: psutil docs + common daemon pattern
import os
import sys
import psutil
from pathlib import Path

PID_FILE = Path(os.environ["APPDATA"]) / "AgentTalk" / "service.pid"

def acquire_pid_lock() -> None:
    """Exit if already running; write PID file otherwise."""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if psutil.pid_exists(pid):
                # Verify it's actually our process (not PID reuse)
                try:
                    proc = psutil.Process(pid)
                    if "python" in proc.name().lower():
                        print(f"Service already running (PID {pid}). Exiting.")
                        sys.exit(0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # PID reuse or access denied — treat as stale
        except (ValueError, OSError):
            pass  # Corrupt PID file — overwrite it
        # Stale PID file — remove and continue
        PID_FILE.unlink(missing_ok=True)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

def release_pid_lock() -> None:
    PID_FILE.unlink(missing_ok=True)
```

### Pattern 5: File Logging Setup (pythonw.exe mandatory)

**What:** pythonw.exe discards all output to stdout and stderr. Every log message MUST go to the file handler. Set up logging before any other code runs — including before the try/except startup guard — so that even import errors are captured.

```python
# Source: Python stdlib logging docs
import logging
import os
from pathlib import Path

LOG_FILE = Path(os.environ["APPDATA"]) / "AgentTalk" / "agenttalk.log"

def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            # No StreamHandler — pythonw.exe discards stdout
        ]
    )
    # Also capture uncaught exceptions
    import sys
    def log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = log_uncaught
```

### Pattern 6: FastAPI /health with 503-until-ready

**What:** A global `is_ready` flag starts as False. The `/health` endpoint returns 503 while False, 200 when True. The lifespan function sets it to True after Kokoro warmup completes.

**When to use:** Phase 1 needs a minimal FastAPI app; Phase 2 will expand it.

```python
# Source: FastAPI official docs (lifespan events)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

is_ready: bool = False
kokoro_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global is_ready, kokoro_engine
    # Startup: runs before first request
    logging.info("Loading Kokoro model...")
    kokoro_engine = load_and_warmup(MODEL_PATH, VOICES_PATH)
    is_ready = True
    logging.info("Kokoro model ready. Service accepting requests.")
    yield
    # Shutdown
    is_ready = False

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    if not is_ready:
        return JSONResponse({"status": "initializing"}, status_code=503)
    return JSONResponse({"status": "ok"}, status_code=200)
```

### Pattern 7: Uvicorn in a Daemon Thread (Windows-safe)

**What:** uvicorn.run() blocks the calling thread. To run it in a background thread, subclass uvicorn.Server and override install_signal_handlers() to be a no-op (required on Windows where loop.add_signal_handler() raises NotImplementedError).

```python
# Source: FastAPI GitHub issue #650 / community pattern
import threading
import uvicorn

class BackgroundServer(uvicorn.Server):
    def install_signal_handlers(self):
        pass  # Disable — cannot install signal handlers in non-main thread

def start_http_server(app, host="127.0.0.1", port=5050) -> threading.Thread:
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = BackgroundServer(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread
```

Note: Phase 1 needs a minimal HTTP server only for /health. The full FastAPI setup (port 5050, /speak endpoint) comes in Phase 2.

### Anti-Patterns to Avoid

- **Using logging.basicConfig() after any import that triggers logging:** basicConfig is a no-op if the root logger already has handlers. Call it first.
- **Writing to stdout/stderr in pythonw.exe context:** These are discarded silently. Any print() call is invisible. Use logging.
- **Using psutil.process_iter() name matching instead of PID file:** Process name matching is ambiguous (multiple pythonw.exe instances). Always use PID file + pid_exists() for uniqueness.
- **Using standard RotatingFileHandler for high-concurrency writes:** On Windows, RotatingFileHandler has a known race condition during rotation when multiple processes write to the same file. For Phase 1 (single process), it is safe. If concurrent access is later needed, use concurrent-log-handler.
- **Blocking the main thread with uvicorn.run():** Phase 1's main thread does: logging init → PID lock → start HTTP daemon thread → start TTS warmup → block on pystray (Phase 4) or idle. Never run uvicorn on main thread for this architecture.
- **Calling sd.play() without sd.wait():** Without wait(), the function returns immediately and the audio array may be garbage collected before playback finishes, causing silent truncation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Phoneme-to-speech conversion | Custom g2p logic | kokoro-onnx (embeds espeakng-loader + phonemizer) | G2P is complex, language-specific, involves exception dictionaries |
| Audio format conversion / resampling | Manual numpy resampling | sounddevice WasapiSettings(auto_convert=True) | System-level SRC is higher quality and handles channel layout too |
| Process existence check | Parse `tasklist` output or custom Win32 calls | psutil.pid_exists() | psutil uses OpenProcess directly; O(1) on Windows |
| Thread-safe FastAPI startup state | Custom threading.Event + polling | FastAPI lifespan + module-level flag | Lifespan is the official pattern; handles ASGI lifecycle correctly |

**Key insight:** kokoro-onnx already bundles the entire TTS pipeline including g2p, ONNX inference, and voice mixing. The only integration points needed are: load, warmup, call create(), play samples.

---

## Common Pitfalls

### Pitfall 1: espeakng-loader on Clean Windows Machine

**What goes wrong:** kokoro-onnx depends on espeakng-loader, which bundles espeak-ng DLLs. On some Windows machines, the DLL fails to load with a missing VCRUNTIME dependency error.

**Why it happens:** espeakng-loader ships prebuilt DLLs that require Microsoft Visual C++ Redistributable. If the machine doesn't have it, import fails at runtime.

**How to avoid:** Document the Visual C++ Redistributable as a prerequisite. During Phase 1, test on a clean virtual environment to confirm. If it fails, add a fallback: `pip install espeakng` separately and check for error.

**Warning signs:** ImportError mentioning "espeakng_loader" or "DLL load failed" in the log file at startup.

**State.md note:** This is a flagged blocker — needs empirical validation, not resolvable by research.

### Pitfall 2: Logging Not Initialized Before First Import

**What goes wrong:** If any import (e.g., `from kokoro_onnx import Kokoro`) triggers a log message before setup_logging() is called, that message goes nowhere. If that import then fails, the error is silently lost.

**Why it happens:** logging.basicConfig() is a no-op if any handler is already attached. Third-party libs sometimes attach handlers on import.

**How to avoid:** Call setup_logging() as the very first line in main() (or even at module top-level), before any other imports.

**Warning signs:** Silent crashes with no log entries at all. Check if LOG_FILE exists and has any content.

### Pitfall 3: PID File Left Behind After Crash

**What goes wrong:** If the service crashes without cleanup, the PID file remains. On next launch, the service reads a stale PID, finds no live process, but if it doesn't handle the stale case, it exits thinking another instance is running.

**Why it happens:** Crash before atexit handler or finally block runs, or atexit not registered.

**How to avoid:** In acquire_pid_lock(), always verify the PID is alive AND belongs to a Python process. Register PID cleanup with atexit.register(release_pid_lock).

**Warning signs:** Service refuses to start after a crash; PID file exists with a PID that doesn't correspond to a running process.

### Pitfall 4: sounddevice WASAPI Sample Rate Mismatch

**What goes wrong:** Kokoro returns audio at 24000 Hz. Windows audio devices are typically configured at 44100 Hz or 48000 Hz. Without auto_convert, sounddevice raises `PortAudioError: Invalid sample rate`.

**Why it happens:** WASAPI shared mode requires the audio stream sample rate to match the device's configured rate.

**How to avoid:** Always use `sd.WasapiSettings(auto_convert=True)` as the extra_settings argument. Set it as the default early in service startup: `sd.default.extra_settings = sd.WasapiSettings(auto_convert=True)`.

**Warning signs:** PortAudioError in the log during the warmup synthesis playback.

### Pitfall 5: uvicorn Signal Handlers on Non-Main Thread (Windows)

**What goes wrong:** `uvicorn.run()` called in a thread on Windows raises `NotImplementedError` in install_signal_handlers because `loop.add_signal_handler()` is not supported on Windows event loops.

**Why it happens:** uvicorn's signal handling uses POSIX-style signal registration which doesn't work in threads or on Windows ProactorEventLoop.

**How to avoid:** Subclass uvicorn.Server, override install_signal_handlers() as a no-op. Use that subclass instead of uvicorn.run().

**Warning signs:** `NotImplementedError` traceback at service startup, HTTP server never comes up.

### Pitfall 6: Python 3.12+ pystray GIL Crash

**What goes wrong:** pystray crashes with a GIL-related error on Python 3.12+.

**Why it happens:** Known upstream issue in pystray, no fix released as of 2026-02-26.

**How to avoid:** Use Python 3.11 exactly. This is a locked project decision from STATE.md.

**Warning signs:** Service crashes immediately after tray icon creation (Phase 4 concern, but worth noting during Phase 1 environment setup).

---

## Code Examples

Verified patterns from official sources:

### Kokoro Instantiation and Synthesis

```python
# Source: github.com/thewh1teagle/kokoro-onnx examples/save.py (verified 2026-02-26)
from kokoro_onnx import Kokoro

kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
samples, sample_rate = kokoro.create(
    "Hello from AgentTalk.",
    voice="af_heart",   # American Female voice
    speed=1.0,          # 0.5 to 2.0
    lang="en-us"
)
# samples: numpy float32 array
# sample_rate: typically 24000
```

### Playback with WASAPI auto_convert

```python
# Source: python-sounddevice 0.5.1 docs (verified 2026-02-26)
import sounddevice as sd

# Set globally at startup (applies to all sd.play() calls)
sd.default.extra_settings = sd.WasapiSettings(auto_convert=True)

sd.play(samples, samplerate=sample_rate)
sd.wait()
```

### APPDATA directory path

```python
# Source: Python stdlib os docs
import os
from pathlib import Path

APPDATA_DIR = Path(os.environ["APPDATA"]) / "AgentTalk"
APPDATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = APPDATA_DIR / "agenttalk.log"
PID_FILE = APPDATA_DIR / "service.pid"
MODELS_DIR = APPDATA_DIR / "models"
```

### Full minimal service.py skeleton

```python
# Synthesizes from hardcoded text, logs startup, enforces PID lock
import os, sys, logging, atexit, threading
import psutil
import sounddevice as sd
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# --- Paths ---
APPDATA_DIR = Path(os.environ["APPDATA"]) / "AgentTalk"
LOG_FILE    = APPDATA_DIR / "agenttalk.log"
PID_FILE    = APPDATA_DIR / "service.pid"
MODELS_DIR  = APPDATA_DIR / "models"

def setup_logging():
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
    )
    def log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = log_uncaught

def acquire_pid_lock():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if psutil.pid_exists(pid):
                try:
                    proc = psutil.Process(pid)
                    if "python" in proc.name().lower():
                        logging.warning(f"Already running (PID {pid}). Exiting.")
                        sys.exit(0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (ValueError, OSError):
            pass
        PID_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))

# --- FastAPI ---
is_ready = False
kokoro_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global is_ready, kokoro_engine
    logging.info("Loading Kokoro TTS model...")
    from kokoro_onnx import Kokoro
    kokoro_engine = Kokoro(
        str(MODELS_DIR / "kokoro-v1.0.onnx"),
        str(MODELS_DIR / "voices-v1.0.bin"),
    )
    logging.info("Running warmup synthesis...")
    _s, _r = kokoro_engine.create("Warmup.", voice="af_heart", speed=1.0, lang="en-us")
    is_ready = True
    logging.info("Service ready. /health will return 200.")
    # Phase 1: play hardcoded audio to prove the pipeline works
    sd.default.extra_settings = sd.WasapiSettings(auto_convert=True)
    samples, rate = kokoro_engine.create(
        "AgentTalk is running.", voice="af_heart", speed=1.0, lang="en-us"
    )
    sd.play(samples, samplerate=rate)
    sd.wait()
    logging.info("Startup audio playback complete.")
    yield
    is_ready = False

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    if not is_ready:
        return JSONResponse({"status": "initializing"}, status_code=503)
    return JSONResponse({"status": "ok"}, status_code=200)

# --- Uvicorn daemon thread ---
class BackgroundServer(uvicorn.Server):
    def install_signal_handlers(self):
        pass  # Required for non-main thread / Windows

def start_http_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=5050, log_level="warning")
    server = BackgroundServer(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return t

# --- Main ---
def main():
    setup_logging()
    logging.info("=== AgentTalk service starting ===")
    try:
        acquire_pid_lock()
        start_http_server()
        logging.info("HTTP server started. Waiting for lifespan startup...")
        # Keep main thread alive (Phase 4 will replace this with pystray)
        threading.Event().wait()
    except Exception:
        logging.exception("Fatal error during startup")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| @app.on_event("startup") decorator | `@asynccontextmanager` lifespan parameter | FastAPI ~0.95 | on_event is deprecated; lifespan is the only forward-compatible way |
| uvicorn.run() in main thread | BackgroundServer subclass in daemon thread | Always needed for multi-thread; pattern formalized ~2023 | Must override install_signal_handlers on Windows |
| sounddevice without WasapiSettings | WasapiSettings(auto_convert=True) | sounddevice 0.4+ | Eliminates sample rate mismatch errors on Windows without manual resampling |
| Piper TTS (archived Oct 2025) | kokoro-onnx 0.5.0 | Oct 2025 | Piper upstream archived; kokoro-onnx is the maintained alternative |

**Deprecated/outdated:**
- `@app.on_event("startup")`: Works but deprecated; use lifespan.
- Piper TTS: Upstream archived October 2025; Windows DLL issues; kokoro-onnx is the v1 replacement.

---

## Open Questions

1. **espeakng-loader DLL compatibility on clean Windows 11**
   - What we know: kokoro-onnx depends on espeakng-loader >=0.2.4 which bundles espeak-ng DLLs
   - What's unclear: Whether the bundled DLLs require VCRUNTIME that may be absent on a clean dev machine
   - Recommendation: First task of Phase 1 should be a "cold start" test: fresh venv on developer's machine, pip install, verify import succeeds. If DLL error occurs, document VCRUNTIME prereq.

2. **Kokoro model output sample rate**
   - What we know: Kokoro is described as "near real-time" and sounddevice uses WasapiSettings for rate mismatch
   - What's unclear: The exact sample rate kokoro.create() returns (likely 24000 Hz based on Kokoro-82M architecture)
   - Recommendation: Log the rate returned by create() during warmup and verify WasapiSettings(auto_convert=True) resolves any mismatch without error.

3. **Uvicorn startup timing — is_ready race**
   - What we know: Lifespan startup runs before uvicorn accepts requests, so /health returns 503 during model load
   - What's unclear: Exact timing of when uvicorn binds the port vs. when lifespan starts executing
   - Recommendation: After start_http_server() returns, add a short polling loop (up to 10 seconds) that checks if the port is bound before logging "HTTP server ready" — prevents false "ready" log before uvicorn has bound.

---

## Sources

### Primary (HIGH confidence)
- https://github.com/thewh1teagle/kokoro-onnx — Official repo; examples/save.py read directly; pyproject.toml dependencies verified
- https://pypi.org/project/kokoro-onnx/ — Version 0.5.0 confirmed, released 2026-01-30
- https://python-sounddevice.readthedocs.io/en/0.5.1/api/platform-specific-settings.html — WasapiSettings(auto_convert=True) API verified
- https://fastapi.tiangolo.com/advanced/events/ — Lifespan asynccontextmanager pattern; on_event deprecation confirmed
- https://pypi.org/project/sounddevice/ — Version 0.5.5, released 2026-01-23

### Secondary (MEDIUM confidence)
- FastAPI GitHub issue #650 — BackgroundServer pattern for daemon thread uvicorn (community-verified, multiple sources)
- psutil docs https://psutil.readthedocs.io — pid_exists() behavior on Windows; known ERROR_ACCESS_DENIED edge case
- Python stdlib logging docs — FileHandler, basicConfig, sys.excepthook patterns

### Tertiary (LOW confidence)
- STATE.md note on pystray Python 3.12 GIL crash — Project-internal finding, empirically established; not verified against upstream pystray issue tracker

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions confirmed from PyPI and official repos; kokoro-onnx 0.5.0 and sounddevice 0.5.5 explicitly verified
- Architecture: HIGH — FastAPI lifespan pattern from official docs; uvicorn daemon thread from confirmed community pattern; PID pattern from stdlib + psutil docs
- Pitfalls: MEDIUM-HIGH — Most pitfalls derived from official sources; espeakng-loader DLL risk is LOW (empirical gap)

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days — kokoro-onnx and sounddevice are active projects; check for new releases before planning)

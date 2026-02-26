"""
AgentTalk background service — Phase 1: Service Skeleton and Core Audio.

Launch via: pythonw.exe agenttalk/service.py
Console suppression is handled by the pythonw.exe interpreter itself.
No special subprocess flags are needed for the service process itself.
"""
import os
import sys
import logging
import atexit
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import queue
import time

import psutil
import sounddevice as sd
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import pystray

from agenttalk.tts_worker import TTS_QUEUE, STATE, start_tts_worker, _ducker
from agenttalk.tray import build_tray_icon
from agenttalk.config_loader import load_config, save_config
from agenttalk.preprocessor import preprocess

# ---------------------------------------------------------------------------
# APPDATA paths
# ---------------------------------------------------------------------------
APPDATA_DIR = Path(os.environ["APPDATA"]) / "AgentTalk"
LOG_FILE    = APPDATA_DIR / "agenttalk.log"
PID_FILE    = APPDATA_DIR / "service.pid"
MODELS_DIR  = APPDATA_DIR / "models"

MODEL_PATH  = MODELS_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"

# ---------------------------------------------------------------------------
# Logging — must be initialised before any other code runs in main()
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """Configure file-only logging. pythonw.exe discards stdout/stderr."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            # No StreamHandler — pythonw.exe silently discards stdout
        ],
    )

    def _log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _log_uncaught

    def _thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        logging.critical("Unhandled exception in thread '%s'", args.thread.name if args.thread else "unknown", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = _thread_excepthook


# ---------------------------------------------------------------------------
# PID lock — prevents duplicate instances
# ---------------------------------------------------------------------------

def acquire_pid_lock() -> None:
    """
    Prevent duplicate service instances.
    - If PID file exists and PID is alive (verified as python process): log and exit.
    - If PID file exists but PID is stale/dead: remove stale file and continue.
    - If no PID file: write current PID and register atexit cleanup.
    """
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if psutil.pid_exists(pid):
                try:
                    proc = psutil.Process(pid)
                    if "python" in proc.name().lower():
                        logging.warning(
                            "AgentTalk service already running (PID %d). Exiting.", pid
                        )
                        sys.exit(0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # PID reuse or access denied — treat as stale
        except (ValueError, OSError):
            pass  # Corrupt PID file — overwrite it

        # Stale PID file — remove and continue startup
        logging.info("Removing stale PID file.")
        PID_FILE.unlink(missing_ok=True)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    logging.info("PID lock acquired: %s (PID %d)", PID_FILE, os.getpid())
    atexit.register(_release_pid_lock)


def _release_pid_lock() -> None:
    PID_FILE.unlink(missing_ok=True)
    logging.info("PID lock released.")


# ---------------------------------------------------------------------------
# TTS engine — kokoro-onnx
# ---------------------------------------------------------------------------

def _load_and_warmup_kokoro():
    """
    Load Kokoro model and perform a warmup synthesis call.
    Warmup forces ONNX JIT compilation, eliminating 3-8s first-request latency.
    Returns the loaded Kokoro instance.
    Raises FileNotFoundError if model files are missing.
    """
    for p in (MODEL_PATH, VOICES_PATH):
        if not p.exists():
            raise FileNotFoundError(f"Model file missing: {p}\nRun 'agenttalk setup' to download.")

    from kokoro_onnx import Kokoro  # deferred import — logging is already active

    logging.info("Loading Kokoro model from %s ...", MODEL_PATH)
    kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    logging.info("Kokoro model loaded. Running warmup synthesis...")

    _samples, _rate = kokoro.create(
        "Warmup.",
        voice="af_heart",
        speed=1.0,
        lang="en-us",
    )
    logging.info("Warmup synthesis complete (samples=%d, rate=%d).", len(_samples), _rate)
    return kokoro


# ---------------------------------------------------------------------------
# Audio playback — sounddevice (PortAudio/MME handles sample rate conversion)
# ---------------------------------------------------------------------------

def _configure_audio() -> None:
    """
    Configure sounddevice for playback with conditional WASAPI detection.

    Queries the default output device's host API. If the device is WASAPI,
    applies WasapiSettings(auto_convert=True) to handle sample rate mismatches.
    For non-WASAPI devices (MME, DirectSound), PortAudio handles resampling
    internally — applying WasapiSettings to those devices causes
    PaErrorCode -9984 (incompatible host API specific stream info).

    This satisfies AUDIO-05: WASAPI auto_convert is set only when appropriate.
    """
    try:
        device_info = sd.query_devices(kind="output")
        hostapi_id = device_info.get("hostapi", 0)
        hostapi_info = sd.query_hostapis(hostapi_id)
        hostapi_name = hostapi_info.get("name", "").upper()
        if "WASAPI" in hostapi_name:
            sd.default.extra_settings = sd.WasapiSettings(auto_convert=True)
            logging.info("WASAPI device detected — auto_convert enabled.")
        else:
            logging.info(
                "Non-WASAPI device (%s) — using PortAudio default resampling.",
                hostapi_name,
            )
    except sd.PortAudioError:
        logging.warning(
            "Could not detect host API; using PortAudio defaults.", exc_info=True
        )
    except (AttributeError, TypeError):
        logging.error(
            "Could not detect host API; using PortAudio defaults.", exc_info=True
        )


def play_audio(samples, sample_rate: int) -> None:
    """
    Play numpy audio samples synchronously through the default output device.
    sd.wait() is mandatory — without it, audio truncates silently (garbage collection).

    WASAPI note: WasapiSettings(auto_convert=True) is NOT used here — empirical testing
    shows that PortAudio/MME handles 24000 Hz vs 44100/48000 Hz sample rate conversion
    automatically on Windows. Applying WasapiSettings to an MME device causes
    PaErrorCode -9984 (Incompatible host API specific stream info).
    If WASAPI exclusive mode is needed for a specific device, pass it explicitly.
    """
    sd.play(samples, samplerate=sample_rate)
    sd.wait()  # Block until playback finishes — do NOT omit; audio truncates silently


# ---------------------------------------------------------------------------
# FastAPI — /health endpoint
# ---------------------------------------------------------------------------

is_ready: bool = False
_kokoro_engine = None
# Tray icon reference — set by _setup() callback, read by _lifespan to pass to start_tts_worker.
_tray_icon = None


class SpeakRequest(BaseModel):
    """Request body for POST /speak."""

    text: str


class ConfigRequest(BaseModel):
    """Request body for POST /config — all fields optional (partial update)."""

    voice: str | None = None
    speed: float | None = None
    volume: float | None = None
    model: str | None = None       # "kokoro" or "piper"
    muted: bool | None = None
    pre_cue_path: str | None = None
    post_cue_path: str | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """FastAPI lifespan: load Kokoro before accepting requests; set is_ready after warmup."""
    global is_ready, _kokoro_engine
    try:
        _configure_audio()
        _kokoro_engine = _load_and_warmup_kokoro()
        is_ready = True
        logging.info("Service ready. /health will return 200.")

        # Phase 4: Start TTS worker AFTER Kokoro loads, passing the tray icon reference.
        # _tray_icon is set by _setup() before _start_http_server() is called, so it is
        # populated by the time _lifespan runs inside uvicorn.
        start_tts_worker(_kokoro_engine, icon=_tray_icon)
        logging.info("TTS worker started with icon reference.")

        # Startup audio: confirms full pipeline is working.
        logging.info("Running startup audio proof: synthesizing 'AgentTalk is running.'")
        samples, rate = _kokoro_engine.create(
            "AgentTalk is running.",
            voice="af_heart",
            speed=1.0,
            lang="en-us",
        )
        play_audio(samples, rate)
        logging.info("Startup audio playback complete.")

    except FileNotFoundError:
        logging.error(
            "Model files missing — service will start but /health returns 503 until models are present."
        )
    except Exception:
        logging.exception("Error during Kokoro startup — service degraded; /health returns 503.")

    yield  # Service runs here

    is_ready = False
    logging.info("FastAPI shutdown complete.")


app = FastAPI(lifespan=_lifespan)


@app.get("/health")
def health():
    """Returns 503 while Kokoro is loading; 200 when ready."""
    if not is_ready:
        return JSONResponse({"status": "initializing"}, status_code=503)
    return JSONResponse({"status": "ok"}, status_code=200)


@app.post("/speak", status_code=202)
async def speak(req: SpeakRequest):
    """
    Accept text, preprocess for TTS readiness, and queue for synthesis.

    Returns:
        202 + {"status": "queued", "sentences": N}  — text enqueued for playback
        200 + {"status": "skipped", ...}             — no speakable content after preprocessing
        429 + {"status": "dropped", ...}             — TTS queue full (backpressure)
        503 + {"status": "not_ready"}                — service not yet initialized
    """
    if not is_ready:
        return JSONResponse({"status": "not_ready"}, status_code=503)

    try:
        sentences = preprocess(req.text)
    except Exception:
        logging.exception("preprocess() failed for /speak request.")
        return JSONResponse({"status": "error", "reason": "preprocessing failed"}, status_code=500)

    if not sentences:
        return JSONResponse(
            {"status": "skipped", "reason": "no speakable sentences"},
            status_code=200,
        )

    try:
        TTS_QUEUE.put_nowait(sentences)
        return JSONResponse(
            {"status": "queued", "sentences": len(sentences)},
            status_code=202,
        )
    except queue.Full:
        logging.info(
            "TTS queue full (%d items) — dropping /speak request.", TTS_QUEUE.qsize()
        )
        return JSONResponse(
            {"status": "dropped", "reason": "queue full"},
            status_code=429,
        )


@app.post("/config", status_code=200)
async def update_config(req: ConfigRequest):
    """
    Update one or more runtime settings. Changes take effect immediately (CFG-03).
    Persists all settings to config.json after each update (CFG-01, CFG-02).

    Returns:
        200 + {"status": "ok", "updated": [...]}  — keys updated in STATE and saved to disk
        200 + {"status": "ok", "updated": []}     — empty body (no-op)
    """
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return JSONResponse({"status": "ok", "updated": []})
    for key, value in updates.items():
        if key in STATE:
            STATE[key] = value
            logging.info("Config updated: %s = %s", key, value)
    try:
        save_config(STATE)
    except OSError:
        logging.exception("save_config() failed — config not persisted.")
        return JSONResponse({"status": "error", "reason": "config save failed"}, status_code=500)
    return JSONResponse({"status": "ok", "updated": list(updates.keys())})


@app.post("/stop", status_code=200)
async def stop_service():
    """
    Silence current TTS and terminate the service process.

    Calls sd.stop() immediately, then schedules os._exit(0) in a daemon thread
    with a 0.1s delay so the HTTP response is returned before the process exits.
    (os._exit(0) terminates without waiting for threads — same as _on_quit().)

    CMD-02: /agenttalk:stop slash command calls this endpoint.
    """
    sd.stop()  # Interrupt any currently playing audio immediately

    def _exit():
        time.sleep(0.1)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return JSONResponse({"status": "stopped"})


# ---------------------------------------------------------------------------
# Uvicorn daemon thread — Windows-safe (no signal handler)
# ---------------------------------------------------------------------------

class _BackgroundServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass  # Required: loop.add_signal_handler() raises NotImplementedError on Windows threads


def _start_http_server() -> threading.Thread:
    """Start uvicorn on localhost:5050 in a daemon thread."""
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=5050,
        log_config=None,
    )
    server = _BackgroundServer(config)
    def _run_server():
        try:
            server.run()
        except OSError:
            logging.critical("HTTP server failed to start (OSError — port in use?).", exc_info=True)
        except Exception:
            logging.critical("HTTP server crashed unexpectedly.", exc_info=True)

    thread = threading.Thread(target=_run_server, daemon=True, name="uvicorn")
    thread.start()
    logging.info("HTTP server thread started (localhost:5050).")
    return thread


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()  # MUST be first — before any third-party imports or other code
    logging.info("=== AgentTalk service starting ===")
    try:
        acquire_pid_lock()

        # CFG-01, CFG-02, CFG-03: Restore all persisted settings from config.json at startup.
        # This ensures voice, model, speed, volume, mute, and cue paths survive restarts.
        _cfg = load_config()
        for _key in ("voice", "speed", "volume", "model", "muted", "pre_cue_path", "post_cue_path"):
            if _key in _cfg and _cfg[_key] is not None:
                STATE[_key] = _cfg[_key]
                logging.info("Config restored: %s = %s", _key, STATE[_key])

        # Register atexit: unduck any ducked sessions on abnormal exit.
        # This covers crashes and SIGTERM — prevents Spotify/browser stuck at 50%.
        atexit.register(_ducker.unduck)

        def _on_quit() -> None:
            """Called by tray Quit menu item before icon.stop()."""
            logging.info("Tray Quit selected — shutting down.")
            _ducker.unduck()  # Restore any ducked sessions immediately
            # os._exit(0) terminates the entire process immediately.
            # sys.exit() raises SystemExit which daemon threads can swallow.
            os._exit(0)

        # Build tray icon (does NOT run — just constructs the pystray.Icon object).
        # STATE is imported from tts_worker; tray menu reads muted and voice from it.
        icon = build_tray_icon(state=STATE, on_quit=_on_quit)

        def _setup(icon: pystray.Icon) -> None:
            """
            Called by pystray once the Win32 message loop is running.

            MUST set icon.visible = True here (not before icon.run()).
            The visible property can only be set while the icon is running (pystray pitfall #1).

            Stores the icon reference so _lifespan can pass it to start_tts_worker.
            Starts the HTTP server daemon thread — uvicorn's _lifespan runs Kokoro load,
            then calls start_tts_worker(_kokoro_engine, icon=_tray_icon).
            """
            global _tray_icon
            icon.visible = True  # REQUIRED — icon starts hidden by default
            _tray_icon = icon
            _start_http_server()
            logging.info("Service setup complete — tray icon visible, HTTP server starting.")

        # SVC-04: pystray Icon.run() takes the main thread (Win32 message loop).
        # This replaces threading.Event().wait() from Phase 1.
        # _setup fires once the icon is running; it stores the icon ref and starts HTTP.
        # _lifespan (inside uvicorn) starts the TTS worker after Kokoro loads.
        logging.info("Starting pystray tray icon on main thread.")
        icon.run(setup=_setup)

    except Exception:
        logging.exception("Fatal error during startup")
        sys.exit(1)


if __name__ == "__main__":
    main()

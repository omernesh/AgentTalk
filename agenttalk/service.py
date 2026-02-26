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

import psutil
import sounddevice as sd
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

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
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Kokoro model not found: {MODEL_PATH}\n"
            "Run `agenttalk setup` to download model files."
        )
    if not VOICES_PATH.exists():
        raise FileNotFoundError(
            f"Kokoro voices not found: {VOICES_PATH}\n"
            "Run `agenttalk setup` to download model files."
        )

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
    Configure sounddevice for playback.
    Probes the default output device to confirm playback capability.
    WASAPI-specific settings are NOT applied globally — they cause host API mismatch errors
    when the default device uses MME/DirectSound (PortAudio handles resampling internally).
    """
    try:
        default_out = sd.query_devices(sd.default.device[1])
        logging.info(
            "sounddevice default output device: [%d] %s (%s channels, %.0f Hz default rate).",
            sd.default.device[1],
            default_out.get("name", "unknown"),
            default_out.get("max_output_channels", "?"),
            default_out.get("default_samplerate", 0),
        )
    except Exception:
        logging.info("sounddevice configured (default output device).")


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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """FastAPI lifespan: load Kokoro before accepting requests; set is_ready after warmup."""
    global is_ready, _kokoro_engine
    try:
        _configure_audio()
        _kokoro_engine = _load_and_warmup_kokoro()
        is_ready = True
        logging.info("Service ready. /health will return 200.")

        # Phase 1 proof: synthesize and play hardcoded audio to confirm full pipeline
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
        log_level="warning",
    )
    server = _BackgroundServer(config)
    thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
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
        _start_http_server()
        logging.info("HTTP daemon thread started. Waiting for lifespan startup...")
        # Phase 1: block main thread indefinitely.
        # Phase 4 replaces this with pystray Icon.run(setup=fn) on the main thread.
        threading.Event().wait()
    except Exception:
        logging.exception("Fatal error during startup")
        sys.exit(1)


if __name__ == "__main__":
    main()

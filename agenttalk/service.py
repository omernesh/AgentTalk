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
from typing import Literal

import queue
import time

import psutil
import sounddevice as sd
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import pystray

from agenttalk.tts_worker import TTS_QUEUE, STATE, start_tts_worker, _ducker
from agenttalk.tray import build_tray_icon
from agenttalk.config_loader import load_config, save_config, _config_dir
from agenttalk.preprocessor import preprocess

# ---------------------------------------------------------------------------
# Platform-aware paths (cross-platform via _config_dir())
# ---------------------------------------------------------------------------
APPDATA_DIR = _config_dir()
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

    text: str = Field(
        ...,
        description="Text to speak. Markdown is stripped automatically (bold, code blocks, URLs, etc.).",
        examples=["Hello, world! AgentTalk will speak this aloud."],
    )


class ConfigRequest(BaseModel):
    """Runtime configuration — all fields optional (partial update)."""

    voice: str | None = Field(
        None,
        description="Kokoro voice ID (only used when model='kokoro'). See GET /voices for the full list.",
        examples=["af_heart"],
    )
    speed: float | None = Field(
        None,
        description="Speech speed multiplier.",
        ge=0.5, le=2.0,
        examples=[1.0],
    )
    volume: float | None = Field(
        None,
        description="Playback volume (0.0 = silent, 1.0 = full).",
        ge=0.0, le=1.0,
        examples=[1.0],
    )
    model: Literal["kokoro", "piper"] | None = Field(
        None,
        description="TTS engine to use. 'kokoro' (default, high quality) or 'piper' (alternative, requires piper_model_path).",
        examples=["kokoro", "piper"],
    )
    muted: bool | None = Field(
        None,
        description="When true, audio playback is suppressed without affecting the queue.",
        examples=[False],
    )
    pre_cue_path: str | None = Field(
        None,
        description="Absolute path to a WAV/MP3 played before each TTS segment.",
        examples=["C:/sounds/ding.wav"],
    )
    post_cue_path: str | None = Field(
        None,
        description="Absolute path to a WAV/MP3 played after each TTS segment.",
        examples=["C:/sounds/done.wav"],
    )
    piper_model_path: str | None = Field(
        None,
        description="Absolute path to a Piper ONNX voice model (.onnx). Required when model='piper'.",
        examples=["C:/Users/user/AppData/Roaming/AgentTalk/models/piper/en_US-lessac-medium.onnx"],
    )
    speech_mode: Literal["auto", "semi-auto"] | None = Field(
        None,
        description="Speech mode: 'auto' (speak every reply) or 'semi-auto' (only speak when /speak is invoked).",
        examples=["auto", "semi-auto"],
    )


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


_DESCRIPTION = """
AgentTalk is a local Windows text-to-speech service supporting two offline TTS engines:

- **Kokoro ONNX** ([kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)) — default engine, high quality, 11 voices
- **Piper TTS** ([piper-tts](https://github.com/OHF-voice/piper1-gpl)) — alternative engine, switchable at runtime, multiple downloadable voice models

It accepts plain text or Markdown, preprocesses it into speakable sentences, and plays audio through your default output device.

## Integration

Any program can POST to `/speak` to queue text for playback:

```bash
curl -X POST http://localhost:5050/speak \\
     -H "Content-Type: application/json" \\
     -d '{"text": "Hello from your app!"}'
```

## Behaviour

- Text is **preprocessed**: Markdown stripped, code blocks removed, URLs removed, whitespace normalised.
- Audio is **queued** — multiple calls stack up and play in order (FIFO, max 10 items).
- If the queue is full the request is dropped with **429**; the caller may retry.
- While the TTS engine is loading all endpoints return **503**.

## Engine switching

Switch between Kokoro and Piper at runtime via `POST /config`:

```bash
# Switch to Piper
curl -X POST http://localhost:5050/config \\
     -H "Content-Type: application/json" \\
     -d '{"model": "piper", "piper_model_path": "C:/path/to/en_US-lessac-medium.onnx"}'

# Switch back to Kokoro
curl -X POST http://localhost:5050/config \\
     -H "Content-Type: application/json" \\
     -d '{"model": "kokoro"}'
```
"""

app = FastAPI(
    title="AgentTalk",
    description=_DESCRIPTION,
    version="1.0.0",
    contact={
        "name": "AgentTalk on GitHub",
        "url": "https://github.com/omernesh/AgentTalk",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=_lifespan,
)


@app.get(
    "/health",
    tags=["Status"],
    summary="Service health check",
    responses={
        200: {"description": "Service is ready and accepting requests."},
        503: {"description": "Kokoro model is still loading — retry shortly."},
    },
)
def health():
    """Returns `{"status": "ok"}` once the TTS engine has loaded and the worker is running.
    Returns `{"status": "initializing"}` with HTTP 503 while the model is loading (~5–15 s on first launch)."""
    if not is_ready:
        return JSONResponse({"status": "initializing"}, status_code=503)
    return JSONResponse({"status": "ok"}, status_code=200)


@app.get(
    "/voices",
    tags=["Status"],
    summary="List available Kokoro voices",
    responses={
        200: {"description": "List of Kokoro voice IDs (only applicable when model='kokoro')."},
    },
)
def list_voices():
    """Returns all Kokoro voice IDs that can be passed to `POST /config` as `voice`.
    These are only used when `model` is `kokoro`. For Piper voice models see `GET /piper-voices`."""
    from agenttalk.tray import KOKORO_VOICES
    return JSONResponse({"voices": KOKORO_VOICES})


@app.get(
    "/config",
    tags=["Configuration"],
    summary="Get current runtime settings",
    responses={
        200: {"description": "Current runtime configuration."},
    },
)
def get_config():
    """Returns the full current runtime state:
    - `voice`: active Kokoro voice ID (used when `model` is `kokoro`)
    - `model`: active TTS engine — `"kokoro"` or `"piper"`
    - `speed`: speech speed multiplier (0.5–2.0)
    - `volume`: playback volume (0.0–1.0)
    - `muted`: when true, synthesis is skipped entirely
    - `pre_cue_path` / `post_cue_path`: optional WAV paths played before/after each utterance
    - `piper_model_path`: absolute path to the active Piper ONNX model (used when `model` is `piper`)
    - `speech_mode`: `"auto"` (speak every reply) or `"semi-auto"` (only speak when /speak is invoked)
    """
    return JSONResponse({
        "voice":            STATE.get("voice"),
        "model":            STATE.get("model"),
        "speed":            STATE.get("speed"),
        "volume":           STATE.get("volume"),
        "muted":            STATE.get("muted"),
        "pre_cue_path":     STATE.get("pre_cue_path"),
        "post_cue_path":    STATE.get("post_cue_path"),
        "piper_model_path": STATE.get("piper_model_path"),
        "speech_mode":      STATE.get("speech_mode"),
    })


@app.get(
    "/piper-voices",
    tags=["Status"],
    summary="List downloaded Piper voice models",
    responses={
        200: {"description": "List of available Piper ONNX model stems in the models/piper directory."},
    },
)
def list_piper_voices():
    """Returns the stems of downloaded `.onnx` model files in `%APPDATA%/AgentTalk/models/piper/`
    (e.g. `en_US-lessac-medium`). To switch to a listed voice, POST the full path to `/config`:

    ```json
    {"piper_model_path": "<dir>/en_US-lessac-medium.onnx"}
    ```

    The `dir` field in the response contains the full directory path for convenience.
    Only applicable when `model` is `piper`."""
    piper_dir = MODELS_DIR / "piper"
    if not piper_dir.exists():
        return JSONResponse({"voices": [], "dir": str(piper_dir)})
    voices = sorted(p.stem for p in piper_dir.glob("*.onnx"))
    return JSONResponse({"voices": voices, "dir": str(piper_dir)})


@app.post(
    "/speak",
    tags=["TTS"],
    summary="Queue text for TTS playback",
    status_code=202,
    responses={
        202: {"description": "Text accepted and queued for playback."},
        200: {"description": "No speakable content after preprocessing (e.g. pure code, whitespace, or URLs only)."},
        429: {"description": "TTS queue is full — request dropped. Retry after a moment."},
        500: {"description": "Internal preprocessing error."},
        503: {"description": "Service not yet initialised — model still loading."},
    },
)
async def speak(req: SpeakRequest):
    """
    Accepts text (plain or Markdown), preprocesses it into speakable sentences,
    and enqueues each sentence individually for ordered playback.

    Each sentence is a separate queue item (str) so the first sentence begins
    playing as soon as it is synthesized, without waiting for later sentences.
    If the queue fills mid-loop the remaining sentences are dropped gracefully
    and the response includes dropped count.

    Preprocessing strips: fenced code blocks, inline code, Markdown links, bare URLs,
    headings, bold/italic, blockquotes, list markers, and excess whitespace.
    Text is then split into sentences via `pysbd` before queuing.
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

    queued = 0
    dropped = 0
    for sentence in sentences:
        try:
            TTS_QUEUE.put_nowait(sentence)
            queued += 1
        except queue.Full:
            dropped += 1
            logging.info(
                "TTS queue full - dropping %d remaining sentence(s).",
                len(sentences) - queued,
            )
            break

    if queued == 0:
        return JSONResponse(
            {"status": "dropped", "reason": "queue full"},
            status_code=429,
        )

    return JSONResponse(
        {"status": "queued", "sentences": queued, "dropped": dropped},
        status_code=202,
    )


@app.post(
    "/config",
    tags=["Configuration"],
    summary="Update runtime settings",
    status_code=200,
    responses={
        200: {"description": "Settings updated and persisted to config.json."},
        500: {"description": "Config file could not be saved (settings applied in-memory only)."},
    },
)
async def update_config(req: ConfigRequest):
    """
    Applies a partial runtime configuration update. All fields are optional — only
    the provided fields are changed. Settings take effect immediately and are persisted
    to `%APPDATA%\\AgentTalk\\config.json` so they survive service restarts.

    **Engine switching:** set `model` to `"piper"` and provide `piper_model_path` pointing to a
    downloaded `.onnx` file. The Piper engine is lazy-loaded on the next `/speak` request and
    reloaded automatically if `piper_model_path` changes. Switch back by setting `model` to `"kokoro"`.

    See `GET /piper-voices` for downloaded Piper models and `GET /voices` for Kokoro voice IDs.
    """
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return JSONResponse({"status": "ok", "updated": []})
    for key, value in updates.items():
        if key in STATE:
            STATE[key] = value
            logging.info("Config updated: %s = %s", key, value)
        else:
            logging.warning("Config update ignored — unknown STATE key: %s", key)
    try:
        save_config(STATE)
    except OSError:
        logging.exception("save_config() failed — config not persisted.")
        return JSONResponse({"status": "error", "reason": "config save failed"}, status_code=500)
    return JSONResponse({"status": "ok", "updated": list(updates.keys())})


@app.post(
    "/stop",
    tags=["Control"],
    summary="Stop audio and shut down the service",
    status_code=200,
    responses={
        200: {"description": "Service is stopping. The process will exit within ~100 ms."},
    },
)
async def stop_service():
    """
    Immediately silences any currently playing audio, then terminates the service process.
    The HTTP response is delivered before the process exits (~100 ms delay via daemon thread).
    The system-tray icon disappears once the process exits.
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
        for _key in ("voice", "speed", "volume", "model", "muted", "pre_cue_path", "post_cue_path", "piper_model_path", "speech_mode"):
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

        def _on_mute_change() -> None:
            """Called after every Mute toggle. Stops audio immediately when muting."""
            if STATE["muted"]:
                sd.stop()  # Interrupt the current sentence immediately
            try:
                save_config(STATE)
            except OSError:
                logging.warning("save_config() failed after mute toggle.", exc_info=True)

        def _on_config_change() -> None:
            """Called after model, kokoro voice, or piper voice selection from tray."""
            try:
                save_config(STATE)
            except OSError:
                logging.warning("save_config() failed after tray config change.", exc_info=True)

        # Build tray icon (does NOT run — just constructs the pystray.Icon object).
        # STATE is imported from tts_worker; tray menu reads muted, voice, model, and
        # piper_model_path from it. on_config_change persists all voice/model changes to disk.
        icon = build_tray_icon(
            state=STATE,
            on_quit=_on_quit,
            on_mute_change=_on_mute_change,
            on_config_change=_on_config_change,
        )

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

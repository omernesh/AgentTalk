"""
TTS worker module — bounded queue and daemon synthesis thread.

Provides a threading.Queue(maxsize=3) for backpressure, a STATE dict
for runtime volume/speed/voice/mute control, and a daemon thread that
consumes sentence lists, synthesizes via Kokoro, and plays audio.

Plan: 02-02 — TTS Worker + /speak Endpoint
Requirements: SVC-03, AUDIO-01, AUDIO-04, AUDIO-06, TTS-05

Phase 4 additions (Plan 04-02):
  - AudioDucker: ducks other audio sessions during TTS synthesis (AUDIO-07)
  - play_cue(): synchronous WAV cue playback before/after speech (CUE-01, CUE-02, CUE-03)
  - STATE["speaking"]: bool flag for tray icon speaking indicator (TRAY-03)
  - STATE["pre_cue_path"], STATE["post_cue_path"]: configurable cue paths (CUE-04)
  - Icon image swapping: speaking/idle indicator via tray icon (TRAY-03)
  - start_tts_worker(kokoro_engine, icon=None): icon reference for image swap

Phase 5 additions (Plan 05-01):
  - STATE["model"]: TTS engine selector — "kokoro" (default) or "piper" (TTS-04)
  - STATE["piper_model_path"]: absolute path to Piper ONNX model file (TTS-04)
  - Plan 05-02 adds _get_active_engine() dispatcher for runtime engine switching

CRITICAL: threading.Queue is used intentionally — NOT asyncio.Queue.
asyncio.Queue is not thread-safe and must not be used as the bridge
between FastAPI's async handlers and this blocking threading.Thread worker.
(Research pitfall #1.)

CRITICAL: kokoro.create() runs ONLY inside _tts_worker(). It is blocking
CPU work and must never be called in the async FastAPI handler.
(Research pitfall #2.)
"""

import logging
import queue
import threading
import winsound

import numpy as np
import sounddevice as sd

from agenttalk.audio_duck import AudioDucker
from agenttalk.tray import create_image_idle, create_image_speaking


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Bounded queue — maxsize=3 implements backpressure (AUDIO-04).
# put_nowait() raises queue.Full when full; handler returns 429.
TTS_QUEUE: queue.Queue = queue.Queue(maxsize=3)

# Runtime state dict — read at synthesis time so changes take effect
# on the NEXT sentence without service restart (AUDIO-06, TTS-05).
STATE: dict = {
    "volume": 1.0,              # 0.0–2.0; >1.0 clips via np.clip to protect speakers
    "speed": 1.0,               # 0.5–2.0; passed to kokoro.create(speed=...)
    "voice": "af_heart",        # Kokoro voice identifier
    "muted": False,             # Skip synthesis entirely when True
    "speaking": False,          # True while TTS is synthesizing/playing (TRAY-03)
    "pre_cue_path": None,       # Path to WAV file played before each utterance (CUE-01, CUE-03)
    "post_cue_path": None,      # Path to WAV file played after each utterance (CUE-02, CUE-03)
    "model": "kokoro",          # TTS engine: "kokoro" or "piper" (TTS-04)
    "piper_model_path": None,   # Absolute path to Piper ONNX model file (TTS-04)
}

# Module-level AudioDucker instance — shared between worker and atexit handler.
# Exported so service.py can register atexit(_ducker.unduck).
_ducker: AudioDucker = AudioDucker()

# Icon reference — set by start_tts_worker() when icon is available.
# If None, icon image swapping is skipped (safe for testing without tray).
_icon_ref = None

# Lazy-loaded Piper engine instance — None until STATE['model'] first switches to 'piper'.
# _get_active_engine() creates it on demand. Once loaded, reused for all subsequent Piper synthesis.
_piper_engine = None


# ---------------------------------------------------------------------------
# Engine dispatcher
# ---------------------------------------------------------------------------

def _get_active_engine(kokoro):
    """
    Return the active TTS engine based on STATE['model'].

    When model == 'kokoro' (default): returns the Kokoro engine passed as argument.
    When model == 'piper': lazy-loads PiperEngine on first call using STATE['piper_model_path'].

    Args:
        kokoro: The Kokoro engine instance (passed from _tts_worker via start_tts_worker).

    Returns:
        An engine with a create(text, voice, speed, lang) -> (samples, rate) interface.

    Raises:
        RuntimeError: If model == 'piper' and piper_model_path is not configured in STATE.
        ImportError: If model == 'piper' and piper-tts package is not installed.
        FileNotFoundError: If model == 'piper' and the model file does not exist.

    TTS-04: Piper TTS switchable at runtime via /agenttalk:model without service restart.
    CFG-03: STATE['model'] is updated by POST /config; next synthesis call uses new engine.
    """
    global _piper_engine
    model = STATE.get("model", "kokoro")
    if model == "piper":
        if _piper_engine is None:
            piper_path = STATE.get("piper_model_path")
            if not piper_path:
                raise RuntimeError(
                    "Piper model path not configured. "
                    "Run 'agenttalk setup --piper' to download a model, "
                    "or set piper_model_path in config.json."
                )
            from agenttalk.piper_engine import PiperEngine  # deferred — lazy load
            logging.info("Initialising Piper engine from %s", piper_path)
            _piper_engine = PiperEngine(piper_path)
        return _piper_engine
    # Default: Kokoro
    return kokoro


# ---------------------------------------------------------------------------
# Audio cue helper
# ---------------------------------------------------------------------------

def play_cue(path: str | None) -> None:
    """
    Play a WAV audio cue synchronously. No-op if path is None or empty.

    Uses winsound.SND_FILENAME (blocking) — the cue must finish before TTS begins.
    DO NOT use SND_ASYNC; async playback overlaps with speech synthesis.

    CUE-01, CUE-02, CUE-03: Optional pre/post cue playback.
    """
    if not path:
        return
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME)
    except FileNotFoundError:
        logging.error("Audio cue file not found: %s — check pre_cue_path/post_cue_path config", path)
    except Exception:
        logging.warning("Audio cue failed: %s", path, exc_info=True)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

def start_tts_worker(kokoro_engine, icon=None) -> threading.Thread:
    """
    Start the TTS daemon thread.

    Must be called from the FastAPI lifespan AFTER the Kokoro model is
    loaded and warmed up. The daemon flag ensures the thread does not
    prevent process exit.

    Args:
        kokoro_engine: Loaded Kokoro instance from kokoro_onnx.
        icon: Optional pystray.Icon reference for speaking state indicator (TRAY-03).
              If None, icon image swapping is skipped (safe for testing without tray).

    Returns:
        The started daemon Thread (for reference; callers need not manage it).
    """
    global _icon_ref
    _icon_ref = icon
    t = threading.Thread(
        target=_tts_worker,
        args=(kokoro_engine,),
        daemon=True,
        name="tts-worker",
    )
    t.start()
    logging.info(
        "TTS worker daemon thread started (icon=%s).", "yes" if icon else "none"
    )
    return t


def _swap_icon(image_fn, label: str) -> None:
    """Swap the tray icon image. No-op if no icon reference is set."""
    if _icon_ref is None:
        return
    try:
        _icon_ref.icon = image_fn()
    except Exception:
        logging.warning("Icon swap to %s failed (non-fatal).", label, exc_info=True)


def _tts_worker(kokoro_engine) -> None:
    """
    Blocking TTS synthesis loop — runs in daemon thread.

    Phase 4 additions: audio ducking (AUDIO-07), pre/post cues (CUE-01–04),
    speaking state flag (TRAY-03), icon image swapping (TRAY-03).

    Sequence per utterance batch:
      1. Check muted — skip entire batch if True
      2. Set speaking=True, swap icon to speaking image
      3. Play pre-cue (synchronous WAV, if configured)
      4. Duck other audio sessions
      5. Synthesize and play each sentence
      6. Unduck audio sessions
      7. Play post-cue (synchronous WAV, if configured)
      8. finally: set speaking=False, swap icon to idle, call task_done()

    The try/finally guarantees task_done() is always called, even on error.
    The 'continue' in the muted branch executes the finally block — correct Python behavior.
    """
    logging.info("TTS worker thread running.")
    while True:
        sentences: list[str] = TTS_QUEUE.get()
        try:
            if STATE["muted"]:
                logging.debug(
                    "TTS: muted — skipping batch of %d sentences.", len(sentences)
                )
                continue

            # TRAY-03: Notify tray icon that TTS is speaking
            STATE["speaking"] = True
            _swap_icon(create_image_speaking, "speaking")

            # CUE-01: Play pre-speech cue (synchronous — must finish before synthesis)
            play_cue(STATE.get("pre_cue_path"))

            # AUDIO-07: Duck other audio sessions
            _ducker.duck()

            engine = _get_active_engine(kokoro_engine)
            for sentence in sentences:
                if not sentence.strip():
                    continue

                logging.debug("TTS: synthesizing %r", sentence[:60])
                samples, rate = engine.create(
                    sentence,
                    voice=STATE["voice"],
                    speed=STATE["speed"],
                    lang="en-us",
                )

                # Apply volume scaling; clip to [-1.0, 1.0] if >1.0 to
                # prevent clipping distortion at the speaker/DAC level.
                scaled = samples * STATE["volume"]
                if STATE["volume"] > 1.0:
                    scaled = np.clip(scaled, -1.0, 1.0)

                sd.play(scaled, samplerate=rate)
                sd.wait()  # Block until this sentence finishes playing

            # AUDIO-07: Restore ducked sessions after all sentences finish
            _ducker.unduck()

            # CUE-02: Play post-speech cue
            play_cue(STATE.get("post_cue_path"))

        except Exception:
            logging.exception("TTS worker error — skipping batch.")
            # Ensure unduck on error path — prevents volumes stuck at 50% after crash
            if _ducker.is_ducked:
                try:
                    _ducker.unduck()
                except Exception:
                    logging.warning(
                        "Unduck on error path also failed.", exc_info=True
                    )
        finally:
            # TRAY-03: Always restore idle icon and clear speaking flag
            STATE["speaking"] = False
            _swap_icon(create_image_idle, "idle")
            TTS_QUEUE.task_done()

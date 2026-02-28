"""
TTS worker module — bounded queue and daemon synthesis thread.

Provides a threading.Queue(maxsize=10) for backpressure, a STATE dict
for runtime volume/speed/voice/mute control, and a daemon thread that
consumes individual str sentences, synthesizes via Kokoro or Piper, and
plays audio via sounddevice.

Each queue item is a single str sentence. The /speak endpoint enqueues
sentences one by one so audio on sentence 1 begins playing while sentence 2
is still queued (sentence-level TTS streaming).

CRITICAL: threading.Queue is used intentionally — NOT asyncio.Queue.
asyncio.Queue is not thread-safe for the bridge between FastAPI's async
handlers and this blocking daemon thread.

CRITICAL: kokoro.create() runs ONLY inside _tts_worker(). It is blocking
CPU work and must never be called in the async FastAPI handler.
"""

import logging
import platform
import queue
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

if platform.system() == "Windows":
    import winsound
    from agenttalk.audio_duck import AudioDucker
else:
    winsound = None  # type: ignore[assignment]

    class _NoOpDucker:
        """No-op stub used on non-Windows platforms where WASAPI ducking is unavailable."""

        def duck(self) -> None:
            pass

        def unduck(self) -> None:
            pass

        @property
        def is_ducked(self) -> bool:
            return False

    AudioDucker = _NoOpDucker  # type: ignore[misc,assignment]

from agenttalk.tray import create_image_idle, create_image_speaking


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _CueItem:
    """Sentinel queue item that plays a cue sound without triggering synthesis.

    The /speak handler pushes one _CueItem before sentences (pre_cue) and one
    after (post_cue) so cues fire exactly once per response, not per sentence.
    """
    path: str


# Bounded queue — maxsize=10 implements backpressure (AUDIO-04).
# Each item is a str sentence or a _CueItem sentinel (plays audio cue, no synthesis).
# /speak enqueues each sentence individually so sentence 1 plays immediately.
# put_nowait() raises queue.Full when full; handler returns 429.
TTS_QUEUE: queue.Queue = queue.Queue(maxsize=10)

# Runtime state dict — read at synthesis time so changes take effect
# on the NEXT sentence without service restart (AUDIO-06, TTS-05).
STATE: dict = {
    "volume": 1.0,              # 0.0–1.0; clipped via np.clip to protect speakers
    "speed": 1.0,               # 0.5–2.0; passed to kokoro.create(speed=...)
    "voice": "af_heart",        # Kokoro voice identifier
    "muted": False,             # Skip synthesis entirely when True
    "speaking": False,          # True while TTS is synthesizing/playing (TRAY-03)
    "pre_cue_path": None,       # Path to WAV file played before each utterance (CUE-01, CUE-03)
    "post_cue_path": None,      # Path to WAV file played after each utterance (CUE-02, CUE-03)
    "model": "kokoro",          # TTS engine: "kokoro" or "piper" (TTS-04)
    "piper_model_path": None,   # Absolute path to Piper ONNX model file (TTS-04)
    "speech_mode": "auto",      # "auto" (speak every reply) or "semi-auto" (only on /speak)
}

# Module-level AudioDucker instance — shared between worker and atexit handler.
# Exported so service.py can register atexit(_ducker.unduck).
_ducker: AudioDucker = AudioDucker()

# Icon reference — set by start_tts_worker() when icon is available.
# If None, icon image swapping is skipped (safe for testing without tray).
_icon_ref = None

# Consecutive synthesis failure counter — reset on each successful synthesis.
# Used by _notify_if_degraded() to surface repeated failures via tray notification.
_consecutive_failures: int = 0
_MAX_CONSECUTIVE_FAILURES = 3


def _notify_if_degraded(msg: str) -> None:
    """Send a tray notification once consecutive failure threshold is reached."""
    if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES and _icon_ref is not None:
        try:
            _icon_ref.notify(msg)
        except Exception:
            pass

# Lazy-loaded Piper engine instance — None until STATE['model'] first switches to 'piper'.
# _get_active_engine() creates it on demand and reloads it when piper_model_path changes.
_piper_engine = None
_piper_loaded_path: str | None = None  # tracks which .onnx is currently loaded


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
    global _piper_engine, _piper_loaded_path
    model = STATE.get("model", "kokoro")
    if model == "piper":
        piper_path = STATE.get("piper_model_path")
        if not piper_path:
            raise RuntimeError(
                "Piper model path not configured. "
                "Run 'agenttalk setup --piper' to download a model, "
                "or set piper_model_path in config.json."
            )
        if _piper_engine is None or _piper_loaded_path != piper_path:
            from agenttalk.piper_engine import PiperEngine  # deferred — lazy load
            logging.info("Initialising Piper engine from %s", piper_path)
            _piper_engine = PiperEngine(piper_path)
            _piper_loaded_path = piper_path
        return _piper_engine
    # Default: Kokoro
    return kokoro


# ---------------------------------------------------------------------------
# Audio cue helper
# ---------------------------------------------------------------------------

def play_cue(path: str | None) -> None:
    """
    Play a WAV audio cue synchronously. No-op if path is None or empty.

    Uses winsound.SND_FILENAME (blocking) on Windows — the cue must finish before TTS begins.
    DO NOT use SND_ASYNC; async playback overlaps with speech synthesis.
    On non-Windows platforms, cue playback is silently skipped (winsound unavailable).

    CUE-01, CUE-02, CUE-03: Optional pre/post cue playback.
    """
    if not path:
        return
    if winsound is None:
        logging.debug("Audio cue skipped on non-Windows platform: %s", path)
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

    Each queue item is a single str sentence. Duck/unduck and cue playback
    happen per sentence so the first sentence plays immediately after it is
    synthesized, without waiting for the full batch to queue up.

    Sequence per item:
      _CueItem: play the cue sound synchronously — no synthesis, no ducking.
      str sentence:
        1. Check muted — skip if True
        2. Skip if blank
        3. Set speaking=True, swap icon to speaking image
        4. Resolve active engine — raises on misconfiguration (before ducking)
        5. Duck other audio sessions
        6. Synthesize and play the sentence
        7. Unduck audio sessions
        8. else: reset consecutive failure counter
        9. finally: unduck if still ducked, set speaking=False, swap icon, task_done()

    Cues fire once per response because /speak pushes _CueItem sentinels before
    and after the sentence batch — not once per sentence.

    The try/finally guarantees task_done() is always called, even on error.
    The 'continue' in the muted/blank branches executes the finally block — correct Python.
    """
    global _consecutive_failures
    logging.info("TTS worker thread running.")
    while True:
        item = TTS_QUEUE.get()

        # Cue sentinel — play sound immediately, no synthesis.
        if isinstance(item, _CueItem):
            try:
                play_cue(item.path)
            finally:
                TTS_QUEUE.task_done()
            continue

        sentence: str = item
        ducked = False
        try:
            if STATE["muted"]:
                logging.debug("TTS: muted - skipping sentence.")
                continue
            if not sentence.strip():
                continue

            STATE["speaking"] = True
            _swap_icon(create_image_speaking, "speaking")

            # Resolve engine before ducking — avoids briefly silencing other apps
            # only to fail immediately after with a configuration error.
            engine = _get_active_engine(kokoro_engine)
            _ducker.duck()
            ducked = True

            logging.debug("TTS: synthesizing %r", sentence[:60])
            samples, rate = engine.create(
                sentence,
                voice=STATE["voice"],
                speed=STATE["speed"],
                lang="en-us",
            )
            scaled = np.clip(samples * STATE["volume"], -1.0, 1.0)
            sd.play(scaled, samplerate=rate)
            sd.wait()

            _ducker.unduck()
            ducked = False

        except (RuntimeError, FileNotFoundError, ImportError) as config_err:
            # Engine misconfiguration — actionable message, notify user after threshold.
            _consecutive_failures += 1
            logging.error(
                "TTS engine configuration error (failure %d): %s",
                _consecutive_failures, config_err,
            )
            _notify_if_degraded(f"AgentTalk: {config_err}")
        except Exception:
            _consecutive_failures += 1
            logging.exception(
                "TTS worker error (failure %d) — skipping sentence.", _consecutive_failures
            )
            _notify_if_degraded("AgentTalk: TTS synthesis failing. Check the log.")
        else:
            _consecutive_failures = 0  # reset on clean synthesis
        finally:
            if ducked:
                try:
                    _ducker.unduck()
                except Exception:
                    logging.warning("Unduck in finally failed.", exc_info=True)
            STATE["speaking"] = False
            _swap_icon(create_image_idle, "idle")
            TTS_QUEUE.task_done()

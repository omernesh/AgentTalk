"""
TTS worker module — bounded queue and daemon synthesis thread.

Provides a threading.Queue(maxsize=3) for backpressure, a STATE dict
for runtime volume/speed/voice/mute control, and a daemon thread that
consumes sentence lists, synthesizes via Kokoro, and plays audio.

Plan: 02-02 — TTS Worker + /speak Endpoint
Requirements: SVC-03, AUDIO-01, AUDIO-04, AUDIO-06, TTS-05

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

import numpy as np
import sounddevice as sd


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Bounded queue — maxsize=3 implements backpressure (AUDIO-04).
# put_nowait() raises queue.Full when full; handler returns 429.
TTS_QUEUE: queue.Queue = queue.Queue(maxsize=3)

# Runtime state dict — read at synthesis time so changes take effect
# on the NEXT sentence without service restart (AUDIO-06, TTS-05).
# Phase 4 /mute endpoint will toggle STATE["muted"].
STATE: dict = {
    "volume": 1.0,    # 0.0–2.0; >1.0 clips via np.clip to protect speakers
    "speed": 1.0,     # 0.5–2.0; passed to kokoro.create(speed=...)
    "voice": "af_heart",  # Kokoro voice identifier
    "muted": False,   # Skip synthesis entirely when True (Phase 4 use)
}


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

def start_tts_worker(kokoro_engine) -> threading.Thread:
    """
    Start the TTS daemon thread.

    Must be called from the FastAPI lifespan AFTER the Kokoro model is
    loaded and warmed up. The daemon flag ensures the thread does not
    prevent process exit.

    Args:
        kokoro_engine: Loaded Kokoro instance from kokoro_onnx.

    Returns:
        The started daemon Thread (for reference; callers need not manage it).
    """
    t = threading.Thread(
        target=_tts_worker,
        args=(kokoro_engine,),
        daemon=True,
        name="tts-worker",
    )
    t.start()
    logging.info("TTS worker daemon thread started.")
    return t


def _tts_worker(kokoro_engine) -> None:
    """
    Blocking TTS synthesis loop — runs in daemon thread.

    Consumes lists of sentences from TTS_QUEUE. For each sentence:
    synthesizes audio via Kokoro, applies volume scaling, plays via
    sounddevice, and waits for playback to finish before the next sentence.

    Error handling: synthesis errors on individual sentences are logged
    and skipped — the worker continues consuming from the queue.
    task_done() is always called in finally to unblock queue.join() callers.
    """
    logging.info("TTS worker thread running.")
    while True:
        sentences: list[str] = TTS_QUEUE.get()
        try:
            for sentence in sentences:
                if not sentence.strip():
                    continue
                if STATE["muted"]:
                    logging.debug("TTS: muted — skipping %r", sentence[:40])
                    continue

                logging.debug("TTS: synthesizing %r", sentence[:60])
                samples, rate = kokoro_engine.create(
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

        except Exception:
            logging.exception("TTS worker error on sentence — skipping batch.")
        finally:
            TTS_QUEUE.task_done()

"""
piper_engine.py — Thin wrapper around piper-tts (OHF-Voice/piper1-gpl) that
exposes the same interface as Kokoro:

    create(text, voice, speed, lang) -> (np.ndarray[float32], int sample_rate)

This allows tts_worker._get_active_engine() to return either Kokoro or PiperEngine
and call create() without branching on the engine type.

TTS-04: Piper TTS available as alternate engine, switchable at runtime via /agenttalk:model.

LAZY LOADING:
piper-tts is NOT imported at module level. PiperVoice.load() is called in __init__
only when PiperEngine is first instantiated (triggered by STATE['model'] == 'piper').
This prevents the 2-5s Piper init cost from affecting startup when Kokoro is the
active engine.

VOICE PARAMETER:
Piper uses the voice model baked into the .onnx file. The 'voice' parameter accepted
by create() is ignored — it exists only to match the Kokoro interface.

SAMPLE RATE:
Piper outputs 22050 Hz by default. The actual framerate is read from the synthesized
WAV buffer and returned as the second element of the create() tuple so that
sounddevice receives the correct sample rate automatically.

SPEED MAPPING:
Piper's SynthesisConfig.length_scale is the inverse of speech speed:
    length_scale = 1.0 / speed
A speed of 1.5 -> length_scale = 0.67 (faster).
A speed of 0.5 -> length_scale = 2.0 (slower).
Minimum speed is clamped to 0.1 to prevent division-by-zero.
"""
import io
import logging
import wave

import numpy as np


class PiperEngine:
    """
    Piper TTS engine wrapper with Kokoro-compatible interface.

    Args:
        model_path: Absolute path to a Piper ONNX voice model file
                    (e.g., %APPDATA%\\AgentTalk\\models\\piper\\en_US-lessac-medium.onnx).
                    The corresponding .json config file must exist at the same path
                    with a .json extension (piper-tts loads it automatically).

    Raises:
        FileNotFoundError: If model_path does not exist.
        ImportError: If piper-tts package is not installed (pip install piper-tts installs as 'piper' module).
    """

    def __init__(self, model_path: str):
        from piper import PiperVoice  # deferred import — lazy load
        logging.info("Loading Piper model from %s ...", model_path)
        self._voice = PiperVoice.load(model_path)
        self._sample_rate = 22050  # Piper default; updated from actual WAV framerate after first synthesis
        logging.info("Piper model loaded.")

    def create(
        self,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> tuple[np.ndarray, int]:
        """
        Synthesize text to audio samples.

        Args:
            text:  Text to synthesize.
            voice: Ignored — Piper uses the model's built-in voice.
            speed: Speech speed multiplier (0.1-2.0). Mapped to length_scale = 1/speed.
            lang:  Ignored — Piper language is determined by the model.

        Returns:
            (samples, sample_rate):
                samples: np.ndarray[float32] in range [-1.0, 1.0]
                sample_rate: int (typically 22050 Hz for Piper)
        """
        from piper import SynthesisConfig  # deferred import

        # Clamp speed to avoid division-by-zero
        safe_speed = max(float(speed), 0.1)
        cfg = SynthesisConfig(length_scale=1.0 / safe_speed)

        # Synthesize to an in-memory WAV buffer
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self._voice.synthesize_wav(text, wf, syn_config=cfg)

        # Read back: extract raw PCM bytes and actual sample rate
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            if wf.getnframes() == 0:
                raise RuntimeError(
                    f"Piper synthesized zero frames for: {text[:60]!r}"
                )
            raw = wf.readframes(wf.getnframes())
            self._sample_rate = wf.getframerate()

        # Convert int16 PCM -> float32 in [-1.0, 1.0]
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return samples, self._sample_rate

"""
hebrewpiper_engine.py — Hebrew TTS via the PiperStream REST API.

Wraps the PiperStream Docker service (github.com/maxmelichov/PiperStream) to
provide Hebrew TTS with the same interface as Kokoro and PiperEngine:

    create(text, voice, speed, lang) -> (np.ndarray[float32], int sample_rate)

PiperStream pipeline:
    raw Hebrew text -> phonikud (auto diacritization) -> Piper ONNX inference -> WAV (22050 Hz)

Two voices: "male" (piper_medium_male.onnx), "female" (piper_medium_female.onnx).

Requires:
    docker compose up  (in a clone of https://github.com/maxmelichov/PiperStream)
    Download onnx.zip from the repo and place model files as described in the repo README.

No new Python dependencies beyond the existing `requests` library.

Speed mapping: length_scale = 1.0 / speed (same as PiperEngine).
"""
import io
import logging
import wave

import numpy as np


class HebrewPiperEngine:
    """
    Hebrew TTS engine wrapper around the PiperStream Docker REST API.

    Provides a Kokoro-compatible interface:
        create(text, voice, speed, lang) -> (np.ndarray[float32], int sample_rate)

    The engine does NOT make any network calls in __init__ — the first network
    request happens inside create() (lazy health check on first synthesis call).

    Args:
        host:  Base URL for the PiperStream service. Default: "http://localhost:8000".
               Trailing slashes are stripped automatically.
        voice: Default Hebrew voice to use. Either "male" or "female". Default: "female".
               Can be overridden per-call via create(voice=...).
    """

    def __init__(self, host: str = "http://localhost:8000", voice: str = "female"):
        self._host = host.rstrip("/")
        self._voice = voice
        logging.info("HebrewPiperEngine initialized, host=%s voice=%s", self._host, self._voice)

    def create(
        self,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
        lang: str = "he",
    ) -> tuple[np.ndarray, int]:
        """
        Synthesize Hebrew text to audio samples via PiperStream.

        Args:
            text:  Hebrew text to synthesize.
            voice: Voice override. Either "male" or "female". If None, uses the
                   engine's default voice set in __init__.
            speed: Speech speed multiplier (0.1-2.0). Mapped to length_scale = 1/speed.
                   A speed of 1.5 -> length_scale = 0.67 (faster).
            lang:  Ignored — PiperStream handles Hebrew diacritization automatically.

        Returns:
            (samples, sample_rate):
                samples: np.ndarray[float32] in range [-1.0, 1.0]
                sample_rate: int (typically 22050 Hz as provided in WAV header)

        Raises:
            RuntimeError: If PiperStream is not reachable (Docker not running).
            RuntimeError: If PiperStream returns a non-200 HTTP response.
        """
        import requests  # deferred — already in project deps

        effective_voice = voice if voice is not None else self._voice
        # Same speed-to-length_scale mapping as PiperEngine
        length_scale = 1.0 / max(float(speed), 0.1)
        payload = {"text": text, "model": effective_voice, "length_scale": length_scale}

        url = f"{self._host}/synthesize/audio"
        try:
            r = requests.post(url, json=payload, timeout=30)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"PiperStream not reachable at {self._host}. "
                "Start Docker: cd PiperStream && docker compose up"
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"PiperStream request timed out after 30 s (host={self._host}). "
                "The service may be overloaded or the Docker container is not responding."
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"PiperStream request failed: {exc}"
            ) from exc

        if r.status_code != 200:
            raise RuntimeError(
                f"PiperStream /synthesize/audio returned {r.status_code}: {r.text[:200]}"
            )

        # Parse WAV bytes from the response body
        buf = io.BytesIO(r.content)
        try:
            wf = wave.open(buf, "rb")
        except wave.Error as exc:
            raise RuntimeError(
                f"PiperStream returned invalid WAV data: {exc}"
            ) from exc
        with wf:
            if wf.getnframes() == 0:
                raise RuntimeError(
                    f"PiperStream synthesized zero frames for: {text[:60]!r}"
                )
            sampwidth = wf.getsampwidth()
            if sampwidth != 2:
                raise RuntimeError(
                    f"PiperStream returned unexpected sample width {sampwidth} bytes "
                    f"(expected 2 for int16 PCM)."
                )
            raw_pcm = wf.readframes(wf.getnframes())
            sample_rate = wf.getframerate()

        # Convert int16 PCM -> float32 in [-1.0, 1.0]
        samples = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
        return samples, sample_rate

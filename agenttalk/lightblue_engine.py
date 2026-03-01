"""
lightblue_engine.py — Hebrew TTS via Light-BlueTTS (local Python inference).

Wraps the Light-BlueTTS library (github.com/maxmelichov/Light-BlueTTS) to provide
Hebrew TTS with the same interface as Kokoro and PiperEngine:

    create(text, voice, speed, lang) -> (np.ndarray[float32], int sample_rate)

Light-BlueTTS performs local inference — no Docker or network service required.
Output sample rate: 44100 Hz (fixed).

Voices: Style JSON files in the voices/ directory of the cloned repository
(e.g., voices/female1.json). Pass the absolute path to create(voice=...).

Requires (OPTIONAL — NOT in core requirements due to ~2GB torch dependency):
    pip install onnxruntime phonikud phonikud-onnx soundfile torch torchaudio
    AND cloning https://github.com/maxmelichov/Light-BlueTTS to get:
      - onnx_models/   (9 ONNX files: backbone, text_encoder, vocoder, etc.)
      - phonikud-1.0.onnx
      - voices/        (style JSON files for each voice)
    Then add the repo root to PYTHONPATH so `hebrew_inference_helper` is importable.

Heavy dependencies: torch (~2GB) — this engine is optional. All imports are
deferred inside __init__ so the module imports cleanly without torch installed.

Speed handling: Light-BlueTTS bakes speed into TTSConfig at instantiation. If
speed changes between calls, the engine is reloaded with the new TTSConfig
(rare operation — speed changes are uncommon in practice).
"""
import logging

import numpy as np


class LightBlueTTSEngine:
    """
    Light-BlueTTS engine wrapper with Kokoro-compatible interface.

    All heavy imports (hebrew_inference_helper, torch, onnxruntime) are deferred
    to __init__ so the module can be imported without torch installed. Only when
    LightBlueTTSEngine() is instantiated do the heavy deps get loaded.

    Args:
        onnx_dir:       Absolute path to the onnx_models/ directory in the
                        cloned Light-BlueTTS repository.
        phonikud_path:  Absolute path to phonikud-1.0.onnx. Defaults to
                        "phonikud-1.0.onnx" (current working directory).
        speed:          Initial speech speed. Baked into TTSConfig at load time.
        use_gpu:        Whether to use GPU inference. Default: False.

    Raises:
        ImportError: If Light-BlueTTS / hebrew_inference_helper is not installed
                     or not on PYTHONPATH.
    """

    def __init__(
        self,
        onnx_dir: str,
        phonikud_path: str = "phonikud-1.0.onnx",
        speed: float = 1.0,
        use_gpu: bool = False,
    ):
        try:
            from hebrew_inference_helper import HebrewTTS, TTSConfig  # deferred import
        except ImportError:
            raise ImportError(
                "Light-BlueTTS not installed. Install deps:\n"
                "  pip install onnxruntime phonikud phonikud-onnx soundfile torch torchaudio\n"
                "Then clone https://github.com/maxmelichov/Light-BlueTTS and add it to PYTHONPATH.\n"
                "  Windows: set PYTHONPATH=C:\\path\\to\\Light-BlueTTS\n"
                "  macOS/Linux: export PYTHONPATH=/path/to/Light-BlueTTS"
            )

        config = TTSConfig(
            onnx_dir=onnx_dir,
            phonikud_path=phonikud_path,
            speed=speed,
            use_gpu=use_gpu,
        )
        self._tts = HebrewTTS(config)
        self._speed = speed
        self._onnx_dir = onnx_dir
        self._phonikud_path = phonikud_path
        self._use_gpu = use_gpu
        logging.info("LightBlueTTSEngine loaded from %s", onnx_dir)

    def create(
        self,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
        lang: str = "he",
    ) -> tuple[np.ndarray, int]:
        """
        Synthesize Hebrew text to audio samples using Light-BlueTTS.

        Args:
            text:  Hebrew text to synthesize.
            voice: Absolute path to a voices/*.json style file. Required — pass
                   the absolute path via POST /config lightblue_voice_path.
            speed: Speech speed multiplier. NOTE: speed is baked into TTSConfig,
                   so changing speed requires engine reload (logged as a warning).
                   Changing speed frequently is not recommended.
            lang:  Ignored — Light-BlueTTS handles Hebrew exclusively.

        Returns:
            (samples, 44100):
                samples: np.ndarray[float32] — Light-BlueTTS always returns float32
                44100: int — Light-BlueTTS always outputs at 44100 Hz

        Raises:
            RuntimeError: If voice is None (lightblue_voice_path not configured).
            RuntimeError: If inference fails (bad voice file, model error, OOM, etc.).
            ImportError: If Light-BlueTTS is not installed (raised at __init__ time,
                         not here — but documented for completeness).
        """
        if voice is None:
            raise RuntimeError(
                "LightBlueTTS voice path not configured. "
                "POST /config with lightblue_voice_path set to an absolute path "
                "to a voices/*.json file (e.g. C:/Light-BlueTTS/voices/female1.json)."
            )

        # Speed is baked into TTSConfig — reload if speed changes
        if abs(speed - self._speed) > 1e-9:
            logging.warning(
                "LightBlueTTSEngine: speed change from %.2f to %.2f requires engine reload.",
                self._speed,
                speed,
            )
            # Import cannot fail here — __init__ already verified the library is present.
            from hebrew_inference_helper import HebrewTTS, TTSConfig
            config = TTSConfig(
                onnx_dir=self._onnx_dir,
                phonikud_path=self._phonikud_path,
                speed=speed,
                use_gpu=self._use_gpu,
            )
            try:
                self._tts = HebrewTTS(config)
            except Exception as exc:
                raise RuntimeError(
                    f"LightBlueTTSEngine: failed to reload with speed={speed}: {exc}"
                ) from exc
            self._speed = speed

        try:
            wav = self._tts.infer(text, style_json_path=voice)
        except Exception as exc:
            raise RuntimeError(
                f"LightBlueTTS inference failed for text {text[:60]!r} "
                f"(voice={voice!r}): {exc}"
            ) from exc

        # Light-BlueTTS always outputs 44100 Hz float32 ndarray
        return wav, 44100

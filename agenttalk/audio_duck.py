"""
audio_duck.py — Per-session audio ducking via Windows Core Audio API (pycaw).

Provides AudioDucker class with duck() and unduck() methods. When called,
duck() lowers all non-AgentTalk Windows audio sessions to 50% of their
current volume. unduck() restores them to their pre-duck levels.

Design decisions:
  - COM initialization: comtypes.CoInitialize/CoUninitialize is called on
    every duck()/unduck() call because the TTS worker is a daemon thread where
    COM is not initialized automatically (research pitfall #2).
  - Best-effort: pycaw errors are logged as warnings and do NOT propagate —
    a ducking failure must never crash the TTS worker (research pitfall #4).
  - Session identity: keyed by process name (str). Sessions created/destroyed
    between duck() and unduck() are accepted as an edge case (research open Q #2).
  - No pystray coupling: this module must NOT import tray.py.

Requirements: AUDIO-07
"""
import logging

import comtypes
from pycaw.pycaw import AudioUtilities


class AudioDucker:
    """
    Lowers all non-AgentTalk Windows audio sessions to 50% during TTS playback.

    Usage:
        ducker = AudioDucker()
        ducker.duck()     # Call before TTS synthesis
        # ... TTS playback ...
        ducker.unduck()   # Call after TTS playback; restores saved volumes

    Thread safety: duck() and unduck() are called from the TTS worker thread.
    COM is initialized per-call via CoInitialize/CoUninitialize.

    Export: AudioDucker is imported by tts_worker.py and registered as an
    atexit handler in service.py via `from agenttalk.tts_worker import _ducker`.
    """

    def __init__(self) -> None:
        # Maps process_name -> original volume before ducking.
        # Cleared by unduck() after restoration.
        self._saved: dict[str, float] = {}

    @property
    def is_ducked(self) -> bool:
        """True if duck() has been called and saved volumes are pending restoration."""
        return bool(self._saved)

    def duck(self) -> None:
        """
        Lower all non-AgentTalk audio sessions to 50%. Best-effort — logs on failure.

        Sequence:
          1. CoInitialize() — required in non-main threads
          2. Enumerate all audio sessions
          3. Skip sessions with no Process (System Sounds)
          4. Skip python.exe / pythonw.exe (our own process)
          5. Save current volume, set to original * 0.5
          6. CoUninitialize() — always, even on error

        AUDIO-07: Ducking other apps so AgentTalk speech is prominent.
        """
        comtypes.CoInitialize()
        try:
            self._saved.clear()
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process is None:
                    continue  # System Sounds session — skip
                name = session.Process.name()
                if name.lower() in ("python.exe", "pythonw.exe"):
                    continue  # Skip ourselves
                vol = session.SimpleAudioVolume
                original = vol.GetMasterVolume()
                if original > 0.0:
                    self._saved[name] = original
                    vol.SetMasterVolume(original * 0.5, None)
                    logging.debug(
                        "Ducked %s: %.2f → %.2f", name, original, original * 0.5
                    )
        except Exception:
            logging.warning(
                "Audio ducking failed — continuing without duck.", exc_info=True
            )
        finally:
            comtypes.CoUninitialize()

    def unduck(self) -> None:
        """
        Restore all previously ducked sessions to saved volume.

        No-op if duck() was not called or had nothing to save (avoids
        unnecessary COM initialization when there are no ducked sessions).

        AUDIO-07: Restoring audio after TTS speech finishes.
        """
        if not self._saved:
            return  # Nothing was ducked — skip COM initialization entirely
        comtypes.CoInitialize()
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process is None:
                    continue
                name = session.Process.name()
                if name in self._saved:
                    vol = session.SimpleAudioVolume
                    vol.SetMasterVolume(self._saved[name], None)
                    logging.debug("Restored %s → %.2f", name, self._saved[name])
            self._saved.clear()
        except Exception:
            logging.warning("Audio un-ducking failed.", exc_info=True)
        finally:
            comtypes.CoUninitialize()

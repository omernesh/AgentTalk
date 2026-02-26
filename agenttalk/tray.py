"""
tray.py — System tray icon for AgentTalk.

Provides:
  - create_image_idle(): Dark navy circle with blue waveform bars (64x64).
  - create_image_speaking(): Dark green circle with bright waveform bars (64x64).
  - build_tray_icon(state, on_quit): Constructs pystray.Icon with full right-click menu.

IMPORTANT: build_tray_icon() does NOT call icon.run() or set icon.visible.
Both are done by service.py's _setup() callback (research pattern #1).

Requirements: TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05, TRAY-06
"""
import logging
import os
from pathlib import Path
from typing import Callable

import pystray
from PIL import Image, ImageDraw


# All Kokoro voice identifiers (TRAY-04 — Voice submenu)
KOKORO_VOICES = [
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis",
]


def _draw_waveform(
    dc: ImageDraw.ImageDraw,
    size: int,
    bar_color: tuple,
    heights_frac: list[float],
) -> None:
    """Draw 5 equalizer bars centered in the icon canvas."""
    n = 5
    bar_w = max(2, round(size * 0.078))   # ~5px at 64,  ~20px at 256
    gap    = max(1, round(size * 0.063))   # ~4px at 64,  ~16px at 256
    total_w = n * bar_w + (n - 1) * gap
    x0 = (size - total_w) // 2
    for i, frac in enumerate(heights_frac):
        h = max(2, round(size * frac))
        x = x0 + i * (bar_w + gap)
        y = (size - h) // 2
        dc.rectangle([x, y, x + bar_w - 1, y + h - 1], fill=bar_color)


def create_image_idle(size: int = 64) -> Image.Image:
    """
    Dark navy circle with five blue equalizer bars — idle state.

    CRITICAL: Size MUST default to 64. PIL images smaller than ~20px trigger
    "OSError: [WinError 0]" in pystray's LoadImage call (research pitfall #5).
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([0, 0, size - 1, size - 1], fill=(14, 27, 44, 255))
    _draw_waveform(dc, size, (91, 200, 245, 255), [0.19, 0.31, 0.47, 0.31, 0.19])
    return image


def create_image_speaking(size: int = 64) -> Image.Image:
    """
    Dark green circle with taller bright-green bars — TTS actively playing.

    CRITICAL: Size MUST default to 64 (see create_image_idle note).
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([0, 0, size - 1, size - 1], fill=(10, 44, 28, 255))
    _draw_waveform(dc, size, (46, 213, 115, 255), [0.28, 0.47, 0.69, 0.47, 0.28])
    return image


def _piper_dir() -> Path:
    """Return the Piper models directory path."""
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(appdata) / "AgentTalk" / "models" / "piper"


def build_tray_icon(
    state: dict,
    on_quit: Callable[[], None] | None = None,
    on_mute_change: Callable[[], None] | None = None,
    on_config_change: Callable[[], None] | None = None,
) -> pystray.Icon:
    """
    Build and return a pystray.Icon with the AgentTalk tray menu.

    Does NOT call icon.run() — that is service.py's responsibility.
    Does NOT set icon.visible — that must be done inside the setup callback.

    Args:
        state: Shared mutable dict with keys 'muted' (bool), 'voice' (str),
               'model' (str: 'kokoro' or 'piper'), and 'piper_model_path' (str|None).
               The tray menu reads and writes these keys in real time.
        on_quit: Optional callable invoked when the user selects Quit.
                 Called before icon.stop(). Use for cleanup (e.g., audio unduck).
        on_mute_change: Optional callable invoked after every Mute toggle.
                        Use for save_config() and immediate audio stop.
        on_config_change: Optional callable invoked after model, kokoro voice, or
                          piper voice selection from tray. Use for save_config(STATE).
                          Defaults to None so service.py call sites without this
                          parameter continue to compile without modification.

    Returns:
        pystray.Icon ready to be passed to icon.run(setup=fn).

    Menu structure (TRAY-02, TRAY-04, TRAY-05, TRAY-06):
      1. Mute — toggle with checkmark reflecting state['muted']
      2. Model — submenu: kokoro / piper radio buttons
      3. Voice — submenu: context-aware (Kokoro voices or Piper .onnx stems)
      4. Active: {voice/stem} — read-only info item (enabled=False)
      5. --- separator ---
      6. Quit — calls on_quit() then icon.stop()
    """

    def _invoke_config_change() -> None:
        """Invoke on_config_change with exception guard. No-op when callback is None."""
        if on_config_change is not None:
            try:
                on_config_change()
            except Exception:
                logging.warning("on_config_change callback raised exception", exc_info=True)

    def _toggle_mute(icon, item=None):
        state["muted"] = not state["muted"]
        if on_mute_change is not None:
            try:
                on_mute_change()
            except Exception:
                logging.warning("on_mute_change callback raised exception", exc_info=True)
        icon.update_menu()

    def _set_voice(voice):
        def _inner(icon, item):
            state["voice"] = voice
            _invoke_config_change()
            icon.update_menu()
        return _inner

    def _set_model(model):
        def _inner(icon, item):
            state["model"] = model
            _invoke_config_change()
            icon.update_menu()
        return _inner

    def _set_piper_voice(full_path: str):
        """Select a Piper voice: set piper_model_path and switch to piper model."""
        def _inner(icon, item):
            state["piper_model_path"] = full_path
            state["model"] = "piper"
            _invoke_config_change()
            icon.update_menu()
        return _inner

    def _quit(icon, item=None):
        if on_quit is not None:
            try:
                on_quit()
            except Exception:
                logging.warning("on_quit callback raised exception", exc_info=True)
        icon.stop()

    def _voice_items():
        """Generate Voice submenu items based on active model. Called at menu render time."""
        if state.get("model", "kokoro") == "piper":
            piper_path = _piper_dir()
            if piper_path.exists():
                onnx_files = sorted(piper_path.glob("*.onnx"))
            else:
                onnx_files = []
            if not onnx_files:
                yield pystray.MenuItem(
                    "No Piper models found",
                    lambda icon, item: None,
                    enabled=False,
                )
                return
            for onnx_path in onnx_files:
                stem = onnx_path.stem
                full_path = str(onnx_path)
                yield pystray.MenuItem(
                    stem,
                    _set_piper_voice(full_path),
                    checked=lambda item, p=full_path: state.get("piper_model_path") == p,
                    radio=True,
                )
        else:
            # Kokoro mode — static list
            for voice in KOKORO_VOICES:
                yield pystray.MenuItem(
                    voice,
                    _set_voice(voice),
                    checked=lambda item, v=voice: state["voice"] == v,
                    radio=True,
                )

    menu = pystray.Menu(
        # TRAY-02: Mute toggle with dynamic checkmark
        pystray.MenuItem(
            "Mute",
            _toggle_mute,
            checked=lambda item: state["muted"],
        ),
        # Model submenu — radio buttons for kokoro / piper engine selection
        pystray.MenuItem(
            "Model",
            pystray.Menu(
                pystray.MenuItem(
                    "kokoro",
                    _set_model("kokoro"),
                    checked=lambda item: state.get("model", "kokoro") == "kokoro",
                    radio=True,
                ),
                pystray.MenuItem(
                    "piper",
                    _set_model("piper"),
                    checked=lambda item: state.get("model", "kokoro") == "piper",
                    radio=True,
                ),
            ),
        ),
        # TRAY-04: Voice submenu — context-aware (Kokoro voices or Piper .onnx stems)
        pystray.MenuItem(
            "Voice",
            pystray.Menu(_voice_items),
        ),
        # TRAY-06: Active voice/model info item — read-only, always disabled
        # NOTE: action must be a no-op lambda, NOT None — bare None causes TypeError
        # in some pystray versions (research pitfall #3).
        pystray.MenuItem(
            lambda item: (
                f'Active: {Path(state["piper_model_path"]).stem}'
                if state.get("model") == "piper" and state.get("piper_model_path")
                else f'Active: {state["voice"]}'
            ),
            lambda icon, item: None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        # TRAY-05: Quit item
        pystray.MenuItem("Quit", _quit),
    )

    return pystray.Icon(
        "AgentTalk",
        icon=create_image_idle(),
        title="AgentTalk",
        menu=menu,
    )

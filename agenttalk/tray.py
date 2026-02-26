"""
tray.py — System tray icon for AgentTalk.

Provides:
  - create_image_idle(): Blue circle PIL image (64x64) for idle state.
  - create_image_speaking(): Orange/red circle PIL image (64x64) for speaking state.
  - build_tray_icon(state, on_quit): Constructs pystray.Icon with full right-click menu.

IMPORTANT: build_tray_icon() does NOT call icon.run() or set icon.visible.
Both are done by service.py's _setup() callback (research pattern #1).

Requirements: TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05, TRAY-06
"""
import logging
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


def create_image_idle(size: int = 64) -> Image.Image:
    """
    Blue circle — idle state icon.

    CRITICAL: Size MUST default to 64. PIL images smaller than ~20px trigger
    "OSError: [WinError 0]" in pystray's LoadImage call (research pitfall #5).
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, size - 4, size - 4], fill=(30, 120, 200, 255))
    return image


def create_image_speaking(size: int = 64) -> Image.Image:
    """
    Orange/red circle — TTS actively playing.

    CRITICAL: Size MUST default to 64 (see create_image_idle note).
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, size - 4, size - 4], fill=(220, 80, 20, 255))
    return image


def build_tray_icon(state: dict, on_quit: Callable[[], None] | None = None) -> pystray.Icon:
    """
    Build and return a pystray.Icon with the AgentTalk tray menu.

    Does NOT call icon.run() — that is service.py's responsibility.
    Does NOT set icon.visible — that must be done inside the setup callback.

    Args:
        state: Shared mutable dict with keys 'muted' (bool) and 'voice' (str).
               The tray menu reads and writes these keys in real time.
        on_quit: Optional callable invoked when the user selects Quit.
                 Called before icon.stop(). Use for cleanup (e.g., audio unduck).

    Returns:
        pystray.Icon ready to be passed to icon.run(setup=fn).

    Menu structure (TRAY-02, TRAY-04, TRAY-05, TRAY-06):
      1. Mute — toggle with checkmark reflecting state['muted']
      2. Voice — submenu with radio buttons for each KOKORO voice
      3. Active: {voice} — read-only info item (enabled=False)
      4. --- separator ---
      5. Quit — calls on_quit() then icon.stop()
    """

    def _toggle_mute(icon, item=None):
        state["muted"] = not state["muted"]
        icon.update_menu()

    def _set_voice(voice):
        def _inner(icon, item):
            state["voice"] = voice
            icon.update_menu()
        return _inner

    def _quit(icon, item=None):
        if on_quit is not None:
            try:
                on_quit()
            except Exception:
                logging.warning("on_quit callback raised exception", exc_info=True)
        icon.stop()

    menu = pystray.Menu(
        # TRAY-02: Mute toggle with dynamic checkmark
        pystray.MenuItem(
            "Mute",
            _toggle_mute,
            checked=lambda item: state["muted"],
        ),
        # TRAY-04: Voice submenu — radio buttons for each Kokoro voice
        pystray.MenuItem(
            "Voice",
            pystray.Menu(lambda: (
                pystray.MenuItem(
                    voice,
                    _set_voice(voice),
                    checked=lambda item, v=voice: state["voice"] == v,
                    radio=True,
                )
                for voice in KOKORO_VOICES
            )),
        ),
        # TRAY-06: Active voice info item — read-only, always disabled
        # NOTE: action must be a no-op lambda, NOT None — bare None causes TypeError
        # in some pystray versions (research pitfall #3).
        pystray.MenuItem(
            lambda item: f'Active: {state["voice"]}',
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

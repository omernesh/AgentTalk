# Phase 4: System Tray UX, Audio Ducking, and Cues - Research

**Researched:** 2026-02-26
**Domain:** Windows system tray (pystray), Windows Core Audio session management (pycaw), audio cue playback (winsound)
**Confidence:** MEDIUM-HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SVC-04 | pystray tray icon runs on the main thread (Win32 message loop requirement) | `Icon.run(setup=fn)` pattern — setup fn spawns daemon threads, main thread is surrendered to pystray |
| TRAY-01 | Service icon visible in Windows system tray while running | `pystray.Icon` with PIL image; `icon.visible = True` in setup callback |
| TRAY-02 | Right-click menu: Mute/Unmute (checkmark), voice submenu, Quit | `pystray.Menu` + `MenuItem(checked=lambda item: state)` + nested `Menu` for submenu |
| TRAY-03 | Tray icon changes appearance while TTS is actively speaking | Replace `icon.icon` property at runtime — PIL image swap; thread-safe via `threading.Event` signalling |
| TRAY-04 | Voice submenu listing all available Kokoro voices | Dynamic `Menu(lambda: ...)` generator pattern returns `MenuItem` per voice with radio=True |
| TRAY-05 | Quit action cleanly shuts down the service | `icon.stop()` + `os._exit(0)` or `sys.exit()` from menu callback |
| TRAY-06 | Current active voice name shown as disabled informational item | `MenuItem(text=lambda item: STATE["voice"], enabled=False)` |
| AUDIO-07 | Other audio streams duck to 50% during TTS; restore after | `pycaw` — `AudioUtilities.GetAllSessions()` + `ISimpleAudioVolume.GetMasterVolume/SetMasterVolume` per session |
| CUE-01 | User-configurable pre-speech audio file plays before TTS | `winsound.PlaySound(path, SND_FILENAME)` — synchronous, blocks until file finishes |
| CUE-02 | User-configurable post-speech audio file plays after TTS | `winsound.PlaySound(path, SND_FILENAME)` — synchronous, blocks until file finishes |
| CUE-03 | Pre/post cues optional — when not set, no sound plays | Conditional check: `if STATE["pre_cue_path"]` before calling PlaySound |
| CUE-04 | Cue paths configurable via config.json | Read from config at synthesis time; changes take effect on next utterance |
</phase_requirements>

---

## Summary

Phase 4 adds three distinct capabilities on top of the Phase 1-3 service: a system tray icon (pystray), audio ducking of other Windows audio sessions during TTS (pycaw), and optional pre/post audio cue playback (winsound). These three concerns are largely independent of each other but all need to integrate with the existing `STATE` dict and `_tts_worker` thread in `tts_worker.py`.

The critical architectural constraint is **thread ownership**: pystray's `Icon.run()` must hold the main thread (on Windows this is not strictly required but is the correct cross-platform approach and matches what Phase 1's service.py already planned for — replacing `threading.Event().wait()` with `icon.run(setup=fn)`). The existing uvicorn daemon thread and TTS worker daemon thread continue running as-is; pystray's `setup=fn` callback spawns them.

The Python version blocker from STATE.md (`pystray GIL crash on 3.12+`) needs resolution before Phase 4 can proceed. The project is currently using Python 3.12 on dev and must either install Python 3.11 or test whether the specific GIL crash occurs in the pystray `_win32` backend under the project's actual usage pattern (no PyGame, no PySimpleGUI). Research finds the crash is documented with PySimpleGUI+psgtray+PyGame stack — pure pystray on 3.12 may be functional.

**Primary recommendation:** Use pystray 0.19.5 + pycaw 20251023 + winsound (stdlib). Integrate all three in the TTS worker: duck before synthesis, play pre-cue, synthesize+play, play post-cue, un-duck. The tray icon observes `STATE["speaking"]` to swap icons.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pystray | 0.19.5 | Windows system tray icon, right-click menu | The only pure-Python cross-platform tray library; Win32 backend is well-tested |
| pycaw | 20251023 | Per-session Windows Core Audio volume control | Standard Python wrapper for Windows Core Audio Session API (WASAPI) |
| Pillow (PIL) | already installed | Create/modify tray icon images programmatically | pystray requires PIL.Image objects; already a project dependency |
| winsound | stdlib | Play WAV audio cues synchronously | Zero-dependency Windows-only WAV player; already in stdlib, no install needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| comtypes | latest (pycaw dependency) | COM apartment initialization for pycaw in threads | Required: call `comtypes.CoInitialize()` at start of any non-main thread that calls pycaw |
| threading.Event | stdlib | Signal between TTS worker and tray icon about speaking state | Use to notify icon thread of speaking start/stop so it can swap images |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pycaw per-session ducking | Windows IAudioDuckingExclude COM API | Windows 7+ duck API is automatic but cannot be controlled per-session; pycaw gives explicit control |
| winsound | sounddevice for cues | sounddevice supports more formats (MP3 etc.) but adds complexity; winsound covers WAV with zero deps |
| pystray | infi.systray | infi.systray is Windows-only, simpler API but lacks submenu support needed for voice list |
| Programmatic PIL icon | Embedded PNG file | File-based icons require shipping assets; PIL lets us generate colored circles in-code |

**Installation:**
```bash
pip install pystray pycaw
# Pillow and winsound are already present
```

---

## Architecture Patterns

### Recommended Project Structure

```
agenttalk/
├── service.py           # main() — replace threading.Event().wait() with icon.run(setup=_setup)
├── tts_worker.py        # Add: duck_sessions(), unduck_sessions(), play_cue(), STATE["speaking"]
├── tray.py              # NEW: build_icon(), build_menu(), create_image_idle(), create_image_speaking()
└── audio_duck.py        # NEW: AudioDucker class — enumerate sessions, save/restore volumes
```

### Pattern 1: pystray Main Thread Ownership

**What:** `Icon.run(setup=fn)` blocks the main thread running the Win32 message loop. The `setup` callback fires in a separate thread once the icon is ready — use it to start uvicorn and the TTS worker (which were previously started before `threading.Event().wait()`).

**When to use:** Always — this is the required pattern from Phase 1's design comment in `service.py`.

```python
# Source: pystray docs https://pystray.readthedocs.io/en/latest/usage.html
# In service.py main():

def _setup(icon):
    icon.visible = True          # REQUIRED: icon is hidden until explicitly shown
    _start_http_server()         # starts uvicorn daemon thread
    start_tts_worker(_kokoro_engine)  # starts TTS daemon thread

icon = build_tray_icon()
icon.run(setup=_setup)           # blocks main thread — replaces threading.Event().wait()
```

**Critical:** Without `icon.visible = True` inside the setup callback, the tray icon never appears. This is a documented pystray behavior — icon starts hidden.

### Pattern 2: Dynamic Menu with Checked State and Submenus

**What:** Menu properties defined as callables are re-evaluated each time the menu opens. `icon.update_menu()` forces a refresh when state changes outside menu interaction.

```python
# Source: pystray docs https://pystray.readthedocs.io/en/latest/usage.html
import pystray

def build_menu(state: dict) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(
            "Mute",
            lambda icon, item: _toggle_mute(icon),
            checked=lambda item: state["muted"],
        ),
        pystray.MenuItem(
            "Voice",
            pystray.Menu(lambda: (
                pystray.MenuItem(
                    voice,
                    _make_voice_setter(voice),
                    checked=lambda item, v=voice: state["voice"] == v,
                    radio=True,
                )
                for voice in KOKORO_VOICES
            )),
        ),
        pystray.MenuItem(
            f'Active: {state["voice"]}',
            None,
            enabled=False,   # informational, not clickable
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
```

**Note:** The `enabled=False` item for TRAY-06 (current voice name) requires the `action` to be `None` — passing `None` as action is supported and renders a grayed-out item.

### Pattern 3: Runtime Icon Image Swap (Speaking Indicator)

**What:** Change `icon.icon` property at runtime to swap the PIL image. pystray applies the change immediately on Windows.

```python
# Source: pystray issue #68 + reference docs
def _notify_speaking_start(icon: pystray.Icon):
    icon.icon = create_image_speaking()   # red/animated appearance

def _notify_speaking_stop(icon: pystray.Icon):
    icon.icon = create_image_idle()       # normal appearance
```

**Coordination:** The `_tts_worker` sets `STATE["speaking"] = True` before synthesis and `False` after. A separate small thread (or callbacks into the icon) triggers the image swap. The cleanest approach is to pass the icon reference into `start_tts_worker()` so the worker can call `icon.icon = ...` directly — this is thread-safe on Windows.

### Pattern 4: Audio Ducking with pycaw

**What:** Before TTS playback begins, save each non-AgentTalk session's current volume, lower it to 50%. After playback, restore saved volumes. Must handle COM initialization in daemon threads.

```python
# Source: pycaw docs + GitHub examples + Microsoft ISimpleAudioVolume docs
import comtypes
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

class AudioDucker:
    def __init__(self):
        self._saved: dict[str, float] = {}   # process_name -> original volume

    def duck(self):
        """Lower all non-AgentTalk audio sessions to 50%."""
        comtypes.CoInitialize()
        try:
            sessions = AudioUtilities.GetAllSessions()
            self._saved.clear()
            for session in sessions:
                if session.Process is None:
                    continue  # System Sounds session — skip
                name = session.Process.name()
                if name.lower() in ("python.exe", "pythonw.exe"):
                    continue  # Skip ourselves
                vol = session.SimpleAudioVolume
                original = vol.GetMasterVolume()
                self._saved[name] = original
                vol.SetMasterVolume(original * 0.5, None)
        finally:
            comtypes.CoUninitialize()

    def unduck(self):
        """Restore all previously ducked sessions."""
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
        finally:
            comtypes.CoUninitialize()
```

**Critical:** `comtypes.CoInitialize()` / `CoUninitialize()` must wrap every pycaw call in a daemon thread. The main thread initializes COM automatically when pycaw is imported, but daemon threads do not.

### Pattern 5: Pre/Post Audio Cues

**What:** Play a WAV file synchronously before/after each TTS utterance. winsound.PlaySound blocks until the file finishes — no threading needed.

```python
# Source: https://docs.python.org/3/library/winsound.html
import winsound

def play_cue(path: str | None) -> None:
    """Play a WAV cue file synchronously. No-op if path is None or empty."""
    if not path:
        return
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME)
    except RuntimeError:
        logging.warning("Audio cue failed to play: %s", path)
```

**Integration point in `_tts_worker`:**
```python
# Before synthesis batch:
play_cue(STATE.get("pre_cue_path"))
duck_audio()

for sentence in sentences:
    synthesize_and_play(sentence)

unduck_audio()
play_cue(STATE.get("post_cue_path"))
```

### Anti-Patterns to Avoid

- **Calling `icon.run()` from a daemon thread:** On Windows it works but breaks macOS/Linux; always call from main thread.
- **Using `asyncio.Queue` for tray state updates:** The tray runs in a Win32 message loop, not asyncio; use `threading.Event` or direct property assignment.
- **Calling pycaw from daemon threads without `comtypes.CoInitialize()`:** Silent COM errors or crashes.
- **Using `winsound.SND_ASYNC` for pre-cues:** Cue must complete before TTS begins; async playback would overlap with speech.
- **Swapping icon images from wrong thread:** On Windows, assigning `icon.icon` from any thread is safe; do NOT call `icon.run()` or `icon.stop()` from daemon threads.
- **Setting `icon.visible = True` before calling `icon.run()`:** The visible property can only be set while the icon is running — do it in the `setup` callback.
- **Creating PIL images larger than needed:** Windows tray icon area is 16x16 to 32x32 px effective; minimum 20x20px to avoid `LoadImage WinError 0`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Windows tray icon Win32 message loop | Custom ctypes WM_TASKBARCREATED handler | pystray | Win32 tray requires NotifyIconData, WM_USER messages, WNDPROC — hundreds of lines of ctypes |
| Per-application audio session volume | ctypes IAudioSessionManager2 directly | pycaw | COM apartment model, session enumeration, lifetime management handled by pycaw |
| WAV file decoding and DirectSound playback | Manual WAV parser + sounddevice for cues | winsound.PlaySound | winsound delegates to Windows MCI — no dependency, WAV playback in one line |
| Thread-safe icon state communication | Shared memory, pipes, events | Direct `icon.icon = new_image` assignment | pystray's Win32 backend handles thread-safe icon updates internally |

**Key insight:** The Win32 tray icon API is deceptively complex; pystray saves ~500 lines of ctypes boilerplate and handles the WNDPROC, DPI awareness, and tooltip registration.

---

## Common Pitfalls

### Pitfall 1: Icon Never Appears (Missing `icon.visible = True`)

**What goes wrong:** The tray icon is running (no error) but nothing appears in the taskbar notification area.
**Why it happens:** pystray starts icons as hidden by default. Setting `visible=True` at construction time is ignored on some platforms.
**How to avoid:** Always set `icon.visible = True` inside the `setup` callback, not before `icon.run()`.
**Warning signs:** No error, no icon, `icon.running` is True.

### Pitfall 2: pycaw COM Errors in Daemon Threads

**What goes wrong:** `comtypes.COMError` or `OSError` when calling `AudioUtilities.GetAllSessions()` from the TTS worker thread.
**Why it happens:** COM is not initialized in new threads automatically; pycaw requires a COM apartment.
**How to avoid:** Wrap every pycaw call block with `comtypes.CoInitialize()` / `comtypes.CoUninitialize()` in non-main threads.
**Warning signs:** `COMError: -2147221008 (CO_E_NOTINITIALIZED)` in logs.

### Pitfall 3: Menu Item with `None` Action Crashes

**What goes wrong:** `MenuItem("Voice: af_heart", None, enabled=False)` raises `TypeError` on some pystray versions.
**Why it happens:** Some pystray versions require a callable action; `None` was not always accepted.
**How to avoid:** Use `lambda icon, item: None` as the action for disabled informational items, or pass `enabled=False` with a no-op lambda.
**Warning signs:** `TypeError: 'NoneType' object is not callable` in logs at menu open time.

### Pitfall 4: Audio Ducking Leaves Sessions at 50% After Service Crash

**What goes wrong:** If the service crashes mid-speech, other apps remain at 50% volume permanently until user adjusts manually.
**Why it happens:** `unduck()` is never called if the process is killed (SIGKILL, task manager).
**How to avoid:** Register an atexit handler that calls `unduck()`. Also call `unduck()` in the tray Quit handler before `icon.stop()`.
**Warning signs:** Spotify or browser audio permanently quiet after a service crash.

### Pitfall 5: Tray Icon Image Size Too Small

**What goes wrong:** `OSError: [WinError 0] The operation completed successfully` when pystray loads the icon.
**Why it happens:** `LoadImage` Windows API fails silently for images below ~20x20 pixels.
**How to avoid:** Always create tray images at least 64x64 pixels (Windows will scale them down). Do not create 15x15 or 16x16 PIL images.
**Warning signs:** WinError 0 in pystray startup, no icon appears.

### Pitfall 6: Session Volume Doubles After Restore

**What goes wrong:** After ducking+restoring, a session's volume is higher than the user originally set.
**Why it happens:** Re-enumerating sessions in `unduck()` may pick up new sessions not in `_saved`; restoring with wrong mapping.
**How to avoid:** Match sessions by process name AND process ID (if available) between `duck()` and `unduck()`. Sessions can be created/destroyed between the two calls.
**Warning signs:** User's Spotify volume jumps to 100% after TTS.

### Pitfall 7: Python 3.12 pystray GIL Crash

**What goes wrong:** Fatal Python error `PyEval_RestoreThread: the function must be called with the GIL held, but the GIL is released` in `pystray/_win32.py`.
**Why it happens:** pystray 0.19.5's Win32 backend has a GIL release/re-acquire sequence that conflicts with Python 3.12's GIL changes. The crash is confirmed with PySimpleGUI+psgtray+PyGame stacks.
**How to avoid:** Run the service under Python 3.11 (confirmed safe per project STATE.md). If Python 3.11 is not available, test pystray 0.19.5 standalone on 3.12 first — the crash may only manifest with specific thread patterns. The `setup=fn` pattern with daemon threads may be safe.
**Warning signs:** Fatal crash immediately on `icon.run()`, no Python traceback (process-level crash).

---

## Code Examples

### Creating Two Icon Images (Idle and Speaking)

```python
# Source: pystray docs https://pystray.readthedocs.io/en/latest/usage.html
from PIL import Image, ImageDraw

def create_image_idle(size: int = 64) -> Image.Image:
    """Blue circle — idle state."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, size - 4, size - 4], fill=(30, 120, 200, 255))
    return image

def create_image_speaking(size: int = 64) -> Image.Image:
    """Orange/red circle — TTS actively playing."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, size - 4, size - 4], fill=(220, 80, 20, 255))
    return image
```

### Full Tray Icon Setup with Menu

```python
# Source: pystray docs https://pystray.readthedocs.io/en/latest/usage.html
import pystray

KOKORO_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael", "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
]

def build_tray_icon(state: dict) -> pystray.Icon:
    def _toggle_mute(icon):
        state["muted"] = not state["muted"]
        icon.update_menu()

    def _set_voice(voice):
        def _inner(icon, item):
            state["voice"] = voice
            icon.update_menu()
        return _inner

    def _quit(icon, item):
        _unduck_all()          # restore any ducked sessions before exit
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            "Mute",
            _toggle_mute,
            checked=lambda item: state["muted"],
        ),
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
        pystray.MenuItem(
            lambda item: f'Active: {state["voice"]}',
            lambda icon, item: None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )

    return pystray.Icon(
        "AgentTalk",
        icon=create_image_idle(),
        title="AgentTalk",
        menu=menu,
    )
```

### Audio Ducking in TTS Worker

```python
# Source: pycaw GitHub examples + Microsoft ISimpleAudioVolume docs
import comtypes
from pycaw.pycaw import AudioUtilities

_ducked_volumes: dict[str, float] = {}

def _duck_other_sessions():
    """Reduce all non-AgentTalk audio sessions to 50%."""
    comtypes.CoInitialize()
    try:
        _ducked_volumes.clear()
        for session in AudioUtilities.GetAllSessions():
            if session.Process is None:
                continue  # system sounds session
            name = session.Process.name().lower()
            if name in ("python.exe", "pythonw.exe"):
                continue  # skip ourselves
            vol = session.SimpleAudioVolume
            original = vol.GetMasterVolume()
            if original > 0.0:
                _ducked_volumes[name] = original
                vol.SetMasterVolume(original * 0.5, None)
    except Exception:
        logging.exception("Audio ducking failed — continuing without duck.")
    finally:
        comtypes.CoUninitialize()

def _unduck_other_sessions():
    """Restore all ducked sessions to saved volume."""
    comtypes.CoInitialize()
    try:
        for session in AudioUtilities.GetAllSessions():
            if session.Process is None:
                continue
            name = session.Process.name().lower()
            if name in _ducked_volumes:
                vol = session.SimpleAudioVolume
                vol.SetMasterVolume(_ducked_volumes[name], None)
        _ducked_volumes.clear()
    except Exception:
        logging.exception("Audio un-ducking failed.")
    finally:
        comtypes.CoUninitialize()
```

### Updated `_tts_worker` Integration Sketch

```python
# Integration point in tts_worker.py _tts_worker() loop:
# (icon reference passed in; STATE dict extended with speaking, pre_cue_path, post_cue_path)

import winsound

while True:
    sentences: list[str] = TTS_QUEUE.get()
    try:
        if STATE["muted"]:
            continue

        # Notify tray: speaking started
        if _icon_ref:
            _icon_ref.icon = create_image_speaking()

        STATE["speaking"] = True

        # Pre-cue
        _play_cue(STATE.get("pre_cue_path"))

        # Duck other audio
        _duck_other_sessions()

        for sentence in sentences:
            if not sentence.strip():
                continue
            samples, rate = kokoro_engine.create(
                sentence, voice=STATE["voice"],
                speed=STATE["speed"], lang="en-us",
            )
            scaled = samples * STATE["volume"]
            if STATE["volume"] > 1.0:
                scaled = np.clip(scaled, -1.0, 1.0)
            sd.play(scaled, samplerate=rate)
            sd.wait()

        # Un-duck
        _unduck_other_sessions()

        # Post-cue
        _play_cue(STATE.get("post_cue_path"))

    except Exception:
        logging.exception("TTS worker error — skipping batch.")
        _unduck_other_sessions()  # ensure unduck even on error
    finally:
        STATE["speaking"] = False
        if _icon_ref:
            _icon_ref.icon = create_image_idle()
        TTS_QUEUE.task_done()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `threading.Event().wait()` as main thread blocker | `icon.run(setup=fn)` as main thread owner | Phase 4 (this phase) | Enables tray icon per SVC-04 |
| Endpoint/master volume control | Per-session `ISimpleAudioVolume` control | Windows Vista+ | Can duck Spotify without affecting system volume |
| File-based icon assets (.ico) | Programmatic PIL images | pystray standard | No file assets to ship; icons generated at runtime |

**Deprecated/outdated:**
- `IMMDevice` endpoint volume (`pycaw.pycaw.AudioUtilities.GetSpeakers()`): controls master device volume — affects ALL audio including our TTS. Use per-session `GetAllSessions()` instead.
- `winsound.SND_ASYNC` for cues: cues must complete before TTS starts; async causes overlap.

---

## Open Questions

1. **Python 3.12 pystray GIL crash — does it affect our exact usage pattern?**
   - What we know: Crash documented in PySimpleGUI+psgtray+PyGame stack (Oct 2024 bug report). Pure pystray on 3.12 may work.
   - What's unclear: Whether `Icon.run(setup=fn)` on 3.12 with daemon threads (no PyGame/GUI toolkit) triggers the crash.
   - Recommendation: Wave 0 — test `python3.12 -c "import pystray; from PIL import Image; i = pystray.Icon('t', Image.new('RGB',(64,64))); i.run(setup=lambda ic: ic.stop())"` on the dev machine. If it crashes, install Python 3.11 before proceeding.

2. **pycaw session identity across duck/unduck calls**
   - What we know: Sessions may be created/destroyed between `duck()` and `unduck()` calls. We key on `Process.name()`.
   - What's unclear: If a process restarts during TTS (rare), we may not restore its volume.
   - Recommendation: Accept this edge case — it's self-correcting when the user adjusts volume manually. The common case (Spotify, browser) is stable.

3. **winsound SND_FILENAME with paths containing spaces**
   - What we know: `winsound.PlaySound` accepts a string path. Windows API handles quoted paths.
   - What's unclear: Whether paths with non-ASCII characters (e.g., accented folder names in `%APPDATA%`) cause encoding issues.
   - Recommendation: Normalize cue paths through `os.fsdecode()` before passing to PlaySound; test with a path containing spaces.

4. **Tray icon visibility in Windows 11 notification area overflow**
   - What we know: Windows 11 may hide tray icons in the overflow menu by default.
   - What's unclear: Whether pystray pins the icon or lets Windows manage visibility.
   - Recommendation: Document in README that users may need to pin the AgentTalk icon in taskbar settings.

---

## Sources

### Primary (HIGH confidence)
- pystray 0.19.5 official docs (https://pystray.readthedocs.io/en/latest/usage.html) — Icon.run, setup pattern, MenuItem checked, submenus, icon image swap, update_menu
- pystray 0.19.5 reference (https://pystray.readthedocs.io/en/latest/reference.html) — Icon constructor, MenuItem parameters, Menu class
- Python stdlib winsound docs (https://docs.python.org/3/library/winsound.html) — PlaySound, SND_FILENAME, SND_ASYNC, blocking behavior
- Microsoft ISimpleAudioVolume docs (https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nn-audioclient-isimpleaudiovolume) — GetMasterVolume, SetMasterVolume, volume range 0.0-1.0

### Secondary (MEDIUM confidence)
- pycaw GitHub examples (https://github.com/AndreMiras/pycaw/blob/develop/examples/simple_audio_volume_example.py) — GetAllSessions, SimpleAudioVolume.GetMute/SetMute
- pycaw GitHub examples (https://github.com/AndreMiras/pycaw/blob/develop/examples/volume_by_process_example.py) — per-process volume control pattern
- pycaw issue #14 (https://github.com/AndreMiras/pycaw/issues/14) — `session.Process is None` for system sounds
- pycaw issue #34 (https://github.com/AndreMiras/pycaw/issues/34) — `comtypes.CoInitialize()` required in daemon threads
- pystray issue #145 (https://github.com/moses-palmer/pystray/issues/145) — minimum icon size 20x20px (WinError 0 below that)
- pystray changelog (https://github.com/moses-palmer/pystray/blob/master/CHANGES.rst) — v0.19.5 released 2023-09-17, fixes Pillow image flags, Windows icon blur

### Tertiary (LOW confidence)
- PySimpleGUI issue #6812 (https://github.com/PySimpleGUI/PySimpleGUI/issues/6812) — GIL crash in pystray _win32.py reported Oct 2024; may not apply to pure pystray usage without PyGame
- pycaw 20251023 version (https://libraries.io/pypi/pycaw) — released October 2025; comtypes + psutil dependencies

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pystray and pycaw are the established tools; winsound is stdlib; all verified via official docs
- Architecture patterns: HIGH — Icon.run/setup pattern from official docs; pycaw COM threading from official pycaw issue; winsound from Python docs
- Pitfalls: MEDIUM — GIL crash (Python 3.12) is LOW confidence (unconfirmed for our exact usage); other pitfalls HIGH from official sources
- Audio ducking implementation: MEDIUM — ISimpleAudioVolume verified from Microsoft docs; specific session identity edge cases are LOW confidence

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days — pystray and pycaw are stable; winsound is stdlib)

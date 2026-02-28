"""
AgentTalk demo recorder.

Records 5 feature clips using pyautogui + FFmpeg.
Run with: python demo/record_demo.py

Prerequisites:
  pip install pyautogui pygetwindow requests pillow pyperclip
  AgentTalk service running at localhost:5050
  FFmpeg on PATH
  Windows Terminal (wt.exe) installed
"""
import re
import subprocess
import sys
import time
import os
from pathlib import Path

# Windows consoles default to legacy code pages that can't encode Unicode symbols.
# Reconfigure before any print() calls.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
import pyautogui
import pygetwindow as gw

# ---------------------------------------------------------------------------
# Config — tweak these if clips are too short or too long
# ---------------------------------------------------------------------------
CLIP_DURATIONS = {
    "01-auto-speak":   30,
    "02-voice-switch": 25,
    "03-30-voices":    15,
    "04-semi-auto":    35,
}

DEMO_DIR = Path(__file__).parent
AGENTTALK_URL = "http://localhost:5050"

# Ensure FFmpeg and Windows Terminal are on PATH
for _dir in (
    r"D:\AI\FFmpeg\bin",
    r"C:\Users\omern\AppData\Local\Microsoft\WindowsApps",
):
    if _dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _dir + os.pathsep + os.environ.get("PATH", "")
CLAUDE_STARTUP_SLEEP = 8   # seconds to wait for Claude to initialize
BETWEEN_CLIP_SLEEP   = 3   # seconds between clips
CLIP_PRE_BUFFER      = 6   # seconds of recording before typing prompt (was 1)
CLIP_POST_BUFFER     = 5   # seconds of recording after duration wait
TYPE_INTERVAL        = 0.05 # seconds between keystrokes


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is on PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def check_agenttalk() -> bool:
    """Return True if AgentTalk service is up and ready."""
    try:
        r = requests.get(f"{AGENTTALK_URL}/health", timeout=3)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def check_prerequisites() -> None:
    """Abort with a helpful message if any prerequisite is missing."""
    if not check_ffmpeg():
        sys.exit("ERROR: ffmpeg not found on PATH. Add D:\\AI\\FFmpeg to PATH and retry.")
    if not check_agenttalk():
        sys.exit(
            "ERROR: AgentTalk service not responding at localhost:5050.\n"
            "Start it with: pythonw -m agenttalk.service"
        )
    print("✓ Prerequisites OK")


# Keywords that identify loopback/output capture devices (in priority order)
_LOOPBACK_KEYWORDS = ["stereo mix", "what u hear", "wave out", "cable output", "loopback", "output"]


def detect_audio_device() -> str:
    """
    Return the first DirectShow audio device suitable for system audio capture.

    Runs: ffmpeg -list_devices true -f dshow -i dummy
    FFmpeg exits with code 1 even on success — check stderr, not returncode.
    Falls back to the first available device if no loopback device is found.
    """
    result = subprocess.run(
        ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        capture_output=True,
    )
    output = result.stderr.decode("utf-8", errors="ignore")

    # Extract quoted device names from lines like:  "Device Name"
    devices = re.findall(r'"([^"]+)"', output)

    # Filter out alternative names (they start with @device_)
    devices = [d for d in devices if not d.startswith("@device_")]

    if not devices:
        sys.exit(
            "ERROR: No DirectShow audio devices found.\n"
            "Enable 'Stereo Mix' in Windows Sound Settings → Recording → Show Disabled Devices."
        )

    # Prefer loopback/output devices
    for keyword in _LOOPBACK_KEYWORDS:
        for d in devices:
            if keyword in d.lower():
                print(f"✓ Audio device: {d}")
                return d

    # No loopback device found — abort with helpful guidance
    print("⚠ No system audio loopback device found.")
    print("  Available devices:", ", ".join(devices))
    print("  Options:")
    print("    1. Install VB-Cable (free): https://vb-audio.com/Cable/")
    print("       Then use: --audio-device \"CABLE Output (VB-Audio Virtual Cable)\"")
    print("    2. Enable Stereo Mix: Sound Settings → Recording → Show Disabled Devices")
    print("    3. Record without audio: --no-audio")
    sys.exit(1)


def build_ffmpeg_cmd(
    audio_device: str | None,
    output_path: Path,
    window_rect: tuple[int, int, int, int] | None = None,
) -> list[str]:
    """
    Build the FFmpeg command list for screen recording.

    Video: gdigrab captures a window region when window_rect=(x,y,w,h) is given,
           or the full desktop otherwise.
    Audio: dshow captures the specified device; omitted when audio_device is None.
    Codec: libx264 ultrafast + aac 128k — fast enough not to drop frames.
    """
    if window_rect:
        x, y, w, h = window_rect
        video_input = [
            "-f", "gdigrab",
            "-offset_x", str(x), "-offset_y", str(y),
            "-video_size", f"{w}x{h}",
            "-framerate", "30", "-i", "desktop",
        ]
    else:
        video_input = ["-f", "gdigrab", "-framerate", "30", "-i", "desktop"]

    cmd = ["ffmpeg", "-y"] + video_input
    if audio_device:
        cmd += ["-f", "dshow", "-i", f"audio={audio_device}",
                "-acodec", "aac", "-b:a", "128k"]
    cmd += ["-vcodec", "libx264", "-preset", "ultrafast", "-crf", "23",
            str(output_path)]
    return cmd


class Recorder:
    """Context manager that starts and stops FFmpeg recording."""

    def __init__(
        self,
        audio_device: str,
        output_path: Path,
        window_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        self._cmd = build_ffmpeg_cmd(audio_device, output_path, window_rect)
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        print(f"  ▶ Recording → {self._cmd[-1]}")
        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(b"q")
                self._proc.stdin.flush()
                self._proc.wait(timeout=10)
            except Exception:
                try:
                    self._proc.terminate()
                except OSError:
                    pass  # process already gone
        print("  ■ Recording stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        try:
            self.stop()
        except Exception:
            pass  # don't let stop() failures mask the original exception


TERMINAL_TITLE = "agenttalk-demo"

# Populated by launch_claude_terminal(); used by focus_terminal().
# Tracking by hwnd avoids relying on the title, which claude overwrites on start.
_claude_window = None


def launch_claude_terminal() -> None:
    """
    Open a new Windows Terminal window and start Claude.

    Snapshots existing windows before launch, then identifies the new window
    by hwnd diff — title-independent, because claude overwrites the tab title.
    """
    global _claude_window
    print("Launching Windows Terminal + Claude...")

    before_hwnds = {w._hWnd for w in gw.getAllWindows() if w._hWnd}

    subprocess.Popen([
        "wt.exe",
        "--window", "new",
        "new-tab", "--title", TERMINAL_TITLE,
        "powershell", "-NoExit", "-Command", "claude --dangerously-skip-permissions",
    ])

    print(f"  Waiting {CLAUDE_STARTUP_SLEEP}s for Claude to start...")
    time.sleep(CLAUDE_STARTUP_SLEEP)

    new_windows = [
        w for w in gw.getAllWindows()
        if w._hWnd and w._hWnd not in before_hwnds and w.title
    ]
    if new_windows:
        _claude_window = new_windows[0]
        print(f"✓ Claude terminal ready (window: {_claude_window.title!r})")
    else:
        print("✓ Claude terminal ready (window not tracked — focus may fail)")


def focus_terminal() -> None:
    """
    Bring the Claude terminal window to the foreground.
    Uses the hwnd captured at launch; falls back to title search.
    Raises RuntimeError if the window cannot be found.
    """
    global _claude_window
    if _claude_window:
        try:
            _claude_window.activate()
            time.sleep(1.0)
            return
        except Exception:
            _claude_window = None  # stale handle; fall through

    windows = gw.getWindowsWithTitle(TERMINAL_TITLE)
    if not windows:
        raise RuntimeError(
            f"Terminal window '{TERMINAL_TITLE}' not found.\n"
            "Make sure wt.exe opened successfully."
        )
    _claude_window = windows[0]
    _claude_window.activate()
    time.sleep(1.0)


def type_prompt(text: str) -> None:
    """
    Type text into the focused terminal window and press Enter.
    Uses clipboard paste (Ctrl+V) for reliable Unicode input.
    Falls back to pyautogui.write() if pyperclip is not installed.
    """
    focus_terminal()
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    except (ImportError, Exception):
        pyautogui.write(text, interval=TYPE_INTERVAL)
    time.sleep(0.2)
    pyautogui.press("enter")
    print(f"  Typed: {text!r}")


def _config_post(payload: dict) -> None:
    """POST a partial config update to AgentTalk. Logs failures but does not abort."""
    try:
        r = requests.post(f"{AGENTTALK_URL}/config", json=payload, timeout=3)
        if r.status_code != 200:
            print(f"  ⚠ Config update failed: {r.status_code} {r.text}")
    except requests.exceptions.RequestException as e:
        print(f"  ⚠ Config update error: {e}")


def reset_voice(voice: str = "af_heart") -> None:
    """Reset AgentTalk voice to the specified value."""
    _config_post({"voice": voice})


def reset_speech_mode(mode: str = "auto") -> None:
    """Reset AgentTalk speech_mode to the specified value."""
    _config_post({"speech_mode": mode})


def record_clip(name: str, audio_device: str, steps_fn) -> None:
    """
    Generic clip recorder.

    Starts FFmpeg on the Claude terminal window, runs steps_fn() (which types
    prompts), waits for the clip duration + post-buffer, then stops FFmpeg.
    """
    if name not in CLIP_DURATIONS:
        raise ValueError(f"Unknown clip name {name!r}. Valid names: {list(CLIP_DURATIONS)}")
    duration = CLIP_DURATIONS[name]
    output = DEMO_DIR / f"{name}.mp4"

    print(f"\n{'='*60}")
    print(f"CLIP: {name}  ({duration}s)")
    print(f"{'='*60}")

    time.sleep(BETWEEN_CLIP_SLEEP)

    # Capture current bounds of the Claude terminal window
    window_rect = None
    if _claude_window:
        try:
            window_rect = (
                _claude_window.left, _claude_window.top,
                _claude_window.width, _claude_window.height,
            )
            print(f"  Window region: {window_rect}")
        except Exception:
            pass  # fall back to full desktop

    with Recorder(audio_device, output, window_rect):
        time.sleep(CLIP_PRE_BUFFER)   # buffer before typing
        steps_fn()
        print(f"  Waiting {duration}s for Claude + TTS to finish...")
        time.sleep(duration)
        time.sleep(CLIP_POST_BUFFER)  # extra buffer after response

    print(f"✓ Saved: {output}")


def clip_01_auto_speak(audio_device: str) -> None:
    """Clip 1: Auto-TTS — Claude replies, AgentTalk speaks automatically."""
    reset_voice("af_heart")
    reset_speech_mode("auto")

    def steps():
        type_prompt("Tell me a fun one-sentence fact about octopuses.")

    record_clip("01-auto-speak", audio_device, steps)


def clip_02_voice_switch(audio_device: str) -> None:
    """Clip 2: Voice switching — af_heart → bf_emma live in session."""
    reset_voice("af_heart")
    reset_speech_mode("auto")

    def steps():
        type_prompt("/agenttalk:voice bf_emma")
        time.sleep(3)  # wait for voice switch confirmation
        type_prompt("Say hello in your new voice.")

    try:
        record_clip("02-voice-switch", audio_device, steps)
    finally:
        reset_voice("af_heart")  # clean up for next clip


def clip_03_30_voices(audio_device: str) -> None:
    """Clip 3: Show the interactive voice picker via /agenttalk:voice (no args)."""
    reset_speech_mode("auto")

    def steps():
        type_prompt("/agenttalk:voice")

    record_clip("03-30-voices", audio_device, steps)
    # Press Escape to exit the picker so Claude is ready for next clip
    time.sleep(1)
    try:
        focus_terminal()
        pyautogui.press("escape")
    except RuntimeError as e:
        print(f"  ⚠ Could not dismiss voice picker: {e}")


def clip_04_semi_auto(audio_device: str) -> None:
    """Clip 4: Semi-auto mode — silence after reply, then speak on demand."""
    reset_voice("af_heart")
    reset_speech_mode("auto")

    def steps():
        # Switch to semi-auto
        type_prompt("/agenttalk:mode")
        time.sleep(4)
        # Ask something — Claude answers but AgentTalk stays silent
        type_prompt("What is the capital of France?")
        time.sleep(8)
        # Now speak on demand
        type_prompt("/agenttalk:speak")

    try:
        record_clip("04-semi-auto", audio_device, steps)
    finally:
        reset_speech_mode("auto")  # restore for next clip


def clip_05_tray_icon(audio_device: str) -> None:
    """Clip 5: Tray icon animation — icon changes state while speaking."""
    reset_voice("af_heart")
    reset_speech_mode("auto")

    def steps():
        # Long response so tray animation is visible
        type_prompt("Count from one to ten, saying each number on its own line.")

    record_clip("05-tray-icon", audio_device, steps)


_NO_AUDIO = object()  # sentinel: skip audio entirely


def run_demo(audio_device=_NO_AUDIO) -> None:
    """Run all 5 demo clips in sequence."""
    print("AgentTalk Demo Recorder")
    print("=======================")
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    check_prerequisites()
    if audio_device is _NO_AUDIO:
        audio_device = detect_audio_device()
    elif audio_device is None:
        print("  (no audio track)")
    else:
        print(f"✓ Audio device: {audio_device}")

    launch_claude_terminal()

    for clip_fn, label in [
        (lambda: clip_01_auto_speak(audio_device), "01-auto-speak"),
        (lambda: clip_02_voice_switch(audio_device), "02-voice-switch"),
        (lambda: clip_03_30_voices(audio_device), "03-30-voices"),
        (lambda: clip_04_semi_auto(audio_device), "04-semi-auto"),
    ]:
        try:
            clip_fn()
        except Exception as e:
            print(f"  ✗ Clip {label} failed: {e}")

    print("\n✓ All clips recorded!")
    print(f"Output directory: {DEMO_DIR.resolve()}")
    for name in CLIP_DURATIONS:
        path = DEMO_DIR / f"{name}.mp4"
        try:
            size_mb = path.stat().st_size / 1_048_576
        except OSError:
            size_mb = 0
        print(f"  {name}.mp4  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AgentTalk demo recorder")
    parser.add_argument(
        "--audio-device", "-a",
        metavar="DEVICE",
        help="DirectShow audio device name for recording (overrides auto-detect)",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Record video only (no audio track)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available DirectShow audio devices and exit",
    )
    args = parser.parse_args()

    if args.list_devices:
        result = subprocess.run(
            ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
        )
        output = result.stderr.decode("utf-8", errors="ignore")
        devices = [d for d in re.findall(r'"([^"]+)"', output) if not d.startswith("@device_")]
        print("DirectShow audio devices:")
        for i, d in enumerate(devices):
            print(f"  [{i}] {d}")
        print()
        print('Use: python record_demo.py --audio-device "Device Name"')
        print('     python record_demo.py --no-audio')
    elif args.no_audio:
        print("⚠ Recording without audio (--no-audio)")
        run_demo(audio_device=None)  # None = explicitly no audio
    else:
        # args.audio_device is a string or None (not specified = auto-detect via sentinel)
        run_demo(audio_device=args.audio_device if args.audio_device else _NO_AUDIO)

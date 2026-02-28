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
    "05-tray-icon":    25,
}

DEMO_DIR = Path(__file__).parent
AGENTTALK_URL = "http://localhost:5050"
CLAUDE_STARTUP_SLEEP = 8   # seconds to wait for Claude to initialize
BETWEEN_CLIP_SLEEP   = 3   # seconds between clips
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
_LOOPBACK_KEYWORDS = ["stereo mix", "what u hear", "wave out", "output", "loopback"]


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

    # Fallback: first device (usually microphone)
    print(f"⚠ No loopback device found, using: {devices[0]}")
    return devices[0]


def build_ffmpeg_cmd(audio_device: str, output_path: Path) -> list[str]:
    """
    Build the FFmpeg command list for screen + audio recording.

    Video: gdigrab captures the full desktop at 30 fps.
    Audio: dshow captures the specified device (loopback or mic).
    Codec: libx264 ultrafast + aac 128k — fast enough not to drop frames.
    """
    return [
        "ffmpeg", "-y",
        # Video: full desktop capture
        "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
        # Audio: DirectShow device
        "-f", "dshow", "-i", f"audio={audio_device}",
        # Encoding
        "-vcodec", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-acodec", "aac", "-b:a", "128k",
        str(output_path),
    ]


class Recorder:
    """Context manager that starts and stops FFmpeg recording."""

    def __init__(self, audio_device: str, output_path: Path) -> None:
        self._cmd = build_ffmpeg_cmd(audio_device, output_path)
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


def launch_claude_terminal() -> None:
    """
    Open a new Windows Terminal window titled 'agenttalk-demo' and start Claude.

    Uses wt.exe (Windows Terminal) with --title to make the window findable
    by pygetwindow. Waits CLAUDE_STARTUP_SLEEP seconds for Claude to initialize.
    """
    print("Launching Windows Terminal + Claude...")
    subprocess.Popen([
        "wt.exe",
        "powershell", "-NoExit", "-Command",
        f"$host.UI.RawUI.WindowTitle = '{TERMINAL_TITLE}'; claude",
    ])
    print(f"  Waiting {CLAUDE_STARTUP_SLEEP}s for Claude to start...")
    time.sleep(CLAUDE_STARTUP_SLEEP)
    print("✓ Claude terminal ready")


def focus_terminal() -> None:
    """
    Bring the 'agenttalk-demo' terminal window to the foreground.
    Raises RuntimeError if the window is not found.
    """
    windows = gw.getWindowsWithTitle(TERMINAL_TITLE)
    if not windows:
        raise RuntimeError(
            f"Terminal window '{TERMINAL_TITLE}' not found.\n"
            "Make sure wt.exe opened successfully."
        )
    win = windows[0]
    win.activate()
    time.sleep(1.0)  # Wait for focus to register (FFmpeg CPU load can slow this)


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

    Starts FFmpeg, runs steps_fn() (which types prompts), waits for the
    clip duration, then stops FFmpeg.
    """
    if name not in CLIP_DURATIONS:
        raise ValueError(f"Unknown clip name {name!r}. Valid names: {list(CLIP_DURATIONS)}")
    duration = CLIP_DURATIONS[name]
    output = DEMO_DIR / f"{name}.mp4"

    print(f"\n{'='*60}")
    print(f"CLIP: {name}  ({duration}s)")
    print(f"{'='*60}")

    time.sleep(BETWEEN_CLIP_SLEEP)

    with Recorder(audio_device, output):
        time.sleep(1)          # 1s buffer before typing
        steps_fn()
        print(f"  Waiting {duration}s for Claude + TTS to finish...")
        time.sleep(duration)

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


def run_demo() -> None:
    """Run all 5 demo clips in sequence."""
    print("AgentTalk Demo Recorder")
    print("=======================")
    DEMO_DIR.mkdir(exist_ok=True)

    check_prerequisites()
    audio_device = detect_audio_device()

    launch_claude_terminal()

    clip_01_auto_speak(audio_device)
    clip_02_voice_switch(audio_device)
    clip_03_30_voices(audio_device)
    clip_04_semi_auto(audio_device)
    clip_05_tray_icon(audio_device)

    print("\n✓ All clips recorded!")
    print(f"Output directory: {DEMO_DIR.resolve()}")
    for name in CLIP_DURATIONS:
        path = DEMO_DIR / f"{name}.mp4"
        size_mb = path.stat().st_size / 1_048_576 if path.exists() else 0
        print(f"  {name}.mp4  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    run_demo()

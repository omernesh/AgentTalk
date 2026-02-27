# Demo Recording Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `demo/record_demo.py` — a fully automated script that opens Windows Terminal, starts Claude, and records 5 feature demo clips using pyautogui for automation and FFmpeg for screen+audio capture.

**Architecture:** Single Python script in `demo/record_demo.py`. Helper functions (prerequisite checks, audio device detection, FFmpeg wrapper, terminal automation) are unit-tested with mocked subprocesses. The main `run_demo()` function orchestrates clip recording in sequence with REST calls to AgentTalk between clips to reset state.

**Tech Stack:** Python 3.11+, pyautogui, pygetwindow, requests, FFmpeg (gdigrab + dshow), AgentTalk REST API at localhost:5050

---

## Prerequisites

```bash
pip install pyautogui pygetwindow requests pillow
```

FFmpeg must be on PATH (it is, at `D:\AI\FFmpeg`).
AgentTalk service must be running before the script starts.

---

### Task 1: Create demo/ folder and test skeleton

**Files:**
- Create: `demo/record_demo.py`
- Create: `demo/test_record_demo.py`

**Step 1: Create the demo folder and empty script**

```bash
mkdir demo
```

Create `demo/record_demo.py` with just the module docstring and imports:

```python
"""
AgentTalk demo recorder.

Records 5 feature clips using pyautogui + FFmpeg.
Run with: python demo/record_demo.py

Prerequisites:
  pip install pyautogui pygetwindow requests pillow
  AgentTalk service running at localhost:5050
  FFmpeg on PATH
  Windows Terminal (wt.exe) installed
"""
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
```

**Step 2: Create the test skeleton**

Create `demo/test_record_demo.py`:

```python
"""Unit tests for record_demo helper functions."""
import subprocess
from unittest.mock import patch, MagicMock
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

**Step 3: Run tests (empty, should pass)**

```bash
cd demo && python -m pytest test_record_demo.py -v
```
Expected: 0 tests collected, no errors.

**Step 4: Commit**

```bash
git add demo/record_demo.py demo/test_record_demo.py
git commit -m "feat(demo): scaffold demo recorder module and test file"
```

---

### Task 2: Prerequisite checks

**Files:**
- Modify: `demo/record_demo.py`
- Modify: `demo/test_record_demo.py`

**Step 1: Write failing tests**

Add to `demo/test_record_demo.py`:

```python
from record_demo import check_prerequisites, check_ffmpeg, check_agenttalk

def test_check_ffmpeg_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert check_ffmpeg() is True

def test_check_ffmpeg_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert check_ffmpeg() is False

def test_check_agenttalk_success():
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        assert check_agenttalk() is True

def test_check_agenttalk_down():
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
        assert check_agenttalk() is False
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test_record_demo.py -v
```
Expected: ImportError — `check_prerequisites` not defined.

**Step 3: Implement**

Add to `demo/record_demo.py`:

```python
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
```

**Step 4: Run tests**

```bash
python -m pytest test_record_demo.py -v
```
Expected: 4 PASS

**Step 5: Commit**

```bash
git add demo/record_demo.py demo/test_record_demo.py
git commit -m "feat(demo): add prerequisite checks with tests"
```

---

### Task 3: Audio device detection

**Files:**
- Modify: `demo/record_demo.py`
- Modify: `demo/test_record_demo.py`

**Step 1: Write failing test**

Add to `demo/test_record_demo.py`:

```python
from record_demo import detect_audio_device

# Sample FFmpeg dshow output (written to stderr)
FFMPEG_DSHOW_OUTPUT = b"""
[dshow @ 0000] DirectShow audio devices (some may be both input and output)
[dshow @ 0000]  "Microphone Array (Realtek(R) Audio)"
[dshow @ 0000]     Alternative name "@device_cm_{33D9A762}..."
[dshow @ 0000]  "Stereo Mix (Realtek(R) Audio)"
[dshow @ 0000]     Alternative name "@device_cm_{33D9A762}..."
"""

FFMPEG_DSHOW_MIC_ONLY = b"""
[dshow @ 0000] DirectShow audio devices
[dshow @ 0000]  "Microphone (USB Audio Device)"
"""

def test_detect_stereo_mix():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=FFMPEG_DSHOW_OUTPUT)
        device = detect_audio_device()
    assert device == "Stereo Mix (Realtek(R) Audio)"

def test_detect_fallback_to_mic():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=FFMPEG_DSHOW_MIC_ONLY)
        device = detect_audio_device()
    assert device == "Microphone (USB Audio Device)"
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test_record_demo.py::test_detect_stereo_mix -v
```
Expected: ImportError.

**Step 3: Implement**

Add to `demo/record_demo.py`:

```python
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
    import re
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
```

**Step 4: Run tests**

```bash
python -m pytest test_record_demo.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add demo/record_demo.py demo/test_record_demo.py
git commit -m "feat(demo): audio device auto-detection with loopback preference"
```

---

### Task 4: FFmpeg recording wrapper

**Files:**
- Modify: `demo/record_demo.py`
- Modify: `demo/test_record_demo.py`

**Step 1: Write failing tests**

Add to `demo/test_record_demo.py`:

```python
from record_demo import build_ffmpeg_cmd

def test_ffmpeg_cmd_contains_gdigrab():
    cmd = build_ffmpeg_cmd("Stereo Mix (Realtek)", Path("demo/01-auto.mp4"))
    assert "-f" in cmd
    assert "gdigrab" in cmd

def test_ffmpeg_cmd_contains_audio_device():
    cmd = build_ffmpeg_cmd("Stereo Mix (Realtek)", Path("demo/01-auto.mp4"))
    joined = " ".join(cmd)
    assert "Stereo Mix (Realtek)" in joined

def test_ffmpeg_cmd_output_path():
    cmd = build_ffmpeg_cmd("Stereo Mix", Path("demo/clip.mp4"))
    assert str(Path("demo/clip.mp4")) == cmd[-1]
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test_record_demo.py::test_ffmpeg_cmd_contains_gdigrab -v
```
Expected: ImportError.

**Step 3: Implement**

Add to `demo/record_demo.py`:

```python
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
                self._proc.terminate()
        print("  ■ Recording stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
```

**Step 4: Run tests**

```bash
python -m pytest test_record_demo.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add demo/record_demo.py demo/test_record_demo.py
git commit -m "feat(demo): FFmpeg recording wrapper with context manager"
```

---

### Task 5: Terminal automation helpers

**Files:**
- Modify: `demo/record_demo.py`

No unit tests for this task — pyautogui functions require a real display. These will be validated during the end-to-end smoke test (Task 9).

**Step 1: Implement terminal launch**

Add to `demo/record_demo.py`:

```python
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
        "--title", TERMINAL_TITLE,
        "powershell", "-NoExit", "-Command", "claude",
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
    time.sleep(0.5)  # Brief pause for focus to register


def type_prompt(text: str) -> None:
    """
    Type text into the focused terminal window and press Enter.
    Uses pyautogui.typewrite for reliable character-by-character input.
    Handles special characters via pyautogui.write (ASCII-safe).
    """
    focus_terminal()
    # typewrite doesn't handle all Unicode — use clipboard for safety
    import pyperclip  # optional; falls back to typewrite if missing
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    except ImportError:
        pyautogui.write(text, interval=TYPE_INTERVAL)
    time.sleep(0.2)
    pyautogui.press("enter")
    print(f"  Typed: {text!r}")
```

**Step 2: Commit**

```bash
git add demo/record_demo.py
git commit -m "feat(demo): terminal launch and pyautogui typing helpers"
```

---

### Task 6: AgentTalk REST helpers

**Files:**
- Modify: `demo/record_demo.py`
- Modify: `demo/test_record_demo.py`

**Step 1: Write failing tests**

Add to `demo/test_record_demo.py`:

```python
from record_demo import reset_voice, reset_speech_mode

def test_reset_voice():
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        reset_voice("af_heart")
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["voice"] == "af_heart"

def test_reset_speech_mode():
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        reset_speech_mode("auto")
        call_json = mock_post.call_args[1]["json"]
        assert call_json["speech_mode"] == "auto"
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test_record_demo.py::test_reset_voice -v
```
Expected: ImportError.

**Step 3: Implement**

Add to `demo/record_demo.py`:

```python
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
```

**Step 4: Run tests**

```bash
python -m pytest test_record_demo.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add demo/record_demo.py demo/test_record_demo.py
git commit -m "feat(demo): AgentTalk REST helpers with tests"
```

---

### Task 7: Implement the 5 clip functions

**Files:**
- Modify: `demo/record_demo.py`

Each function records one clip. No unit tests — these are integration sequences that require the full stack.

**Step 1: Implement all 5 clip functions**

Add to `demo/record_demo.py`:

```python
def record_clip(name: str, audio_device: str, steps_fn) -> None:
    """
    Generic clip recorder.

    Starts FFmpeg, runs steps_fn() (which types prompts), waits for the
    clip duration, then stops FFmpeg.
    """
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

    record_clip("02-voice-switch", audio_device, steps)
    reset_voice("af_heart")  # clean up for next clip


def clip_03_30_voices(audio_device: str) -> None:
    """Clip 3: Show the interactive voice picker via /agenttalk:voice (no args)."""
    reset_speech_mode("auto")

    def steps():
        type_prompt("/agenttalk:voice")

    record_clip("03-30-voices", audio_device, steps)
    # Press Escape to exit the picker so Claude is ready for next clip
    time.sleep(1)
    focus_terminal()
    pyautogui.press("escape")


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

    record_clip("04-semi-auto", audio_device, steps)
    reset_speech_mode("auto")  # restore for next clip


def clip_05_tray_icon(audio_device: str) -> None:
    """Clip 5: Tray icon animation — icon changes state while speaking."""
    reset_voice("af_heart")
    reset_speech_mode("auto")

    def steps():
        # Long response so tray animation is visible
        type_prompt("Count from one to ten, saying each number on its own line.")

    record_clip("05-tray-icon", audio_device, steps)
```

**Step 2: Commit**

```bash
git add demo/record_demo.py
git commit -m "feat(demo): implement all 5 clip recording functions"
```

---

### Task 8: Wire main() and add pyperclip dependency

**Files:**
- Modify: `demo/record_demo.py`

**Step 1: Implement main()**

Add to `demo/record_demo.py`:

```python
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
```

**Step 2: Add pyperclip to prerequisites note**

Update the docstring at the top of `record_demo.py` — change the pip install line:

```python
# Prerequisites:
#   pip install pyautogui pygetwindow requests pillow pyperclip
```

**Step 3: Run all unit tests**

```bash
cd demo && python -m pytest test_record_demo.py -v
```
Expected: all PASS

**Step 4: Commit**

```bash
git add demo/record_demo.py
git commit -m "feat(demo): add main() orchestrator and pyperclip dependency"
```

---

### Task 9: Smoke test and README note

**Files:**
- Modify: `demo/record_demo.py` (if any issues found)
- Create: `demo/README.md`

**Step 1: Dry-run prerequisite check**

With AgentTalk running:

```bash
cd demo
python -c "from record_demo import check_prerequisites, detect_audio_device; check_prerequisites(); print(detect_audio_device())"
```
Expected:
```
✓ Prerequisites OK
✓ Audio device: Stereo Mix (...)   ← or whatever device is found
```

**Step 2: Test FFmpeg command build**

```bash
python -c "
from record_demo import build_ffmpeg_cmd
from pathlib import Path
cmd = build_ffmpeg_cmd('Stereo Mix', Path('demo/test.mp4'))
print(' '.join(cmd))
"
```
Expected: full ffmpeg command printed, no errors.

**Step 3: Run unit tests one final time**

```bash
python -m pytest test_record_demo.py -v
```
Expected: all PASS

**Step 4: Create demo/README.md**

```markdown
# AgentTalk Demo Clips

Automated screen recordings demonstrating AgentTalk features.

## Running the recorder

```bash
# Install dependencies (one-time)
pip install pyautogui pygetwindow requests pillow pyperclip

# Start AgentTalk service first
pythonw -m agenttalk.service

# Run the recorder
python demo/record_demo.py
```

## Clips

| File | Feature |
|------|---------|
| `01-auto-speak.mp4` | Auto-TTS — Claude replies, AgentTalk speaks |
| `02-voice-switch.mp4` | Voice switching mid-session |
| `03-30-voices.mp4` | 30-voice picker menu |
| `04-semi-auto.mp4` | Semi-auto mode — speak on demand |
| `05-tray-icon.mp4` | Tray icon animation during speech |

## Timing

Edit `CLIP_DURATIONS` at the top of `record_demo.py` if clips cut off early
(slow machine) or have too much dead air (fast machine).
```

**Step 5: Final commit**

```bash
git add demo/record_demo.py demo/test_record_demo.py demo/README.md
git commit -m "feat(demo): complete demo recorder — 5 clips, smoke tested"
```

---

## Execution Checklist

Before running the full demo:

1. `pythonw -m agenttalk.service` — AgentTalk running
2. `curl localhost:5050/health` → `{"status":"ok"}`
3. Stereo Mix or loopback audio device enabled in Windows Sound Settings
4. `pip install pyautogui pygetwindow requests pillow pyperclip`
5. `python demo/record_demo.py`
6. Do NOT touch mouse or keyboard during recording — pyautogui controls the terminal

Clips land in `demo/*.mp4`.

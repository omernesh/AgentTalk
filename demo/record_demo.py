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

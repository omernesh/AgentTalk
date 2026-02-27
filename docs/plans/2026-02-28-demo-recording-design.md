# Demo Recording Script — Design

**Date:** 2026-02-28
**Status:** Approved

## Goal

Automate production of 5 short demo video clips for the AgentTalk GitHub repo, each
demonstrating one notable feature. No OBS required — uses FFmpeg (already on PATH) for
recording and pyautogui for terminal automation.

---

## Clips

| # | Filename | Feature | Duration |
|---|----------|---------|----------|
| 1 | `01-auto-speak.mp4` | Auto-TTS — Claude replies, AgentTalk speaks without user action | 30 s |
| 2 | `02-voice-switch.mp4` | Voice switching — `af_heart` → `bf_emma` live in session | 25 s |
| 3 | `03-30-voices.mp4` | Voice list picker via `/agenttalk:voice` (no args) | 15 s |
| 4 | `04-semi-auto.mp4` | Semi-auto mode — silence after reply, speak on demand with `/agenttalk:speak` | 35 s |
| 5 | `05-tray-icon.mp4` | Tray icon animation — icon changes while speaking | 25 s |

---

## Technical Architecture

### Script: `demo/record_demo.py`

**Language:** Python 3.11+
**Dependencies:** `pyautogui`, `pillow`, `requests` (all pip-installable)
**External tools:** FFmpeg (already at `D:\AI\FFmpeg`), AgentTalk service running

### Flow

```
1. Startup checks
   ├── FFmpeg on PATH?
   ├── AgentTalk health: GET localhost:5050/health → 200
   └── Create demo/ folder

2. Audio device detection
   ├── ffmpeg -list_devices true -f dshow -i dummy
   ├── Parse output for loopback/stereo-mix/output device
   └── Fallback: microphone

3. Terminal launch
   ├── wt.exe new-tab → Windows Terminal window
   ├── Type: claude [Enter]
   └── Sleep 5s for Claude to initialize

4. Per-clip loop (5 clips)
   ├── Sleep 2s
   ├── Start FFmpeg (gdigrab + dshow) as background subprocess
   ├── Focus terminal window via pyautogui (find by title)
   ├── Type prompt(s) with character-level delays
   ├── Sleep clip-specific duration
   ├── Send 'q' to FFmpeg stdin → save clip
   └── POST /config reset if needed

5. Done — 5 .mp4 files in demo/
```

### Timing defaults (configurable at top of script)

```python
CLIP_DURATIONS = {
    "01-auto-speak":   30,
    "02-voice-switch": 25,
    "03-30-voices":    15,
    "04-semi-auto":    35,
    "05-tray-icon":    25,
}
```

### FFmpeg command template

```
ffmpeg -y
  -f gdigrab -framerate 30 -i desktop
  -f dshow -i audio="<detected_device>"
  -vcodec libx264 -preset ultrafast -crf 23
  -acodec aac -b:a 128k
  demo/<clip_name>.mp4
```

### State resets between clips

| Before clip | Action |
|-------------|--------|
| Before #2 | Ensure voice is `af_heart` (POST /config) |
| Before #4 | Ensure speech_mode is `auto` (POST /config) |
| After #4 | Reset speech_mode to `auto` (POST /config) |

---

## Files created

```
demo/
  record_demo.py        # Main automation + recording script
  01-auto-speak.mp4     # Output
  02-voice-switch.mp4   # Output
  03-30-voices.mp4      # Output
  04-semi-auto.mp4      # Output
  05-tray-icon.mp4      # Output
```

---

## Assumptions

- AgentTalk service is running before the script starts
- Windows Terminal (`wt.exe`) is installed
- FFmpeg is on PATH
- Claude Code is installed and `claude` command works
- Python 3.11 venv with pyautogui + pillow + requests installed

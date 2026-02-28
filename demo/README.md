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

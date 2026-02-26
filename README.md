# AgentTalk

Real-time text-to-speech for Claude Code output — offline, local, no API keys.

Claude Code's responses are spoken aloud as they complete, hands-free, without leaving the terminal.

**Requires Python 3.11.** Python 3.12 and above are not supported (see [Troubleshooting](#troubleshooting)).

---

## Installation

### Prerequisites

- Windows 11
- Python 3.11 (exactly — see [Python version requirements](#python-version-requirements-311-only))
- A working audio output device

### Install and setup

```bash
pip install git+https://github.com/omernesh/AgentTalk
agenttalk setup
```

`agenttalk setup` will:
1. Download the Kokoro ONNX model files (~310 MB) to `%APPDATA%\AgentTalk\models\`
2. Register the `Stop` and `SessionStart` hooks in `~/.claude/settings.json`
3. Create an `AgentTalk.lnk` shortcut on your desktop

---

## Quickstart

```bash
# 1. Install
pip install git+https://github.com/omernesh/AgentTalk

# 2. Download model and register hooks
agenttalk setup

# 3. Launch the service (or double-click the desktop shortcut)
pythonw agenttalk/service.py
```

Open Claude Code. The next Claude response will be spoken aloud automatically.

---

## Available Voices

Switch voices with `/agenttalk:voice [name]` or via the tray menu.

| Prefix | Region | Voices |
|--------|--------|--------|
| `af_` | American Female | `af_heart` (default), `af_bella`, `af_nicole`, `af_aoede`, `af_kore`, `af_sarah`, `af_sky` |
| `am_` | American Male | `am_adam`, `am_michael`, `am_echo`, `am_eric`, `am_fenrir`, `am_liam`, `am_onyx`, `am_puck`, `am_santa` |
| `bf_` | British Female | `bf_emma`, `bf_isabella`, `bf_alice`, `bf_lily` |
| `bm_` | British Male | `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`, `bm_norton`, `bm_oscar` |

The default voice is `af_heart`.

---

## Slash Commands

Run these from the Claude Code terminal (type the command as your message):

| Command | Description |
|---------|-------------|
| `/agenttalk:start` | Launch the AgentTalk service if it is not running |
| `/agenttalk:stop` | Stop the service and silence any playing audio |
| `/agenttalk:voice [name]` | Switch the active voice (e.g., `/agenttalk:voice af_bella`) |
| `/agenttalk:model [kokoro\|piper]` | Switch the TTS engine (`kokoro` is the only working engine in v1) |

Voice and model changes take effect immediately for the next utterance and persist across restarts.

---

## Tray Menu

Right-click the AgentTalk icon in the Windows system tray to access:

- **Mute / Unmute** — toggle TTS on and off (checkmark shows current state)
- **Voice** — submenu listing all available Kokoro voices; click to switch
- **Quit** — stop the service and remove the tray icon

The tray icon changes appearance while TTS is actively speaking and returns to default when playback finishes.

---

## Configuration

Settings are persisted in `%APPDATA%\AgentTalk\config.json`. All settings can be changed at runtime without restarting the service.

| Setting | Default | How to change |
|---------|---------|---------------|
| `voice` | `af_heart` | `/agenttalk:voice [name]` or tray menu |
| `speed` | `1.0` | POST to `/config` with `{"speed": 1.2}` |
| `volume` | `1.0` | POST to `/config` with `{"volume": 0.8}` |
| `model` | `kokoro` | `/agenttalk:model [kokoro\|piper]` |
| `muted` | `false` | Tray Mute toggle |
| `pre_cue_path` | `null` | POST to `/config` with `{"pre_cue_path": "C:\\path\\bell.wav"}` |
| `post_cue_path` | `null` | POST to `/config` with `{"post_cue_path": "C:\\path\\bell.wav"}` |

---

## Troubleshooting

### WASAPI exclusive mode conflicts

**Symptom:** No audio plays, or you see `PaErrorCode -9984` in the log.

**Cause:** Some audio devices use WASAPI in exclusive mode, which blocks other applications from using the audio device simultaneously.

**Fix options:**
1. In Windows Sound Settings, set your default output device to use "Shared" mode (not "Exclusive").
2. Use an MME audio device instead of WASAPI — MME handles sample rate resampling automatically.
3. If you have multiple audio devices, switch to one that uses WASAPI in shared mode.

Check `%APPDATA%\AgentTalk\agenttalk.log` for the detected host API type:
```
Non-WASAPI device (MME) — using PortAudio default resampling.
```
or
```
WASAPI device detected — auto_convert enabled.
```

### Kokoro model download issues

**Symptom:** `agenttalk setup` fails with an HTTP error or download stalls.

**Fix options:**
1. Check your internet connection and firewall settings — the download requires access to `github.com`.
2. Ensure you have at least 400 MB of free disk space in `%APPDATA%`.
3. If you see HTTP 404, the model URL may have changed — check the latest release at [thewh1teagle/kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases) and update the URL in `agenttalk/installer.py`.
4. Re-run `agenttalk setup` — downloads are idempotent (partially downloaded files are skipped and re-downloaded from scratch on retry).

**Partial download recovery:** If a download was interrupted, delete the incomplete file from `%APPDATA%\AgentTalk\models\` before re-running setup.

### Python version requirements (3.11 only)

**Symptom:** The service crashes immediately, or you see a GIL-related error on startup, or `pystray` fails to import.

**Cause:** Python 3.12 introduced changes to the GIL (Global Interpreter Lock) that cause `pystray` to crash when the tray icon runs on the main thread. This is a known upstream issue with no fix released as of February 2026.

**Fix:** Install Python 3.11 and use it for AgentTalk.

Check your Python version:
```bash
python --version
# Must show: Python 3.11.x
```

Install Python 3.11 from [python.org/downloads](https://www.python.org/downloads/release/python-3118/) and re-install AgentTalk in a Python 3.11 virtual environment:
```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install git+https://github.com/omernesh/AgentTalk
agenttalk setup
```

### Hook registration verification

**Symptom:** Claude Code responses are not being spoken — the service is running but hooks do not fire.

**Verify hooks are registered:**
```bash
python -m json.tool %USERPROFILE%\.claude\settings.json
```

Look for `"agenttalk"` entries under `"hooks"` > `"Stop"` and `"hooks"` > `"SessionStart"`.

**Fix:** Re-run `agenttalk setup` to re-register the hooks. The registration is idempotent and will not duplicate existing entries.

**Verify the hook paths are correct:** The hook command must point to the pythonw.exe in your current Python environment. If you have reinstalled AgentTalk into a different venv, re-run `agenttalk setup` to update the paths.

**Verify async hooks:** Both hooks must have `"async": true` to avoid blocking Claude Code's UI. This is set automatically by `agenttalk setup`.

---

## License

MIT — see [LICENSE](LICENSE).

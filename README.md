# AgentTalk

**Real-time, offline text-to-speech for AI coding agents — no API keys, no cloud, no lag.**

Your AI agent's responses are spoken aloud as they complete. Hands-free. Runs locally. Works everywhere.

[![AgentTalk demo](https://img.youtube.com/vi/gpVtaKo4UDc/hqdefault.jpg)](https://youtu.be/gpVtaKo4UDc)

---

## Works with your entire AI stack

| Tool | Integration |
|------|-------------|
| **Claude Code** | Native hooks — auto-speaks every response |
| **Google Antigravity** | Native skill + session workflow |
| **VSCode** + Roo Code + KiloCode | VSIX extension with status bar |
| **opencode** | Session start/stop hooks |
| **OpenClaw** (ClawHub) | Publishable skill |
| **OpenAI CLI** | Pipe wrapper (`openai … \| agenttalk pipe`) |

One service. Any agent. Any IDE.

---

## Install

```bash
pip install git+https://github.com/omernesh/AgentTalk
agenttalk setup
```

**Runs on:** Windows · macOS · Linux · Python 3.11+

For specific integrations, pass additional flags to setup:

```bash
agenttalk setup                   # Claude Code (default)
agenttalk setup --antigravity     # + Google Antigravity IDE
agenttalk setup --opencode        # + opencode
```

After setup, start the service:

```bash
python -m agenttalk.service       # foreground
pythonw -m agenttalk.service      # background (Windows)
```

Or double-click the **AgentTalk** desktop shortcut created by setup.

---

## How it works

AgentTalk runs a local HTTP service on `localhost:5050`. Agent hooks and extensions call `POST /speak` at the end of each response. The service synthesizes speech using [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (default) or [Piper](https://github.com/rhasspy/piper) — fully offline, no cloud, no API keys.

**Audio ducking (Windows):** While AgentTalk is speaking, all other system audio is automatically lowered to 50% volume via the Windows Core Audio API. Volume is restored the moment speech finishes — so you never miss a word over music or a video.

```
Claude Code / VSCode / Antigravity / opencode
           ↓
    POST localhost:5050/speak
           ↓
    Kokoro / Piper TTS engine
           ↓
      🔊 Your speakers
```

---

## Slash commands

Type these as your message in Claude Code (or any supported agent):

| Command | What it does |
|---------|-------------|
| `/agenttalk:mode` | Switch between **auto** (speaks every reply) and **semi-auto** (speak on demand) |
| `/agenttalk:speak` | Speak the last response aloud (semi-auto mode) |
| `/agenttalk:voice [name]` | Switch voice — e.g. `/agenttalk:voice bf_emma` |
| `/agenttalk:model [kokoro\|piper]` | Switch TTS engine |
| `/agenttalk:config` | Interactive configuration menu |
| `/agenttalk:start` | Start the service if it is not running |
| `/agenttalk:stop` | Stop the service and silence audio |
| `/agenttalk:antigravity` | `import antigravity` — you can use AgentTalk to fly 🚀 |

---

## Voices

30 voices across four accent families, all local, all offline:

| Prefix | Region | Voices |
|--------|--------|--------|
| `af_` | American Female | `af_heart` ⭐, `af_bella`, `af_nicole`, `af_aoede`, `af_kore`, `af_sarah`, `af_sky` |
| `am_` | American Male | `am_adam`, `am_michael`, `am_echo`, `am_eric`, `am_fenrir`, `am_liam`, `am_onyx`, `am_puck`, `am_santa` |
| `bf_` | British Female | `bf_emma`, `bf_isabella`, `bf_alice`, `bf_lily` |
| `bm_` | British Male | `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`, `bm_norton`, `bm_oscar` |

Switch anytime with `/agenttalk:voice [name]` or the tray menu. Changes take effect on the next utterance and persist across restarts.

---

## Tray menu (Windows)

Right-click the system tray icon:

- **Mute / Unmute** — instant toggle, checkmark shows current state
- **Model** — submenu: switch between Kokoro and Piper (radio buttons)
- **Voice** — context-aware submenu: Kokoro voices when on Kokoro, Piper `.onnx` stems when on Piper
- **Active: {voice}** — read-only display of the currently selected voice
- **Quit** — stops the service and removes the tray icon

The icon animates while speaking and returns to default when playback finishes.

---

## Configuration

All settings live in the platform config directory and persist across restarts. Change them at runtime — no restart needed.

| Platform | Config location |
|----------|----------------|
| Windows | `%APPDATA%\AgentTalk\config.json` |
| macOS | `~/Library/Application Support/AgentTalk/config.json` |
| Linux | `~/.config/AgentTalk/config.json` |

| Setting | Default | How to change |
|---------|---------|---------------|
| `voice` | `af_heart` | `/agenttalk:voice [name]` or tray |
| `model` | `kokoro` | `/agenttalk:model [kokoro\|piper]` or tray |
| `speech_mode` | `auto` | `/agenttalk:mode` |
| `speed` | `1.0` | `/agenttalk:config` → option 4 |
| `volume` | `1.0` | `/agenttalk:config` → option 5 |
| `muted` | `false` | Tray → Mute |
| `pre_cue_path` | `null` | `/agenttalk:config` → option 1 |
| `post_cue_path` | `null` | `/agenttalk:config` → option 2 |

---

## Integrations

### Claude Code (built-in)

`agenttalk setup` automatically registers `Stop` and `SessionStart` hooks in `~/.claude/settings.json`.

### Google Antigravity

```bash
agenttalk setup --antigravity
```

Installs a native Antigravity skill to `~/.gemini/antigravity/skills/agenttalk.md` and a session startup workflow to `~/.gemini/antigravity/global_workflows/agenttalk_start.md`. Alternatively, install the VSCode VSIX extension directly — Antigravity is a VS Code fork and the extension is fully compatible.

### VSCode / Roo Code / KiloCode

Install the extension from `integrations/vscode/`:

```bash
code --install-extension integrations/vscode/agenttalk-vscode-1.0.0.vsix
```

The extension auto-detects Roo Code and KiloCode and hooks their message events. A status bar item shows service state.

### opencode

```bash
agenttalk setup --opencode
```

Registers `session_start_hook.py` and `stop_hook.py` in `~/.config/opencode/hooks/`.

### OpenAI CLI

```bash
# Pipe any CLI tool through AgentTalk
openai api chat.completions.create … | python integrations/openai-cli/stream_speak.py
```

Or source the shell function from `integrations/openai-cli/README.md` for a `speak-openai` shortcut.

### OpenClaw (ClawHub)

The skill file at `integrations/openclaw/SKILL.md` (also available at the URL below) contains
both the installation walkthrough and the agent operating instructions. Point OpenClaw at it
and ask it to install AgentTalk — the agent follows the steps autonomously.

**Option A — let OpenClaw install from the raw file:**

In an OpenClaw session, paste this prompt:

```
Read https://raw.githubusercontent.com/omernesh/AgentTalk/main/integrations/openclaw/SKILL.md
and follow the AI Agent Installation Instructions to install AgentTalk on this machine.
```

OpenClaw will run `pip install agenttalk`, call `agenttalk setup --no-autostart`, start the
service, and verify it is healthy — all without leaving the session.

**Option B — register as a persistent skill:**

Add the skill to your ClawHub workspace so it loads automatically every session:

```bash
clawhub install https://raw.githubusercontent.com/omernesh/AgentTalk/main/integrations/openclaw/SKILL.md
```

Once installed, OpenClaw checks the service is running at session start and speaks each
response automatically (auto mode) or on demand via `/agenttalk:speak` (semi-auto mode).

---

## REST API

The service exposes a simple HTTP API at `localhost:5050`:

```bash
# Speak text
curl -s -X POST localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from AgentTalk"}'

# Check service status
curl localhost:5050/health

# Get / update config
curl localhost:5050/config
curl -X POST localhost:5050/config -d '{"voice": "bf_emma", "speed": 1.2}'

# Mute / unmute
curl -X POST localhost:5050/mute
curl -X POST localhost:5050/unmute
```

---

## Troubleshooting

### Service not speaking

1. Check it's running: `curl localhost:5050/health`
2. Check hooks are registered: look for `agenttalk` in `~/.claude/settings.json` under `hooks.Stop` and `hooks.SessionStart`
3. Re-run `agenttalk setup` to re-register (idempotent — won't duplicate)

### WASAPI exclusive mode conflicts (Windows)

**Symptom:** No audio, or `PaErrorCode -9984` in the log.

**Fix:** In Windows Sound Settings, set your output device to "Shared" mode. Check `config.json` dir for `agenttalk.log` to see which audio mode was detected.

### Kokoro model download fails

Re-run `agenttalk setup` — downloads are idempotent. Ensure `github.com` is reachable and you have ~400 MB free.

### Python 3.12+ on Windows

The tray icon uses `pystray`, which has a known GIL compatibility issue on Python 3.12 on Windows. Use Python 3.11 if you need the tray icon on Windows. macOS and Linux are unaffected.

```bash
py -3.11 -m venv .venv && .venv\Scripts\activate
pip install git+https://github.com/omernesh/AgentTalk
agenttalk setup
```

---

## License

MIT

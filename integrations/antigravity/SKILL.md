# AgentTalk — Real-Time Voice for Google Antigravity

AgentTalk gives your Antigravity sessions a voice. Every assistant response is spoken
aloud through your speakers using a local, offline TTS engine (no API keys required).

---

## Setup (run once)

When this skill is first activated, ensure AgentTalk is installed and ready:

```bash
pip install agenttalk
agenttalk setup --antigravity
```

This downloads the Kokoro ONNX model (~310 MB), registers Claude Code hooks, and copies
the AgentTalk skill and workflow files to the correct Antigravity directories:
- Skill: `~/.gemini/antigravity/skills/agenttalk.md`
- Workflow: `~/.gemini/antigravity/global_workflows/agenttalk_start.md`

To start the AgentTalk service manually:

```bash
python -m agenttalk.service
```

The service runs on `localhost:5050`. Verify it is running:

```bash
curl http://localhost:5050/health
# Expected: {"status": "ok"}
```

---

## How It Works

AgentTalk is a local FastAPI service that accepts text via HTTP POST and speaks it
using the Kokoro ONNX text-to-speech engine. No data leaves your machine.

**Endpoint:** `POST http://localhost:5050/speak`
**Body:** `{"text": "text to speak"}`

---

## Agent Instructions

As an Antigravity agent with this skill active, follow these rules:

### Session Start

At the beginning of each session, check if AgentTalk is running:

```bash
curl -s http://localhost:5050/health 2>/dev/null || echo "offline"
```

If the response is not `{"status": "ok"}`, start the service in the background:

- **Windows:** `start pythonw -m agenttalk.service`
- **macOS/Linux:** `python -m agenttalk.service &`

### After Each Response

After completing each assistant response, POST the response text to AgentTalk:

```bash
curl -s -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"<YOUR_RESPONSE_TEXT>\"}"
```

Replace `<YOUR_RESPONSE_TEXT>` with the actual assistant response text (trimmed
to the key spoken content — omit code blocks, file contents, and long outputs).

### Muting

If the user asks to mute AgentTalk:

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"muted": true}'
```

To unmute:

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"muted": false}'
```

---

## Slash Commands

Users can control AgentTalk via these slash commands in their session:

### `/agenttalk:voice <voice_id>`

Switch the TTS voice. Available Kokoro voices:
`af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `af_sky`,
`am_adam`, `am_michael`, `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"voice": "<voice_id>"}'
```

### `/agenttalk:model <kokoro|piper>`

Switch the TTS engine:

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"model": "kokoro"}'
```

### `/agenttalk:stop`

Stop the service:

```bash
curl -X POST http://localhost:5050/stop
```

### `/agenttalk:start`

Start the service (if not running):

- **Windows:** `start pythonw -m agenttalk.service`
- **macOS/Linux:** `python -m agenttalk.service &`

---

## VS Code Extension

Antigravity is a VS Code fork, so the existing AgentTalk VS Code extension VSIX is
also compatible. Install it from Antigravity's Extensions panel:

1. Open the Extensions panel in Antigravity
2. Click `...` (More Actions) > **Extensions: Install from VSIX**
3. Select: `integrations/vscode/agenttalk-vscode-1.0.0.vsix`

The extension provides a status bar indicator and automatic service start — no agent
instruction reliance required for service startup.

---

## Platforms

AgentTalk works on Windows, macOS, and Linux.

| Platform | Config dir | Auto-start |
|----------|-----------|------------|
| Windows  | `%APPDATA%\AgentTalk\` | Task Scheduler |
| macOS    | `~/Library/Application Support/AgentTalk/` | launchd |
| Linux    | `~/.config/AgentTalk/` | systemd --user |

---

## Troubleshooting

**Service not starting:**
```bash
python -m agenttalk.service  # Run in foreground to see errors
```

**Model files missing:**
```bash
agenttalk setup --antigravity  # Re-run setup to download model files
```

**Port 5050 in use:**
The service will fail to start if another process is using port 5050.
Check with: `netstat -ano | findstr 5050` (Windows) or `lsof -i :5050` (macOS/Linux)

---

## Links

- GitHub: https://github.com/omernesh/AgentTalk
- PyPI: https://pypi.org/project/agenttalk/
- API docs (when running): http://localhost:5050/docs

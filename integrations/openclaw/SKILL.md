# AgentTalk — Real-Time Voice for OpenClaw

AgentTalk gives your OpenClaw sessions a voice. Every assistant response is spoken
aloud through your speakers using a local, offline TTS engine (no API keys required).

---

## AI Agent: Installation Instructions

> **Read this section if AgentTalk is not yet installed.** Follow these steps in
> order. Each step is idempotent — safe to re-run if interrupted.

### Step 1 — Check if already installed

```bash
pip show agenttalk
```

If this prints package info, skip to **Step 3**. If it prints an error, continue.

### Step 2 — Install

```bash
pip install agenttalk
```

### Step 3 — Run first-time setup

Downloads the Kokoro ONNX model (~310 MB) and creates the config directory.
Use `--no-autostart` for OpenClaw (no system service registration needed).

```bash
agenttalk setup --no-autostart
```

Expected output ends with: `Setup complete.`

If the model is already downloaded, this is fast and safe to re-run.

### Step 4 — Start the service

**Windows:**
```bash
start /B pythonw -m agenttalk.service
```

**macOS / Linux:**
```bash
python -m agenttalk.service &
```

### Step 5 — Verify

```bash
curl http://localhost:5050/health
```

Expected: `{"status":"ok"}`

If you see a connection error, wait 3 seconds and retry (model load takes ~2s).

---

## AI Agent: Session Start (every session)

At the beginning of each session, verify the service is running:

```bash
curl -s http://localhost:5050/health 2>/dev/null || echo "offline"
```

If the response is not `{"status":"ok"}`, start it (see Step 4 above).

---

## AI Agent: After Each Response

After completing each assistant response, POST the response text to AgentTalk:

```bash
curl -s -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "<YOUR_RESPONSE_TEXT>"}'
```

**Guidelines for `<YOUR_RESPONSE_TEXT>`:**
- Use the full prose response — AgentTalk's preprocessor strips markdown, code blocks, and URLs automatically
- Do NOT manually truncate or summarize — the service handles filtering
- Omit raw file contents or tool outputs that were not part of your assistant reply

---

## How It Works

AgentTalk is a local FastAPI service. Text is preprocessed (markdown stripped,
paragraphs split into sentences) and queued to the Kokoro ONNX TTS engine.
No data leaves the machine.

**Endpoint:** `POST http://localhost:5050/speak`
**Body:** `{"text": "text to speak"}`

---

## User Commands

### Voice

Switch the TTS voice:

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"voice": "<voice_id>"}'
```

Available Kokoro voices:
`af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `af_sky`,
`am_adam`, `am_michael`, `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`

### Speed and Volume

```bash
# Speed (default 1.0, range 0.5–2.0)
curl -X POST http://localhost:5050/config -H "Content-Type: application/json" \
  -d '{"speed": 1.3}'

# Volume (default 1.0, range 0.1–2.0)
curl -X POST http://localhost:5050/config -H "Content-Type: application/json" \
  -d '{"volume": 0.8}'
```

### Mute / Unmute

```bash
# Mute
curl -X POST http://localhost:5050/config -H "Content-Type: application/json" \
  -d '{"muted": true}'

# Unmute
curl -X POST http://localhost:5050/config -H "Content-Type: application/json" \
  -d '{"muted": false}'
```

### Speech Mode

```bash
# auto — speak every response (default)
curl -X POST http://localhost:5050/config -H "Content-Type: application/json" \
  -d '{"speech_mode": "auto"}'

# semi-auto — only speak when explicitly requested
curl -X POST http://localhost:5050/config -H "Content-Type: application/json" \
  -d '{"speech_mode": "semi-auto"}'
```

### Speak on Demand (semi-auto mode)

```bash
curl -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "<text to speak>"}'
```

### Stop the Service

```bash
curl -X POST http://localhost:5050/stop
```

### Check Current Config

```bash
curl http://localhost:5050/config
```

---

## Platforms

| Platform | Config dir | Model dir |
|----------|-----------|-----------|
| Windows  | `%APPDATA%\AgentTalk\` | `%APPDATA%\AgentTalk\models\` |
| macOS    | `~/Library/Application Support/AgentTalk/` | same |
| Linux    | `~/.config/AgentTalk/` | same |

---

## Troubleshooting

**Service not starting:**
```bash
python -m agenttalk.service  # Run in foreground to see error output
```

**Model files missing (setup needed):**
```bash
agenttalk setup --no-autostart
```

**Port 5050 in use:**
```bash
# Windows
netstat -ano | findstr 5050

# macOS / Linux
lsof -i :5050
```

**Health check returns 200 but no audio:**
- Confirm your system audio is not muted
- Check `curl http://localhost:5050/config` — `"muted"` should be `false`

---

## Links

- GitHub: https://github.com/omernesh/AgentTalk
- PyPI: https://pypi.org/project/agenttalk/
- API docs (when service is running): http://localhost:5050/docs

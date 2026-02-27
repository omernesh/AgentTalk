# AgentTalk — Google Antigravity Integration

Real-time voice output for [Google Antigravity](https://antigravity.dev) (agent-first VS Code fork).

AgentTalk's Antigravity integration uses Antigravity's native skills system to teach
the agent to speak responses aloud via a local TTS service. No cloud services, no API
keys — all processing is local.

---

## Quick Setup

```bash
pip install agenttalk
agenttalk setup --antigravity
```

This will:
1. Download the Kokoro ONNX model (~310 MB)
2. Register Claude Code hooks
3. Copy the AgentTalk skill to `~/.gemini/antigravity/skills/agenttalk.md`
4. Copy the session workflow to `~/.gemini/antigravity/global_workflows/agenttalk_start.md`

After running, open Antigravity — the agenttalk skill is immediately active.

---

## VS Code Extension Alternative

Because Antigravity is a VS Code fork, the existing AgentTalk VS Code extension VSIX
also works in Antigravity. This gives you a UI status bar indicator and automatic
service startup without relying solely on agent instructions.

**To install:**
1. Open Antigravity's Extensions panel
2. Click `...` (More Actions) > **Extensions: Install from VSIX**
3. Select: `integrations/vscode/agenttalk-vscode-1.0.0.vsix`

---

## Manual Setup

If you prefer to place files manually:

| File | Destination |
|------|-------------|
| `integrations/antigravity/SKILL.md` | `~/.gemini/antigravity/skills/agenttalk.md` |
| `integrations/antigravity/session_workflow.md` | `~/.gemini/antigravity/global_workflows/agenttalk_start.md` |

**Platform paths for `~/.gemini/`:**

| Platform | Full path |
|----------|-----------|
| Windows  | `C:\Users\<username>\.gemini\antigravity\` |
| macOS    | `/Users/<username>/.gemini/antigravity/` |
| Linux    | `/home/<username>/.gemini/antigravity/` |

---

## How It Works

1. **Skill file** (`~/.gemini/antigravity/skills/agenttalk.md`) — teaches the Antigravity
   agent to POST each response to `http://localhost:5050/speak` after completing it.

2. **Session workflow** (`~/.gemini/antigravity/global_workflows/agenttalk_start.md`) —
   tells the agent to check and start the AgentTalk service at session start.

3. **AgentTalk service** — local FastAPI app listening on port 5050, converts text to
   speech using Kokoro ONNX.

**Endpoint:** `POST http://localhost:5050/speak`
**Body:** `{"text": "text to speak"}`

---

## Troubleshooting

**Service not starting:**
```bash
python -m agenttalk.service  # Run in foreground to see errors
```

**Skill not active:**
- Confirm `~/.gemini/antigravity/skills/agenttalk.md` exists
- Restart Antigravity to reload skills

**Model files missing:**
```bash
agenttalk setup --antigravity  # Re-run to download model files
```

**Port 5050 in use:**
```bash
# Windows
netstat -ano | findstr 5050
# macOS/Linux
lsof -i :5050
```

---

## Links

- GitHub: https://github.com/omernesh/AgentTalk
- PyPI: https://pypi.org/project/agenttalk/
- API docs (when service running): http://localhost:5050/docs

# AgentTalk opencode Integration

Speak opencode agent responses aloud using AgentTalk TTS.

This integration mirrors the Claude Code hook pattern — two Python scripts
that POST to the AgentTalk service on localhost:5050.

---

## Quick Setup

```bash
pip install agenttalk
agenttalk setup --opencode
```

This registers the hooks in your opencode configuration automatically.

---

## Manual Setup

If `agenttalk setup --opencode` fails, register the hooks manually.

### 1. Find your opencode config directory

| Platform | Path |
|----------|------|
| Windows  | `%APPDATA%\opencode\` or `~/.opencode/` |
| macOS    | `~/.opencode/` |
| Linux    | `~/.opencode/` or `$XDG_CONFIG_HOME/opencode/` |

### 2. Add hooks to opencode config

The opencode hooks configuration is typically in `~/.opencode/config.json`
or `~/.opencode/settings.json`. Add entries for the two hook scripts:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "python",
        "args": ["/path/to/integrations/opencode/session_start_hook.py"],
        "async": true
      }
    ],
    "PostResponse": [
      {
        "command": "python",
        "args": ["/path/to/integrations/opencode/stop_hook.py"],
        "async": true
      }
    ]
  }
}
```

Replace `/path/to/integrations/opencode/` with the actual path where you
cloned AgentTalk or where the scripts are installed.

### 3. Alternative: Copy scripts to opencode hooks directory

If opencode uses a directory-based hook discovery (e.g., `~/.opencode/hooks/`):

```bash
# Create the hooks directory
mkdir -p ~/.opencode/hooks

# Copy the hook scripts
cp integrations/opencode/session_start_hook.py ~/.opencode/hooks/
cp integrations/opencode/stop_hook.py ~/.opencode/hooks/
```

---

## How It Works

### Session Start Hook (`session_start_hook.py`)

- Checks if AgentTalk is running (via PID file)
- If not running, launches the service as a detached process
- Works on Windows (DETACHED_PROCESS), macOS/Linux (start_new_session=True)

### Stop Hook / PostResponse Hook (`stop_hook.py`)

- Reads the assistant message from stdin JSON
- Checks current `speech_mode` setting
- If `speech_mode == "semi-auto"`, skips speaking (respects user preference)
- Otherwise, POSTs the message text to `http://localhost:5050/speak`

---

## Endpoint

All text is sent to: `POST http://localhost:5050/speak`

```bash
# Test manually
curl -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from opencode!"}'
```

---

## Comparison to Claude Code Integration

| Feature | Claude Code | opencode |
|---------|------------|---------|
| Hook mechanism | `~/.claude/settings.json` | `~/.opencode/config.json` |
| Session start | `SessionStart` hook | `SessionStart` hook |
| Post-response | `Stop` hook | `PostResponse` hook |
| Hook format | `{matcher, hooks: [{type, command}]}` | `{command, args, async}` |
| stdin payload | `{last_assistant_message, ...}` | `{content, text, ...}` |

The hook scripts handle key variations via fallback key lookup.

---

## Troubleshooting

**Service not starting:**
```bash
python -m agenttalk.service  # Run in foreground to see errors
```

**Hook not firing:**
Check opencode logs for hook execution errors.
Verify the Python executable path is correct in your opencode config.

**Testing the hook manually:**
```bash
echo '{"last_assistant_message": "test message"}' | python integrations/opencode/stop_hook.py
```

---

## Links

- AgentTalk: https://github.com/omernesh/AgentTalk
- opencode: https://opencode.ai
- opencode docs: https://opencode.ai/docs

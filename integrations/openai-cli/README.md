# AgentTalk OpenAI CLI Integration

Speak OpenAI CLI responses aloud using AgentTalk TTS.

---

## Research Findings

The official OpenAI CLI (`pip install openai`) and the OpenAI Responses API CLI
do not have a built-in hook or plugin system equivalent to Claude Code's hooks.

**Available integration approaches:**

1. **Pipe wrapper** (recommended) — pipe OpenAI CLI output through a TTS filter
2. **Shell function wrapper** — wrap the `openai` command in a shell function
3. **Python script wrapper** — call OpenAI API with streaming and POST to AgentTalk

---

## Approach 1: Pipe Wrapper (Recommended)

The `agenttalk pipe` command reads from stdin line-by-line and POSTs each
meaningful line to localhost:5050/speak:

```bash
# Pipe OpenAI CLI output through AgentTalk
openai api chat.completions.create \
  -m gpt-4o \
  -g user "What is Python?" \
  | python -m agenttalk.pipe
```

The `pipe` subcommand reads stdin, accumulates complete sentences, and POSTs
them to localhost:5050/speak. This works with any CLI tool that outputs text.

---

## Approach 2: Shell Function Wrapper

Add this to your `~/.bashrc` or `~/.zshrc`:

```bash
# Wrap openai CLI to speak responses via AgentTalk
openai-with-tts() {
    openai "$@" | python -m agenttalk.pipe
}
```

Or for PowerShell (`$PROFILE`):

```powershell
function Invoke-OpenAIWithTTS {
    openai @args | python -m agenttalk.pipe
}
Set-Alias openai-tts Invoke-OpenAIWithTTS
```

Usage:
```bash
openai-with-tts api chat.completions.create -m gpt-4o -g user "Hello!"
```

---

## Approach 3: Python Streaming Script

For streaming responses with real-time TTS, use the included `stream_speak.py`:

```bash
python integrations/openai-cli/stream_speak.py "What is quantum computing?"
```

This script:
1. Calls the OpenAI API with streaming enabled
2. Accumulates tokens into complete sentences
3. POSTs each complete sentence to AgentTalk as it arrives

---

## Setup

1. Install AgentTalk and OpenAI:
   ```bash
   pip install agenttalk openai
   ```

2. Start the AgentTalk service:
   ```bash
   python -m agenttalk.service
   ```

3. Set your OpenAI API key:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

4. Use one of the approaches above.

---

## agenttalk pipe Command

The `pipe` command is a thin stdin-to-TTS bridge. Install agenttalk and run:

```bash
echo "Hello world" | python -m agenttalk.pipe
```

Or register as a CLI command (after `pip install agenttalk`):
```bash
# Not yet a registered entry point — use python -m agenttalk.pipe
```

---

## Notes

- The pipe approach works with ANY CLI tool, not just OpenAI CLI
- Works with: `curl`, `httpie`, `llm` CLI, `fabric`, `sgpt`, etc.
- The AgentTalk service handles all TTS — zero audio logic in the pipe script
- `agenttalk.pipe` reads complete lines and uses the preprocessor to filter
  non-speakable content (code blocks, URLs, etc.)

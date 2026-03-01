---
name: model
description: "Switch the AgentTalk TTS engine. Run without arguments to pick from the list."
argument-hint: [engine-name]
allowed-tools: Bash
---

Switch the AgentTalk TTS engine to $ARGUMENTS.

**If $ARGUMENTS is empty or blank**, display this pick list and ask the user to choose:

```
1. kokoro      — Kokoro ONNX (default, English, high quality, downloaded during setup)
2. piper       — Piper TTS (alternative English, requires separate model download)
3. lightblue   — Hebrew TTS via Light-BlueTTS (local, requires onnx_models setup)
4. hebrewpiper — Hebrew TTS via PiperStream Docker service (requires `docker compose up`)
```

Wait for the user to type a number or engine name, then run the curl below.

**If $ARGUMENTS is an engine name or number**, resolve it to one of: kokoro, piper, lightblue, hebrewpiper and run:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"RESOLVED_ENGINE\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, confirm: "Engine switched to [engine]."
If the response contains `"piper_model_path"` error, say: "Piper model is not downloaded yet. Run 'agenttalk setup --piper' to download it."
If the response contains `"onnx_dir"` error, say: "Light-BlueTTS models not configured. See docs/hebrew-tts-setup.md for setup instructions."
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."

## Examples

```bash
# Switch to Hebrew (PiperStream — easier setup, requires Docker):
/agenttalk:model hebrewpiper

# Switch to Hebrew (Light-BlueTTS — better quality, local, no Docker):
/agenttalk:model lightblue

# Switch back to English:
/agenttalk:model kokoro
```

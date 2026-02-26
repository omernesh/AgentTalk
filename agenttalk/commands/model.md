---
name: model
description: "Switch the AgentTalk TTS engine. Run without arguments to pick from the list."
argument-hint: [engine-name]
allowed-tools: Bash
---

Switch the AgentTalk TTS engine to $ARGUMENTS.

**If $ARGUMENTS is empty or blank**, display this pick list and ask the user to choose:

```
1. kokoro — Kokoro ONNX (default, high quality, downloaded during setup)
2. piper  — Piper TTS (alternative, requires separate model download)
```

Wait for the user to type a number or engine name, then run the curl below.

**If $ARGUMENTS is an engine name or number**, resolve it to `kokoro` or `piper` and run:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"RESOLVED_ENGINE\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, confirm: "Engine switched to [engine]."
If the response contains `"piper_model_path"` error, say: "Piper model is not downloaded yet. Run 'agenttalk setup --piper' to download it."
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."

---
name: model
description: "Switch the AgentTalk TTS engine. Options: kokoro (default), piper"
argument-hint: [kokoro|piper]
disable-model-invocation: true
allowed-tools: Bash
---

Switch the AgentTalk TTS engine to $ARGUMENTS.

Run this command:
```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"$ARGUMENTS\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, say "TTS engine switched to $ARGUMENTS. The next utterance will use this engine."
If the response contains `"status": "error"`, display the reason from the response. If the reason mentions "Piper model path not configured", say "Piper model is not downloaded yet. Run 'agenttalk setup --piper' to download it."
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."

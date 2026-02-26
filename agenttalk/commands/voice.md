---
name: voice
description: "Switch the AgentTalk TTS voice. Available: af_heart, af_bella, af_nicole, af_sarah, af_sky, am_adam, am_michael, bf_emma, bf_isabella, bm_george, bm_lewis"
argument-hint: [voice-name]
disable-model-invocation: true
allowed-tools: Bash
---

Switch the AgentTalk TTS voice to $ARGUMENTS.

Run this command:
```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"voice\": \"$ARGUMENTS\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, say "Voice switched to $ARGUMENTS. The next utterance will use this voice."
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."

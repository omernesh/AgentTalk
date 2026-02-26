---
name: stop
description: Stop the AgentTalk TTS service and silence any current audio
disable-model-invocation: true
allowed-tools: Bash
---

Stop the AgentTalk service.

Run this command:
```bash
curl -s -X POST http://localhost:5050/stop --max-time 3 || true
```

If the command succeeds and returns `{"status": "stopped"}`, say "AgentTalk service stopped."
If the connection was refused (service was already stopped), say "AgentTalk service was not running."
If the connection was reset mid-request (service stopped while responding — this is normal), say "AgentTalk service stopped."

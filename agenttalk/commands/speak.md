---
name: speak
description: "Speak the last assistant reply aloud (use in semi-auto mode or to replay audio)."
allowed-tools: Bash
---

Speak the last assistant reply aloud by POSTing it to the AgentTalk service.

Use the `$LAST_RESPONSE` variable (Claude Code's built-in that contains the last assistant message text) and run:

```bash
curl -s -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$LAST_RESPONSE\"}" \
  --max-time 5
```

Substitute `$LAST_RESPONSE` directly in the `-d` argument so the full text of the last reply is sent as the `text` field.

Then interpret the response:

- If the HTTP status is **202** or the JSON contains `"status": "queued"`: say "Speaking last reply."
- If the HTTP status is **200** or the JSON contains `"status": "skipped"`: say "No speakable content in the last reply (code-only or empty)."
- If the connection is refused (exit code 7 or `curl: (7)`): say "AgentTalk service is not running. Start it with /agenttalk:start."
- For any other error: report the curl output.

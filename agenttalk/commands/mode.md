---
name: mode
description: "Switch AgentTalk speech mode: auto (speaks every reply) or semi-auto (only speaks when /speak is invoked)."
argument-hint: [auto|semi-auto]
allowed-tools: Bash
---

Switch the AgentTalk speech mode between `auto` (speak every reply automatically) and `semi-auto` (only speak when you run /speak).

**Step 1: Read current mode**

```bash
curl -s http://localhost:5050/config --max-time 5
```

If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start." and stop.

Parse `speech_mode` from the JSON response. This is the current mode.

**Step 2: Resolve the target mode**

If `$ARGUMENTS` is empty, display the pick list and ask the user to choose:

```
AgentTalk Speech Mode
─────────────────────────────────────────
1. auto      — Speak every reply automatically (current behavior)
2. semi-auto — Only speak when you run /speak
─────────────────────────────────────────
Current mode: [insert current speech_mode here]
```

Ask: "Pick 1 or 2 (or type 'auto' / 'semi-auto'):"

If `$ARGUMENTS` is provided, resolve it:
- `"1"` or `"auto"` → `auto`
- `"2"` or `"semi-auto"` → `semi-auto`
- Anything else: tell the user the valid options and stop.

**Step 3: Apply the new mode**

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"speech_mode\": \"RESOLVED_MODE\"}" \
  --max-time 5
```

Replace `RESOLVED_MODE` with the resolved value (`auto` or `semi-auto`).

**Step 4: Confirm**

- If response contains `"status": "ok"`: say "Speech mode set to [mode]." followed by:
  - If `semi-auto`: "Run /speak after any reply to hear it aloud."
  - If `auto`: "AgentTalk will speak every reply automatically."
- If the connection is refused: say "AgentTalk service is not running. Start it with /agenttalk:start."

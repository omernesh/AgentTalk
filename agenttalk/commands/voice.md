---
name: voice
description: "Switch the AgentTalk TTS voice. Run without arguments to pick from the list."
argument-hint: [voice-name]
allowed-tools: Bash
---

Switch the AgentTalk TTS voice to $ARGUMENTS.

**If $ARGUMENTS is empty or blank**, display this numbered pick list to the user and ask them to type a number to select:

```
1.  af_heart    — American Female (warm, default)
2.  af_bella    — American Female (bright)
3.  af_nicole   — American Female (calm)
4.  af_sarah    — American Female (clear)
5.  af_sky      — American Female (airy)
6.  am_adam     — American Male
7.  am_michael  — American Male
8.  bf_emma     — British Female
9.  bf_isabella — British Female
10. bm_george   — British Male
11. bm_lewis    — British Male
```

Wait for the user to type a number or voice name, resolve it to the voice ID, then run the curl below.

**If $ARGUMENTS is a voice name or number**, resolve it to the correct voice ID and run:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"voice\": \"RESOLVED_VOICE_ID\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, confirm: "Voice switched to [voice-id]."
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."

---
name: voice
description: "Switch the AgentTalk TTS voice. Run without arguments to pick from the list."
argument-hint: [voice-name]
allowed-tools: Bash
---

Switch the AgentTalk TTS voice to $ARGUMENTS.

First check the active engine and available voices:

```bash
curl -s http://localhost:5050/config --max-time 5
curl -s http://localhost:5050/piper-voices --max-time 5
```

If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start." and stop.

---

**If `model` is `kokoro`:**

**If $ARGUMENTS is empty or blank**, show this numbered list and ask the user to pick:

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

Wait for user to pick, resolve to voice ID, then:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"voice\": \"RESOLVED_VOICE_ID\"}" \
  --max-time 5
```

---

**If `model` is `piper`:**

The `/piper-voices` response contains a `voices` array of model stems (e.g. `en_US-lessac-medium`) and a `dir` path.

**If $ARGUMENTS is empty or blank**, show the voices as a numbered list and ask the user to pick.

Wait for user to pick, build the full path as `dir + "/" + stem + ".onnx"`, then:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"piper_model_path\": \"FULL_PATH\"}" \
  --max-time 5
```

Note: switching Piper voice triggers an engine reload on the next spoken sentence (takes ~2 s).

---

If `"status": "ok"` in the response, confirm: "Voice switched to [name]."
If connection refused: "AgentTalk service is not running. Start it with /agenttalk:start."

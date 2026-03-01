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
curl -s http://localhost:5050/voices --max-time 5
```

If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start." and stop.

---

The `/voices` response contains a `voices` array with all available voices — Kokoro voices first, then Hebrew voices (he_einav, he_yuval) if LightBlueTTS is configured.

**If $ARGUMENTS is empty or blank**, show the voices as a numbered list grouped by type and ask the user to pick:

- Kokoro voices (English): show with their display names where known
- Hebrew voices (he_einav, he_yuval): label them as "(Hebrew — LightBlueTTS)"

Wait for user to pick, resolve to voice ID, then:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"voice\": \"RESOLVED_VOICE_ID\"}" \
  --max-time 5
```

**If a Hebrew voice is selected (he_*):**

Selecting a Hebrew voice (he_einav or he_yuval) automatically:
- Sets model=lightblue
- Configures lightblue_voice_path to the correct voice file
- Sets voice=he_einav (or he_yuval)

All three STATE changes happen in a single POST /config call — no extra steps needed.

**If `model` is `hebrewpiper`:**

Use the `/hebrew-voices` endpoint to see available voices:

```bash
curl -s http://localhost:5050/hebrew-voices --max-time 5
```

Select a voice by posting to `/config`:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"hebrewpiper_voice\": \"female\"}" \
  --max-time 5
```

HebrewPiper supports `"male"` and `"female"` voices (built into the PiperStream Docker image).

---

**If `model` is `piper`:**

Also fetch piper voices:

```bash
curl -s http://localhost:5050/piper-voices --max-time 5
```

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

If `"status": "ok"` in the response:
- **Hebrew voice (he_*):** confirm in Hebrew — e.g. "הקול הוחלף ל-אינב (עברית). המנוע הוגדר ל-LightBlueTTS."
- **Any other voice:** confirm in English — "Voice switched to [name]."

If connection refused: "AgentTalk service is not running. Start it with /agenttalk:start."

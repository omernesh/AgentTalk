---
name: config
description: "Configure AgentTalk settings: pre/post speech cue sounds, volume, speed, speech mode."
argument-hint: [setting] [value]
allowed-tools: Bash
---

Configure AgentTalk settings.

**If $ARGUMENTS is empty**, display this menu and ask the user what they want to configure:

```
AgentTalk Configuration
─────────────────────────────────────────
1. Pre-speech cue  — WAV played before speaking
2. Post-speech cue — WAV played after speaking
3. Volume          — Playback volume (0.0 – 1.0)
4. Speed           — Speech speed (0.5 – 2.0)
5. Mute            — Toggle mute on/off
6. Speech mode     — auto (always speaks) or semi-auto (only on /speak)
─────────────────────────────────────────
```

Ask the user to pick a number. Then:

- **1 (pre-speech cue)**: Ask "Paste the full path to your WAV file (or type 'none' to disable):"
  - Map the response to `pre_cue_path` (use `null` if user typed "none")
- **2 (post-speech cue)**: Ask "Paste the full path to your WAV file (or type 'none' to disable):"
  - Map the response to `post_cue_path` (use `null` if user typed "none")
- **3 (volume)**: Ask "Enter volume (0.0 – 1.0):" → map to `volume`
- **4 (speed)**: Ask "Enter speed (0.5 – 2.0):" → map to `speed`
- **5 (mute)**: Read current mute state first via `curl -s http://localhost:5050/config --max-time 5`, then toggle it
- **6 (speech mode)**: Read current mode first via `curl -s http://localhost:5050/config --max-time 5`. Show "Current mode: [mode]". Ask "Choose mode: type 'auto' or 'semi-auto':". Map response to `speech_mode` field value. POST `{"speech_mode": "auto"}` or `{"speech_mode": "semi-auto"}` to /config. Confirm: "Speech mode set to [mode]."

Once you have the key and value, run:

```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "PAYLOAD" \
  --max-time 5
```

Where PAYLOAD is the appropriate JSON, e.g. `{"pre_cue_path": "C:/Windows/Media/chimes.wav"}` or `{"pre_cue_path": null}`.

**If $ARGUMENTS is provided**, parse it as `setting value` and apply directly. Examples:
- `pre C:/Windows/Media/chimes.wav` → sets pre_cue_path
- `post C:/Windows/Media/notify.wav` → sets post_cue_path
- `volume 0.8` → sets volume
- `speed 1.2` → sets speed
- `mode auto` → sets speech_mode to "auto"
- `mode semi-auto` → sets speech_mode to "semi-auto"

If the response contains `"status": "ok"`, confirm what was set.
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."

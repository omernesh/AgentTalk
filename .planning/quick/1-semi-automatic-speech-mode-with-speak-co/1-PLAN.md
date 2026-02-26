---
phase: quick-1
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - agenttalk/tts_worker.py
  - agenttalk/service.py
  - agenttalk/config_loader.py
  - agenttalk/hooks/stop_hook.py
  - agenttalk/commands/speak.md
  - agenttalk/commands/mode.md
  - agenttalk/commands/config.md
autonomous: true
requirements: []

must_haves:
  truths:
    - "In auto mode (default), the Stop hook speaks every reply unchanged from current behavior"
    - "In semi-auto mode, the Stop hook returns immediately without queuing audio"
    - "Running /speak explicitly reads the last reply and POSTs it to /speak endpoint"
    - "Running /agenttalk:mode toggles between auto and semi-auto with confirmation"
    - "speech_mode persists across service restarts via config.json"
    - "GET /config returns speech_mode field; POST /config accepts speech_mode"
    - "/agenttalk:config menu includes speech_mode as a numbered option"
  artifacts:
    - path: "agenttalk/tts_worker.py"
      provides: "STATE dict with speech_mode key"
      contains: "speech_mode"
    - path: "agenttalk/service.py"
      provides: "ConfigRequest and GET /config with speech_mode field"
      contains: "speech_mode"
    - path: "agenttalk/config_loader.py"
      provides: "save_config persisting speech_mode"
      contains: "speech_mode"
    - path: "agenttalk/hooks/stop_hook.py"
      provides: "semi-auto guard: fetches /config, skips speak if speech_mode=semi-auto"
      contains: "semi-auto"
    - path: "agenttalk/commands/speak.md"
      provides: "/agenttalk:speak command"
    - path: "agenttalk/commands/mode.md"
      provides: "/agenttalk:mode command"
    - path: "agenttalk/commands/config.md"
      provides: "speech_mode as option 6 in config menu"
  key_links:
    - from: "agenttalk/hooks/stop_hook.py"
      to: "http://localhost:5050/config"
      via: "GET request to read speech_mode before deciding to POST /speak"
      pattern: "speech_mode.*semi.auto"
    - from: "agenttalk/commands/speak.md"
      to: "http://localhost:5050/speak"
      via: "curl POST in slash command body"
      pattern: "localhost:5050/speak"
    - from: "agenttalk/commands/mode.md"
      to: "http://localhost:5050/config"
      via: "curl POST with speech_mode field"
      pattern: "speech_mode"
---

<objective>
Implement semi-automatic speech mode: a `speech_mode` toggle ("auto" vs "semi-auto") that controls
whether the Stop hook auto-speaks every reply or waits for the user to explicitly run /speak.

Purpose: Give users control over when audio plays — useful in meetings, quiet environments, or when
only certain replies need to be heard.
Output: speech_mode field in STATE/config/API, stop_hook guard, two new slash commands,
config menu updated.
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/PROJECT.md

<interfaces>
<!-- Key contracts the executor needs — extracted from existing files. -->

From agenttalk/tts_worker.py:
```python
STATE: dict = {
    "volume": 1.0,
    "speed": 1.0,
    "voice": "af_heart",
    "muted": False,
    "speaking": False,
    "pre_cue_path": None,
    "post_cue_path": None,
    "model": "kokoro",
    "piper_model_path": None,
    # ADD: "speech_mode": "auto"  -- "auto" | "semi-auto"
}
```

From agenttalk/config_loader.py — save_config() persisted fields:
```python
persisted = {
    "voice": state.get("voice", "af_heart"),
    "speed": state.get("speed", 1.0),
    "volume": state.get("volume", 1.0),
    "model": state.get("model", "kokoro"),
    "muted": state.get("muted", False),
    "pre_cue_path": state.get("pre_cue_path"),
    "post_cue_path": state.get("post_cue_path"),
    "piper_model_path": state.get("piper_model_path"),
    # ADD: "speech_mode": state.get("speech_mode", "auto"),
}
```

From agenttalk/service.py — config restore loop in main():
```python
for _key in ("voice", "speed", "volume", "model", "muted", "pre_cue_path", "post_cue_path", "piper_model_path"):
    # ADD "speech_mode" to this tuple
```

From agenttalk/service.py — ConfigRequest (Pydantic):
```python
class ConfigRequest(BaseModel):
    voice: str | None = Field(None, ...)
    speed: float | None = Field(None, ...)
    # ... all existing optional fields
    # ADD: speech_mode: str | None = Field(None, description="'auto' (default) or 'semi-auto'")
```

From agenttalk/service.py — GET /config handler:
```python
return JSONResponse({
    "voice": STATE.get("voice"),
    ...
    # ADD: "speech_mode": STATE.get("speech_mode"),
})
```

From agenttalk/hooks/stop_hook.py — main():
```python
# After extracting `text`, before POSTing to /speak:
# 1. GET http://localhost:5050/config (timeout=2)
# 2. If speech_mode == "semi-auto": sys.exit(0)
# 3. Otherwise: proceed with existing POST /speak logic
```

Pattern for GET in stop_hook (stdlib only, same style as existing POST):
```python
cfg_req = urllib.request.Request('http://localhost:5050/config', method='GET')
try:
    with urllib.request.urlopen(cfg_req, timeout=2) as resp:
        cfg = json.loads(resp.read().decode('utf-8'))
    if cfg.get('speech_mode') == 'semi-auto':
        sys.exit(0)
except urllib.error.URLError:
    pass  # service unreachable — fall through to speak (fail-open: auto mode behavior)
except Exception:
    pass
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add speech_mode to STATE, config persistence, API, and stop_hook guard</name>
  <files>
    agenttalk/tts_worker.py
    agenttalk/config_loader.py
    agenttalk/service.py
    agenttalk/hooks/stop_hook.py
  </files>
  <action>
**agenttalk/tts_worker.py** — Add `"speech_mode": "auto"` to the STATE dict after `"piper_model_path": None`. Default is "auto" (current always-on behavior unchanged).

**agenttalk/config_loader.py** — In `save_config()`, add `"speech_mode": state.get("speech_mode", "auto")` to the `persisted` dict alongside the other 8 fields.

**agenttalk/service.py** — Four changes:
1. `ConfigRequest` model: add optional field `speech_mode: str | None = Field(None, description="Speech mode: 'auto' (speak every reply) or 'semi-auto' (only speak when /speak is invoked).", examples=["auto", "semi-auto"])`.
2. `GET /config` handler (`get_config`): add `"speech_mode": STATE.get("speech_mode")` to the returned dict.
3. `GET /config` docstring: add `- speech_mode: "auto" or "semi-auto"` to the field list.
4. Config restore loop in `main()` — add `"speech_mode"` to the tuple of keys iterated over so it is restored from config.json on startup.

**agenttalk/hooks/stop_hook.py** — After extracting `text` and confirming it is non-empty (line ~36), add a semi-auto guard BEFORE the existing POST logic. Use stdlib urllib only (no new imports). GET /config with a 2-second timeout. If `speech_mode` is `"semi-auto"`, call `sys.exit(0)`. Fail-open on any error (URLError, parse error) — if the service is unreachable or the field is absent, fall through to the existing POST /speak behavior so auto mode remains the effective default. The GET timeout must be short (2s) to avoid blocking Claude Code when the service is not running.

IMPORTANT: Do not touch the `POST /config` handler body — the existing `STATE[key] = value` loop already handles any new key in ConfigRequest as long as that key exists in STATE, which it will after the STATE change above.
  </action>
  <verify>
    python -c "from agenttalk.tts_worker import STATE; assert 'speech_mode' in STATE and STATE['speech_mode'] == 'auto', 'STATE missing speech_mode'"
    python -c "from agenttalk.config_loader import save_config; import json, tempfile, os; os.environ.setdefault('APPDATA', tempfile.mkdtemp()); save_config({'speech_mode': 'semi-auto', 'voice': 'af_heart', 'speed': 1.0, 'volume': 1.0, 'model': 'kokoro', 'muted': False, 'pre_cue_path': None, 'post_cue_path': None, 'piper_model_path': None}); print('save_config OK')"
    python -c "import ast, sys; src=open('agenttalk/hooks/stop_hook.py').read(); assert 'semi-auto' in src, 'stop_hook missing semi-auto guard'; print('stop_hook OK')"
    python -c "import ast, sys; src=open('agenttalk/service.py').read(); assert 'speech_mode' in src, 'service.py missing speech_mode'; print('service OK')"
  </verify>
  <done>
    - STATE["speech_mode"] defaults to "auto"
    - save_config writes speech_mode to config.json
    - GET /config response includes speech_mode field
    - ConfigRequest accepts speech_mode field
    - Config restore loop restores speech_mode from config.json on startup
    - stop_hook exits immediately when speech_mode is "semi-auto", proceeds normally otherwise
  </done>
</task>

<task type="auto">
  <name>Task 2: Create /agenttalk:speak and /agenttalk:mode slash commands</name>
  <files>
    agenttalk/commands/speak.md
    agenttalk/commands/mode.md
  </files>
  <action>
**agenttalk/commands/speak.md** — Create new slash command file. Frontmatter: `name: speak`, `description: "Speak the last assistant reply aloud (use in semi-auto mode or to replay audio)."`, `allowed-tools: Bash`. Body: The command reads `$LAST_RESPONSE` (Claude Code's built-in variable for the last assistant message) and POSTs it to /speak. If service is unreachable, print the appropriate error message. If service returns 202, confirm "Speaking last reply." If 200 (no speakable content), say "No speakable content in the last reply (code-only or empty)." Use this exact curl:
```bash
curl -s -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$LAST_RESPONSE\"}" \
  --max-time 5
```
Note: `$LAST_RESPONSE` is a Claude Code built-in that contains the last assistant message text. The command should instruct Claude to substitute it directly in the -d argument.

If connection is refused: "AgentTalk service is not running. Start it with /agenttalk:start."

**agenttalk/commands/mode.md** — Create new slash command file. Frontmatter: `name: mode`, `description: "Switch AgentTalk speech mode: auto (speaks every reply) or semi-auto (only speaks when /speak is invoked)."`, `argument-hint: [auto|semi-auto]`, `allowed-tools: Bash`. Body:

First read current mode: `curl -s http://localhost:5050/config --max-time 5`. If refused, print service not running error.

If $ARGUMENTS is empty, show pick list:
```
1. auto      — Speak every reply automatically (current behavior)
2. semi-auto — Only speak when you run /speak
Current mode: [show from GET /config response]
```
Ask user to pick. If $ARGUMENTS is provided, resolve "1" → "auto", "2" → "semi-auto", or accept "auto"/"semi-auto" directly.

Then POST:
```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"speech_mode\": \"RESOLVED_MODE\"}" \
  --max-time 5
```

On success: "Speech mode set to [mode]. [If semi-auto: Run /speak to speak the last reply manually. If auto: AgentTalk will speak every reply automatically.]"
If connection refused: "AgentTalk service is not running. Start it with /agenttalk:start."
  </action>
  <verify>
    python -c "
from pathlib import Path
speak = Path('agenttalk/commands/speak.md').read_text()
mode = Path('agenttalk/commands/mode.md').read_text()
assert 'localhost:5050/speak' in speak, 'speak.md missing /speak endpoint'
assert 'LAST_RESPONSE' in speak, 'speak.md missing \$LAST_RESPONSE'
assert 'speech_mode' in mode, 'mode.md missing speech_mode field'
assert 'semi-auto' in mode, 'mode.md missing semi-auto option'
assert 'auto' in mode, 'mode.md missing auto option'
print('Both command files OK')
"
  </verify>
  <done>
    - agenttalk/commands/speak.md exists, POSTs $LAST_RESPONSE to /speak
    - agenttalk/commands/mode.md exists, supports interactive pick list and direct argument
    - Both files have correct frontmatter (name, description, allowed-tools)
    - register_commands() (which globs *.md) will auto-pick both up on next agenttalk setup
  </done>
</task>

<task type="auto">
  <name>Task 3: Add speech_mode option to /agenttalk:config menu</name>
  <files>
    agenttalk/commands/config.md
  </files>
  <action>
Update agenttalk/commands/config.md to add speech_mode as option 6 in the interactive menu.

Update the displayed menu block to:
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

Add handling for option 6:
- **6 (speech mode)**: Read current mode first via GET /config. Show "Current mode: [mode]". Ask "Choose mode: type 'auto' or 'semi-auto':". Map response to `speech_mode` field value. POST `{"speech_mode": "auto"}` or `{"speech_mode": "semi-auto"}` to /config. Confirm: "Speech mode set to [mode]."

Also update the `$ARGUMENTS` shorthand section to support:
- `mode auto` → sets speech_mode to "auto"
- `mode semi-auto` → sets speech_mode to "semi-auto"

The description frontmatter should be updated to include speech_mode: `"Configure AgentTalk settings: pre/post speech cue sounds, volume, speed, speech mode."`
  </action>
  <verify>
    python -c "
from pathlib import Path
cfg = Path('agenttalk/commands/config.md').read_text()
assert '6. Speech mode' in cfg, 'config.md missing option 6'
assert 'speech_mode' in cfg, 'config.md missing speech_mode key'
assert 'semi-auto' in cfg, 'config.md missing semi-auto'
print('config.md OK')
"
  </verify>
  <done>
    - /agenttalk:config menu shows option 6 (speech_mode)
    - Option 6 reads current mode, prompts user, POSTs to /config
    - $ARGUMENTS shorthand supports "mode auto" and "mode semi-auto"
    - Frontmatter description updated
  </done>
</task>

</tasks>

<verification>
After all tasks, run the full verification suite:

```bash
cd D:/docker/claudetalk
python -c "from agenttalk.tts_worker import STATE; assert STATE['speech_mode'] == 'auto'"
python -c "import ast; src=open('agenttalk/hooks/stop_hook.py').read(); assert 'semi-auto' in src"
python -c "src=open('agenttalk/service.py').read(); assert 'speech_mode' in src"
python -c "src=open('agenttalk/config_loader.py').read(); assert 'speech_mode' in src"
python -c "from pathlib import Path; assert Path('agenttalk/commands/speak.md').exists(); assert Path('agenttalk/commands/mode.md').exists()"
python -m pytest tests/ -x -q 2>/dev/null || echo "no tests"
```

Manual smoke test (if service running):
1. `curl -s http://localhost:5050/config` — should include `"speech_mode": "auto"`
2. `curl -s -X POST http://localhost:5050/config -H "Content-Type: application/json" -d '{"speech_mode":"semi-auto"}'` — should return `{"status":"ok","updated":["speech_mode"]}`
3. `curl -s http://localhost:5050/config` — should show `"speech_mode": "semi-auto"`
4. Send a Claude Code message — stop_hook should NOT speak (semi-auto mode)
5. Run /agenttalk:speak — should queue last reply for audio
</verification>

<success_criteria>
- speech_mode defaults to "auto" in STATE; existing behavior unchanged
- stop_hook skips /speak POST when speech_mode is "semi-auto"; fails open if service is unreachable
- /agenttalk:speak command exists and POSTs $LAST_RESPONSE to /speak endpoint
- /agenttalk:mode command exists with interactive pick list and direct argument support
- /agenttalk:config shows speech_mode as option 6
- speech_mode persists via config.json; restored on service restart
- GET /config and POST /config both handle speech_mode field
- All four new/modified source files pass basic import/syntax checks
</success_criteria>

<output>
After completion, create `.planning/quick/1-semi-automatic-speech-mode-with-speak-co/1-SUMMARY.md`
</output>

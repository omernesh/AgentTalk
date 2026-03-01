---
phase: quick-9
plan: 9
type: execute
wave: 1
depends_on: []
files_modified:
  - agenttalk/service.py
  - agenttalk/tray.py
  - agenttalk/translator.py
  - agenttalk/commands/voice.md
  - agenttalk/hooks/user_prompt_hook.py
  - integrations/opencode/user_prompt_hook.py
  - agenttalk/setup.py
autonomous: true
requirements: [QUICK-9]

must_haves:
  truths:
    - "GET /voices returns he_einav and he_yuval when lightblue_onnx_dir is set"
    - "POST /config {voice: 'he_einav'} auto-expands: sets model=lightblue, derives lightblue_voice_path, sets voice=he_einav"
    - "POST /speak with English text translates to Hebrew when model is lightblue/hebrewpiper"
    - "user_prompt_hook.py injects Hebrew instruction when Hebrew model is active"
    - "Tray Voice submenu shows Einav/Yuval items when lightblue_onnx_dir is set"
  artifacts:
    - path: "agenttalk/translator.py"
      provides: "is_hebrew() + translate_to_hebrew() using claude-haiku-4-5-20251001"
      exports: ["is_hebrew", "translate_to_hebrew"]
    - path: "agenttalk/hooks/user_prompt_hook.py"
      provides: "UserPromptSubmit hook — injects Hebrew instruction when model is lightblue/hebrewpiper"
    - path: "integrations/opencode/user_prompt_hook.py"
      provides: "opencode version of user_prompt_hook"
  key_links:
    - from: "service.py POST /config"
      to: "STATE lightblue_voice_path"
      via: "he_ prefix detection + HEBREW_VOICE_MAP lookup + path derivation"
    - from: "service.py POST /speak"
      to: "translator.translate_to_hebrew()"
      via: "model in ('lightblue', 'hebrewpiper') and not is_hebrew(req.text)"
---

<objective>
Integrate Hebrew voices into the unified AgentTalk voice namespace. Selecting he_einav or he_yuval from GET /voices or the tray auto-switches the engine. POST /speak auto-translates English input to Hebrew when a Hebrew engine is active. user_prompt_hook.py injects a Hebrew instruction before Claude generates so translation is a true fallback.

Purpose: Hebrew TTS appears naturally in the same voice picker as English voices — one API call switches engine + voice.
Output: translator.py, user_prompt_hook.py (x2), updated service.py + tray.py + voice.md + setup.py
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/9-hebrew-voices-integration-unified-namesp/../../../docs/plans/2026-03-01-hebrew-voices-integration-design.md
@agenttalk/service.py
@agenttalk/tray.py
@agenttalk/hooks/stop_hook.py
@agenttalk/hooks/session_start_hook.py
@integrations/opencode/stop_hook.py
@agenttalk/setup.py

<interfaces>
<!-- Key types the executor needs. Extracted from agenttalk/service.py and tray.py. -->

From agenttalk/tray.py:
```python
KOKORO_VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
                 "am_adam", "am_michael", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"]
```

From agenttalk/service.py STATE keys (from tts_worker import):
```python
STATE keys: voice, model, speed, volume, muted, pre_cue_path, post_cue_path,
            piper_model_path, speech_mode, hebrewpiper_host, hebrewpiper_voice,
            lightblue_onnx_dir, lightblue_phonikud_path, lightblue_voice_path
```

From agenttalk/service.py existing list_voices():
```python
def list_voices():
    from agenttalk.tray import KOKORO_VOICES
    return JSONResponse({"voices": KOKORO_VOICES})
```

From agenttalk/service.py existing update_config():
```python
async def update_config(req: ConfigRequest):
    updates = req.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key in STATE:
            STATE[key] = value
    save_config(STATE)
```

HEBREW_VOICE_MAP (define in both service.py and tray.py, or import):
```python
HEBREW_VOICE_MAP = {"einav": "female1", "yuval": "male1"}
# Voice ID he_einav → strip he_ → "einav" → HEBREW_VOICE_MAP["einav"] = "female1"
# Path: {lightblue_onnx_dir}/../voices/female1.json
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Voice namespace — service.py + tray.py + voice.md</name>
  <files>agenttalk/service.py, agenttalk/tray.py, agenttalk/commands/voice.md</files>
  <action>
**service.py changes:**

1. Add at module level (after imports, near top):
```python
HEBREW_VOICE_MAP = {"einav": "female1", "yuval": "male1"}
```

2. Replace `list_voices()` body:
```python
def list_voices():
    from agenttalk.tray import KOKORO_VOICES
    voices = list(KOKORO_VOICES)
    if STATE.get("lightblue_onnx_dir"):
        voices += [f"he_{name}" for name in HEBREW_VOICE_MAP]
    return JSONResponse({"voices": voices})
```

3. In `update_config()`, add Hebrew voice auto-expansion BEFORE the existing `for key, value in updates.items()` loop:
```python
# Hebrew voice auto-expansion: he_einav → model=lightblue + lightblue_voice_path + voice=he_einav
if updates.get("voice", "").startswith("he_"):
    stem = updates["voice"][3:]  # strip "he_"
    filename = HEBREW_VOICE_MAP.get(stem)
    if filename is None:
        return JSONResponse({"status": "error", "reason": f"Unknown Hebrew voice: {updates['voice']}"}, status_code=400)
    onnx_dir = STATE.get("lightblue_onnx_dir")
    if not onnx_dir:
        return JSONResponse({"status": "error", "reason": "lightblue_onnx_dir not configured. Set it first via POST /config."}, status_code=400)
    voice_path = str(Path(onnx_dir).parent / "voices" / f"{filename}.json")
    updates["model"] = "lightblue"
    updates["lightblue_voice_path"] = voice_path
    # updates["voice"] already = "he_einav" — kept as-is
```
Note: the existing `for key, value in updates.items(): if key in STATE: STATE[key] = value` loop handles writing all three keys to STATE. No separate writes needed.

**tray.py changes:**

1. Add at module level (same as service.py):
```python
HEBREW_VOICE_MAP = {"einav": "female1", "yuval": "male1"}
```

2. Add Hebrew voice setter inside `build_tray_icon()` (alongside `_set_piper_voice`):
```python
def _set_hebrew_voice(voice_id: str, filename: str):
    """Select a Hebrew voice: set model=lightblue, voice_path, voice."""
    def _inner(icon, item):
        onnx_dir = state.get("lightblue_onnx_dir")
        if not onnx_dir:
            return
        state["lightblue_voice_path"] = str(Path(onnx_dir).parent / "voices" / f"{filename}.json")
        state["model"] = "lightblue"
        state["voice"] = voice_id
        _invoke_config_change()
        icon.update_menu()
    return _inner
```

3. Update `_voice_items()` — add Hebrew voices after the `else` branch (Kokoro section), appended when lightblue_onnx_dir is set:
```python
def _voice_items():
    if state.get("model", "kokoro") == "piper":
        # ... existing piper branch unchanged ...
    else:
        # Kokoro voices
        for voice in KOKORO_VOICES:
            yield pystray.MenuItem(
                voice,
                _set_voice(voice),
                checked=lambda item, v=voice: state["voice"] == v,
                radio=True,
            )
        # Hebrew voices (only when lightblue_onnx_dir is configured)
        if state.get("lightblue_onnx_dir"):
            yield pystray.Menu.SEPARATOR
            for name, filename in HEBREW_VOICE_MAP.items():
                voice_id = f"he_{name}"
                display = name.capitalize() + " (Hebrew)"
                yield pystray.MenuItem(
                    display,
                    _set_hebrew_voice(voice_id, filename),
                    checked=lambda item, v=voice_id: state.get("voice") == v,
                    radio=True,
                )
```

**voice.md changes:**

Replace hardcoded voice list with dynamic fetch pattern. Update the skill to:
- Fetch `GET http://localhost:5050/voices` to get all available voices (Kokoro + Hebrew)
- Show voices as a numbered list (Kokoro voices first, then Hebrew if present)
- On Hebrew voice selection: single call `POST /config {"voice": "he_einav"}` — one call handles model+path+voice
- Note that selecting a Hebrew voice automatically sets model=lightblue and configures the voice path
  </action>
  <verify>
    <automated>cd D:/docker/claudetalk && python -c "from agenttalk.service import HEBREW_VOICE_MAP, list_voices; print('HEBREW_VOICE_MAP:', HEBREW_VOICE_MAP); print('list_voices OK')" && python -c "from agenttalk.tray import HEBREW_VOICE_MAP; print('tray HEBREW_VOICE_MAP:', HEBREW_VOICE_MAP)"</automated>
  </verify>
  <done>HEBREW_VOICE_MAP defined in both service.py and tray.py. GET /voices includes he_einav/he_yuval when lightblue_onnx_dir is set. POST /config {"voice": "he_einav"} expands correctly. Tray voice submenu shows Hebrew section when configured. voice.md updated to dynamic fetch.</done>
</task>

<task type="auto">
  <name>Task 2: translator.py — is_hebrew() + translate_to_hebrew() + /speak integration</name>
  <files>agenttalk/translator.py, agenttalk/service.py</files>
  <action>
**Create agenttalk/translator.py** — new file:

```python
"""
translator.py — Hebrew translation fallback for AgentTalk.

Translates English sentences to Hebrew when a Hebrew TTS engine is active
and the input text is not already Hebrew.

Used in service.py /speak handler after preprocess(), before queuing.
Hook-first (user_prompt_hook.py) is preferred — this is the fallback.
"""
import json
import logging
import os
import unicodedata

logger = logging.getLogger(__name__)

# Hebrew Unicode block: U+0590–U+05FF
_HEB_START = 0x0590
_HEB_END = 0x05FF

_SYSTEM_PROMPT = """\
You are a Hebrew translator for a text-to-speech system.
Translate each sentence to Hebrew. Rules:
- Technical terms with no natural Hebrew equivalent: transliterate phonetically
  (gateway→גייטוואי, Docker→דוקר, API→ייפיאיי, endpoint→אנדפוינט,
   branch→ברנץ׳, merge→מרג׳, commit→קומיט, server→שרת)
- Common words with good Hebrew equivalents: translate naturally
  (file→קובץ, directory→תיקייה, error→שגיאה, warning→אזהרה,
   running→רץ, complete→הושלם, failed→נכשל)
- Code, commands, file paths, URLs, variable names: keep in English exactly
- Proper nouns and product names: transliterate
Return a JSON array of Hebrew strings, same length as input, no extra text.\
"""


def is_hebrew(text: str) -> bool:
    """Return True if >40% of alphabetic chars in text are Hebrew (U+0590–U+05FF)."""
    alpha_chars = [c for c in text if unicodedata.category(c).startswith("L")]
    if not alpha_chars:
        return False
    hebrew_count = sum(1 for c in alpha_chars if _HEB_START <= ord(c) <= _HEB_END)
    return (hebrew_count / len(alpha_chars)) > 0.40


def translate_to_hebrew(sentences: list[str], icon=None) -> list[str]:
    """
    Translate a list of sentences to Hebrew using Claude Haiku.

    Sends all sentences in a single API call (JSON array in/out).
    On any failure, logs the error, optionally shows tray notification,
    and returns the original sentences unchanged (fail-open).

    Args:
        sentences: List of English (or mixed) sentences.
        icon: Optional pystray.Icon for tray notification on failure.

    Returns:
        List of Hebrew strings, same length as input.
    """
    if not sentences:
        return sentences

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — Hebrew translation skipped, using original text.")
        return sentences

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user_content = json.dumps(sentences, ensure_ascii=False)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        if not isinstance(result, list) or len(result) != len(sentences):
            raise ValueError(f"Unexpected response shape: expected list[{len(sentences)}], got {type(result).__name__}[{len(result) if isinstance(result, list) else '?'}]")
        return [str(s) for s in result]
    except Exception:
        logger.exception("translate_to_hebrew() failed — returning original sentences.")
        if icon is not None:
            try:
                icon.notify("Hebrew translation failed — using original text.", "AgentTalk")
            except Exception:
                pass
        return sentences
```

**service.py /speak handler integration:**

Add import near top of service.py (after existing agenttalk imports):
```python
from agenttalk.translator import is_hebrew, translate_to_hebrew
```

In the `speak()` handler, after `sentences = preprocess(req.text)` and the `if not sentences` guard, and BEFORE the pre-cue sentinel block, add:
```python
# Hebrew translation fallback: translate English→Hebrew when Hebrew engine is active
if STATE.get("model") in ("lightblue", "hebrewpiper"):
    if sentences and not is_hebrew(req.text):
        sentences = translate_to_hebrew(sentences, icon=_tray_icon)
```

The `_tray_icon` global is already set by `_setup()` before any `/speak` requests arrive.
  </action>
  <verify>
    <automated>cd D:/docker/claudetalk && python -c "from agenttalk.translator import is_hebrew, translate_to_hebrew; assert is_hebrew('שלום עולם') == True; assert is_hebrew('Hello world') == False; print('translator.py OK')"</automated>
  </verify>
  <done>translator.py exists with is_hebrew() and translate_to_hebrew(). is_hebrew('שלום עולם') returns True, is_hebrew('Hello world') returns False. /speak handler calls translate_to_hebrew() when model is lightblue/hebrewpiper and text is not already Hebrew.</done>
</task>

<task type="auto">
  <name>Task 3: user_prompt_hook.py (Claude Code + opencode) + setup.py registration</name>
  <files>agenttalk/hooks/user_prompt_hook.py, integrations/opencode/user_prompt_hook.py, agenttalk/setup.py</files>
  <action>
**Create agenttalk/hooks/user_prompt_hook.py** — Claude Code UserPromptSubmit hook.

Follow the pattern in agenttalk/hooks/stop_hook.py (read that file for exact structure: shebang, reconfigure stdout/stderr to utf-8, read config.json via _config_dir(), exit 0 always).

Key logic:
1. Reconfigure sys.stdout and sys.stderr to utf-8 (required — Windows cp1255 cannot encode Hebrew)
2. Read config.json from _config_dir() — no HTTP round-trip, matches existing hook pattern
3. If config["model"] in ("lightblue", "hebrewpiper"): print the Hebrew instruction to stdout, then exit 0
4. Otherwise: exit 0 silently (no output)

Hebrew instruction to print (exact text, do not alter):
```
ענה בעברית בלבד. הנחיות:
- כתוב את כל ההסברים, התיאורים והתשובות בעברית
- מונחים טכניים ללא תרגום טבעי: תעתוק פונטי (gateway→גייטוואי, Docker→דוקר, API→ייפיאיי, endpoint→אנדפוינט, branch→ברנץ׳, commit→קומיט)
- מילים עם תרגום עברי טבעי: תרגם (file→קובץ, directory→תיקייה, error→שגיאה, server→שרת, running→רץ)
- קוד, פקודות, paths, URLs, שמות משתנים: השאר באנגלית
- הערות בתוך קוד: בעברית
- שמות מוצרים ומותגים: תעתוק פונטי
```

Wrap everything in try/except — if config cannot be read or any error occurs, exit 0 silently (fail-open: Claude works normally, just without Hebrew instruction).

**Create integrations/opencode/user_prompt_hook.py** — opencode version.

Identical logic to the Claude Code version. Read opencode's stop_hook.py (integrations/opencode/stop_hook.py) for the exact config path pattern used by opencode hooks (it may use a different config location than _config_dir()). Match that pattern exactly.

**Update agenttalk/setup.py:**

Read the existing setup.py to understand how stop_hook and session_start_hook are registered for Claude Code and opencode. Add user_prompt_hook registration using the same pattern:
- For Claude Code: register user_prompt_hook.py under the "UserPromptSubmit" hook type in .claude/settings.json (or wherever stop_hook is registered)
- For opencode: register integrations/opencode/user_prompt_hook.py in the opencode settings (matching how opencode stop_hook is registered)

The hook script path must be absolute (use Path(__file__).parent for the hooks dir).
  </action>
  <verify>
    <automated>cd D:/docker/claudetalk && python -c "
import sys, pathlib
sys.stdout.reconfigure(encoding='utf-8')
hook = pathlib.Path('agenttalk/hooks/user_prompt_hook.py')
opencode_hook = pathlib.Path('integrations/opencode/user_prompt_hook.py')
assert hook.exists(), f'Missing: {hook}'
assert opencode_hook.exists(), f'Missing: {opencode_hook}'
content = hook.read_text(encoding='utf-8')
assert 'UserPromptSubmit' in content or 'lightblue' in content, 'Hook missing Hebrew model check'
assert 'ענה בעברית' in content, 'Hook missing Hebrew instruction'
print('user_prompt_hook.py OK')
print('opencode user_prompt_hook.py OK')
"</automated>
  </verify>
  <done>agenttalk/hooks/user_prompt_hook.py exists with Hebrew instruction output when model is lightblue/hebrewpiper. integrations/opencode/user_prompt_hook.py exists with same logic. setup.py registers both under UserPromptSubmit hook type. All files use utf-8 stdout reconfiguration.</done>
</task>

</tasks>

<verification>
1. `python -c "from agenttalk.service import HEBREW_VOICE_MAP; print(HEBREW_VOICE_MAP)"` prints `{'einav': 'female1', 'yuval': 'male1'}`
2. `python -c "from agenttalk.translator import is_hebrew; print(is_hebrew('שלום'))"` prints `True`
3. `python -c "from agenttalk.translator import is_hebrew; print(is_hebrew('hello'))"` prints `False`
4. `python -c "from agenttalk.hooks.user_prompt_hook import *"` imports without error (or script exits 0)
5. Both hook files contain the Hebrew instruction text `ענה בעברית בלבד`
</verification>

<success_criteria>
- HEBREW_VOICE_MAP defined in service.py and tray.py with einav/yuval entries
- GET /voices returns he_einav, he_yuval when lightblue_onnx_dir is set in STATE
- POST /config {"voice": "he_einav"} auto-sets model=lightblue, lightblue_voice_path, voice=he_einav
- POST /config {"voice": "he_einav"} returns 400 when lightblue_onnx_dir is not configured
- Tray Voice submenu shows Einav (Hebrew) / Yuval (Hebrew) items after Kokoro voices when lightblue_onnx_dir is set
- translator.py: is_hebrew() correctly classifies Hebrew vs English text (>40% Hebrew alpha chars threshold)
- translator.py: translate_to_hebrew() calls claude-haiku-4-5-20251001 with JSON array, returns same-length Hebrew array
- translator.py: on any failure returns original sentences unchanged (fail-open)
- /speak handler calls translate_to_hebrew() when model in (lightblue, hebrewpiper) and text is not Hebrew
- user_prompt_hook.py injects Hebrew instruction to stdout when model is lightblue/hebrewpiper
- setup.py registers user_prompt_hook.py for Claude Code and opencode
- voice.md updated to fetch GET /voices dynamically
</success_criteria>

<output>
After completion, create `.planning/quick/9-hebrew-voices-integration-unified-namesp/9-SUMMARY.md`
</output>

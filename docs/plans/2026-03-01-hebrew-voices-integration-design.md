# Hebrew Voices Integration Design

**Date:** 2026-03-01
**Status:** Approved
**Scope:** Integrate LightBlueTTS voices into the unified AgentTalk voice lineup with automatic Hebrew translation

---

## Goal

Hebrew TTS voices appear naturally in the same voice picker as English voices. Selecting one auto-switches the engine and voice in a single step. The LLM output is natively Hebrew when a Hebrew voice is active, with translator.py as a fallback for non-hooked clients.

---

## Decisions

- **Engine:** LightBlueTTS only in the voice lineup (local ONNX, always available). HebrewPiper (PiperStream) remains accessible via raw API only — removed from voice picker to avoid startup friction.
- **Translation strategy:** Hook-first (prompt injection before LLM generates), translator.py fallback (post-hoc Haiku translation when text arrives in English).
- **Translation service:** Claude Haiku (`claude-haiku-4-5-20251001`).
- **Voice naming:** Human Hebrew names, not file stems (`he_einav` not `he_female1`).

---

## Voice Namespace

Two voices initially. Mapping lives in `HEBREW_VOICE_MAP` dict:

| Voice ID | File | Display |
|----------|------|---------|
| `he_einav` | `female1.json` | Einav (Hebrew) |
| `he_yuval` | `male1.json` | Yuval (Hebrew) |

New voices added by extending the dict. The `he_` prefix is stable — it is the API contract.

### Selecting a Hebrew voice

`POST /config {"voice": "he_einav"}` triggers auto-expansion in the `/config` handler:

1. Detects `he_` prefix
2. Strips prefix → stem (`einav`)
3. Looks up `HEBREW_VOICE_MAP["einav"]` → `"female1"`
4. Derives path: `{lightblue_onnx_dir}/../voices/female1.json`
5. Sets: `STATE["model"] = "lightblue"`, `STATE["lightblue_voice_path"] = <path>`, `STATE["voice"] = "he_einav"`
6. Saves config — persists across restarts

If `lightblue_onnx_dir` is not configured, returns HTTP 400 with actionable error.

### GET /voices

Returns all voices including Hebrew:

```json
{"voices": ["af_heart", "af_bella", ..., "he_einav", "he_yuval"]}
```

Hebrew voices are only included when `lightblue_onnx_dir` is set in STATE. If not configured, only Kokoro voices are returned.

---

## Component 1: Voice Namespace (`service.py`, `tray.py`, `voice.md`)

### service.py

- `HEBREW_VOICE_MAP` dict defined at module level (shared with tray.py via import or duplicated)
- `GET /voices`: scans map + checks `lightblue_onnx_dir` is set → returns Kokoro voices + Hebrew voices
- `POST /config`: when `voice` starts with `he_`, auto-expand before writing to STATE

### tray.py

- `HEBREW_VOICE_MAP` dict (same as service.py, or imported)
- `_voice_items()` updated: Kokoro voices as before, then if `lightblue_onnx_dir` is set, separator + Hebrew voice items
- Each Hebrew voice item: clicking sets `state["model"] = "lightblue"`, `state["lightblue_voice_path"]`, `state["voice"]`
- "Active:" label: already handles lightblue correctly (shows `STATE["voice"]` = `"he_einav"`)

### voice.md skill

- Fetches `GET /voices` dynamically (replaces hardcoded Kokoro list)
- Shows all voices in one numbered list: Kokoro voices then Hebrew voices (visually grouped)
- On Hebrew selection: single `POST /config {"voice": "he_einav"}` — one call handles everything

---

## Component 2: `agenttalk/translator.py`

Fallback translation for non-hooked clients (raw `/speak` calls, opencode without hook, etc.).

### Functions

**`is_hebrew(text: str) -> bool`**
Count Hebrew Unicode chars (U+0590–U+05FF). Return True if >40% of alphabetic chars are Hebrew. Fast, no external calls.

**`translate_to_hebrew(sentences: list[str]) -> list[str]`**
One Haiku API call. Sends sentences as JSON array. Returns Hebrew sentences maintaining 1:1 count.

System prompt:
```
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
Return a JSON array of Hebrew strings, same length as input, no extra text.
```

Temperature: 0. Model: `claude-haiku-4-5-20251001`. API key from `ANTHROPIC_API_KEY` env var.

**Fallback behavior:** On any failure (no API key, rate limit, network error) — log the error, send tray notification if icon is available, return original sentences unchanged.

### Integration in `/speak` handler (`service.py`)

After `preprocess()` returns English sentences, before queuing:

```python
if STATE.get("model") in ("lightblue", "hebrewpiper"):
    if not is_hebrew(req.text):
        sentences = translate_to_hebrew(sentences)
```

`tts_worker.py` is unchanged — it receives Hebrew sentences and synthesizes them.

---

## Component 3: `agenttalk/hooks/user_prompt_hook.py`

UserPromptSubmit hook. Fires before Claude generates a response. Injects Hebrew instruction into context so the LLM output is natively Hebrew — making the translator.py path a true fallback.

### Logic

1. Read local `config.json` (no HTTP round-trip — matches existing hook pattern)
2. Check `model` field
3. If `model` in `("lightblue", "hebrewpiper")`: output Hebrew instruction to stdout
4. Claude Code injects stdout as system context before generating response
5. Exit 0

### Hebrew instruction output

```
ענה בעברית בלבד. הנחיות:
- כתוב את כל ההסברים, התיאורים והתשובות בעברית
- מונחים טכניים ללא תרגום טבעי: תעתוק פונטי (gateway→גייטוואי, Docker→דוקר, API→ייפיאיי, endpoint→אנדפוינט, branch→ברנץ׳, commit→קומיט)
- מילים עם תרגום עברי טבעי: תרגם (file→קובץ, directory→תיקייה, error→שגיאה, server→שרת, running→רץ)
- קוד, פקודות, paths, URLs, שמות משתנים: השאר באנגלית
- הערות בתוך קוד: בעברית
- שמות מוצרים ומותגים: תעתוק פונטי
```

### Files

- `agenttalk/hooks/user_prompt_hook.py` — Claude Code version
- `integrations/opencode/user_prompt_hook.py` — opencode version (same logic, registered in opencode settings)
- VSCode / Antigravity / OpenClaw: instruction-based — update their skill/system-prompt docs with a static Hebrew mode block

### Registration

`agenttalk setup` registers the hook in the appropriate settings file for each integration, matching how `stop_hook` and `session_start_hook` are currently registered.

---

## What does NOT change

- `tts_worker.py` — synthesis loop unchanged; receives Hebrew text, synthesizes it
- `hebrewpiper_engine.py`, `lightblue_engine.py` — engine wrappers unchanged
- `piper_engine.py`, Kokoro — English path unchanged
- `config_loader.py` — no schema changes needed
- Existing hooks (`stop_hook`, `session_start_hook`, `post_tool_use_hook`) — unchanged

---

## File change summary

| File | Change |
|------|--------|
| `agenttalk/service.py` | `GET /voices` + `POST /config` Hebrew voice expansion |
| `agenttalk/tray.py` | `_voice_items()` + `HEBREW_VOICE_MAP` |
| `agenttalk/translator.py` | New file — `is_hebrew()` + `translate_to_hebrew()` |
| `agenttalk/commands/voice.md` | Dynamic `/voices` fetch, Hebrew voice support |
| `agenttalk/hooks/user_prompt_hook.py` | New file — UserPromptSubmit hook |
| `integrations/opencode/user_prompt_hook.py` | New file — opencode version |
| `agenttalk/setup.py` | Register user_prompt_hook for Claude Code + opencode |

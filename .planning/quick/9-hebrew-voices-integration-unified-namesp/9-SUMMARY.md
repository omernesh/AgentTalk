---
phase: quick-9
plan: 9
subsystem: hebrew-voices-integration
tags: [hebrew, tts, lightblue, voice-namespace, translation, hooks]
dependency_graph:
  requires: [quick-8]
  provides: [unified-voice-namespace, hebrew-translation, user-prompt-hook]
  affects: [service.py, tray.py, translator.py, hooks, setup.py]
tech_stack:
  added: [anthropic (claude-haiku-4-5-20251001 for translation)]
  patterns: [he_ voice prefix, HEBREW_VOICE_MAP dict, fail-open translation, hook-first strategy]
key_files:
  created:
    - agenttalk/translator.py
    - agenttalk/hooks/user_prompt_hook.py
    - integrations/opencode/user_prompt_hook.py
  modified:
    - agenttalk/service.py
    - agenttalk/tray.py
    - agenttalk/commands/voice.md
    - agenttalk/setup.py
decisions:
  - "HEBREW_VOICE_MAP duplicated in service.py and tray.py (not imported) — avoids circular import between service and tray"
  - "Claude Code hook reads local config.json (no HTTP); opencode hook uses HTTP GET /config — matches each integration's existing stop_hook pattern"
  - "UserPromptSubmit registered as async: false so instruction is injected synchronously before Claude generates"
  - "translate_to_hebrew fail-open: returns original sentences on any error — audio still plays even if translation fails"
metrics:
  duration: "~12 min"
  completed: "2026-03-01"
  tasks: 3
  files_changed: 7
---

# Quick Task 9: Hebrew Voices Integration — Unified Namespace Summary

**One-liner:** Hebrew TTS voices (he_einav, he_yuval) integrated into the unified voice namespace with auto-engine-switching via he_ prefix, Claude Haiku translation fallback, and UserPromptSubmit hook for native Hebrew LLM output.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Voice namespace — service.py + tray.py + voice.md | f06a682 | service.py, tray.py, voice.md |
| 2 | translator.py + /speak integration | 4577d07 | translator.py, service.py |
| 3 | user_prompt_hook.py (Claude Code + opencode) + setup.py | e590407 | user_prompt_hook.py (x2), setup.py |

## What Was Built

### Task 1: Voice Namespace

`HEBREW_VOICE_MAP = {"einav": "female1", "yuval": "male1"}` defined in both `service.py` and `tray.py`.

`GET /voices` now returns Kokoro voices + Hebrew voices when `lightblue_onnx_dir` is configured:
```json
{"voices": ["af_heart", ..., "he_einav", "he_yuval"]}
```

`POST /config {"voice": "he_einav"}` auto-expands in a single call:
1. Detects `he_` prefix, strips to stem (`einav`)
2. Looks up `HEBREW_VOICE_MAP["einav"]` → `"female1"`
3. Derives path: `{lightblue_onnx_dir}/../voices/female1.json`
4. Sets `model=lightblue`, `lightblue_voice_path=<path>`, `voice=he_einav`
5. Returns 400 with actionable error if `lightblue_onnx_dir` not configured

Tray Voice submenu appends `Einav (Hebrew)` / `Yuval (Hebrew)` items after Kokoro voices when `lightblue_onnx_dir` is set.

`voice.md` updated to fetch `GET /voices` dynamically instead of hardcoded list.

### Task 2: translator.py

New `agenttalk/translator.py`:
- `is_hebrew(text)` — counts Hebrew Unicode chars (U+0590–U+05FF), returns True if >40% of alphabetic chars are Hebrew
- `translate_to_hebrew(sentences, icon)` — single Haiku API call (JSON array in/out), fail-open on any failure

`/speak` handler integration: after `preprocess()`, before queuing — translates when model is `lightblue`/`hebrewpiper` and text is not already Hebrew.

### Task 3: user_prompt_hook.py

`agenttalk/hooks/user_prompt_hook.py` (Claude Code):
- Reads `config.json` locally (no HTTP — matches stop_hook.py pattern)
- Prints Hebrew instruction to stdout when model is `lightblue`/`hebrewpiper`
- `sys.stdout.reconfigure(encoding='utf-8')` at top — Windows cp1255 cannot encode Hebrew
- Fail-open: exits 0 silently on any error

`integrations/opencode/user_prompt_hook.py` (opencode):
- Uses HTTP GET /config (matches opencode stop_hook.py pattern)
- Same Hebrew instruction, same utf-8 reconfiguration, same fail-open

`setup.py`: registers `user_prompt_hook.py` under `UserPromptSubmit` hook type in `~/.claude/settings.json`.

## Verification Results

```
HEBREW_VOICE_MAP: {'einav': 'female1', 'yuval': 'male1'}  ✓
is_hebrew('שלום עולם') == True                             ✓
is_hebrew('Hello world') == False                          ✓
translator.py OK                                           ✓
user_prompt_hook.py OK                                     ✓
opencode user_prompt_hook.py OK                            ✓
```

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `agenttalk/translator.py` — FOUND
- `agenttalk/hooks/user_prompt_hook.py` — FOUND
- `integrations/opencode/user_prompt_hook.py` — FOUND
- Commit f06a682 — FOUND
- Commit 4577d07 — FOUND
- Commit e590407 — FOUND

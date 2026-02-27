---
phase: quick
plan: 5
subsystem: preprocessor / test coverage
tags: [audit, tts, emotional-punctuation, regression-tests, docstring]
dependency_graph:
  requires: []
  provides: [emotional-punctuation regression suite, strip_markdown preservation contract]
  affects: [agenttalk/preprocessor.py, tests/test_preprocessor.py]
tech_stack:
  added: []
  patterns: [parametrized pytest, docstring contracts]
key_files:
  created: []
  modified:
    - tests/test_preprocessor.py
    - agenttalk/preprocessor.py
decisions:
  - "Audit finding: strip_markdown() never stripped emotional punctuation — no code logic change needed"
  - "10 parametrized cases + 1 mixed integration test lock down all 9 character classes"
metrics:
  duration: "~2 min"
  completed_date: "2026-02-28"
  tasks_completed: 2
  files_modified: 2
---

# Quick Task 5: Audit Text Filter — Emotional Punctuation Preservation Summary

**One-liner:** Confirmed strip_markdown() never strips em-dash/ellipsis/curly-quotes/!/? — locked down with 11 regression tests and an explicit preservation contract docstring.

## Audit Finding

`text_filter.py` does not exist. Text cleaning lives in `agenttalk/preprocessor.py` in the `strip_markdown()` function. Pre-plan investigation confirmed that none of the 8 regex substitutions target emotional/prosody punctuation. All 9 character classes pass through unchanged.

**Result: NO FIX REQUIRED.** Only regression tests and a docstring were added.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add emotional-punctuation regression tests | 401b888 | tests/test_preprocessor.py |
| 2 | Add preservation contract docstring to strip_markdown() | f67937d | agenttalk/preprocessor.py |

## Changes Made

### tests/test_preprocessor.py

Added two new test functions after the last existing test:

1. `test_strip_markdown_preserves_emotional_punctuation` — parametrized over 10 cases:
   - em-dash (—/\u2014)
   - Unicode ellipsis (…/\u2026)
   - Exclamation mark (!)
   - Question mark (?)
   - Curly open double-quote (\u201c)
   - Curly close double-quote (\u201d)
   - Curly open single-quote (\u2018)
   - Curly close single-quote (\u2019)
   - ASCII double-dash (--)
   - ASCII ellipsis (...)

2. `test_strip_markdown_preserves_mixed_emotional` — integration test with a sentence combining em-dash, curly apostrophe, !, open/close curly quotes, Unicode ellipsis, and ?.

### agenttalk/preprocessor.py

Added `Preserved (pass through unchanged):` section to `strip_markdown()` docstring. Lists all 7 emotional/prosody character classes with Unicode code points and explains why Kokoro needs them. No code logic changed.

## Verification

```
python -m pytest tests/test_preprocessor.py -v
# 36 passed in 0.30s
```

## Deviations from Plan

None — plan executed exactly as written.

---
phase: quick-7
plan: 7
subsystem: preprocessor
tags: [tdd, sentence-detection, paragraph-breaks, pysbd, strip-markdown]
dependency_graph:
  requires: []
  provides: [paragraph-aware-sentence-splitting]
  affects: [agenttalk/preprocessor.py, TTS sentence streaming]
tech_stack:
  added: []
  patterns: [regex paragraph injection, TDD red-green cycle]
key_files:
  created: []
  modified:
    - agenttalk/preprocessor.py
    - tests/test_preprocessor.py
decisions:
  - "Inject '. ' at paragraph breaks via regex step 9a before whitespace collapse so pysbd receives clean sentence boundaries"
  - "Regex ([^.!?:;,\\n])\\n{2,} guards against double-punctuation and newline-preceded breaks"
metrics:
  duration: 8 min
  completed: 2026-02-28
  tasks_completed: 1
  files_modified: 2
---

# Phase quick-7 Plan 7: Paragraph-Break Sentence Injection Summary

**One-liner:** Step 9a regex injects `. ` at double-newline paragraph breaks before whitespace collapse so pysbd correctly splits Claude's paragraph-separated output into individual TTS sentences.

## What Was Built

The root cause was that `strip_markdown()` step 9 collapsed all whitespace (including `\n\n`) to a single space before pysbd could use paragraph boundaries as sentence breaks. "Idea A\n\nIdea B" became "Idea A Idea B" — one unsplittable run-on.

**Fix:** A new step 9a inserted between list-bullet stripping (step 8) and whitespace normalization (step 9):

```python
# 9a. Paragraph breaks — inject sentence boundary before double-newlines
#     when the preceding character is not already terminal punctuation.
text = re.sub(r"([^.!?:;,\n])\n{2,}", r"\1. ", text)
```

The regex `([^.!?:;,\n])\n{2,}`:
- Matches any char that is NOT terminal punctuation and NOT a newline, followed by 2+ newlines
- Replaces with the matched char + `. ` — a clean sentence boundary for pysbd
- Guards against double punctuation (e.g. "Done.\n\nNext." stays "Done. Next." not "Done.. Next.")

The docstring was updated to document step 9a.

## Tests

5 new tests added to `tests/test_preprocessor.py`:

| Test | Description | Result |
|------|-------------|--------|
| `para_no_punct_injects_period` | `"Idea A\n\nIdea B"` -> `"Idea A. Idea B"` | Pass |
| `para_with_punct_no_double_period` | `"Done.\n\nNext step."` -> `"Done. Next step."` | Pass |
| `three_paras_no_punct` | `"First\n\nSecond\n\nThird"` -> `"First. Second. Third"` | Pass |
| `single_newline_becomes_space` | `"Line one\nLine two"` -> `"Line one Line two"` | Pass |
| `test_preprocess_paragraph_separated_yields_multiple_sentences` | 3 paragraphs -> 3 sentences | Pass |

**Total: 41 tests pass** (36 original + 5 new). The plan anticipated 42 (counting slightly differently) but all intended behaviors are covered.

## Verification

Manual smoke test (4-paragraph input yields 4 sentences):
```
Sentences: 4
  1: 'I found three issues in the code. '
  2: 'The first issue is in the auth module. '
  3: 'The second issue is in the database layer. '
  4: 'The third issue affects performance'
```

## Deviations from Plan

None - plan executed exactly as written.

Note: `tests/test_hooks.py` has 2 pre-existing failures unrelated to this task (confirmed by reverting changes and re-running — failures existed before). Not in scope.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 - TDD: paragraph-break injection | a7dc694 | feat(quick-7): inject sentence boundary at paragraph breaks in strip_markdown |

## Self-Check: PASSED

- `agenttalk/preprocessor.py` exists with step 9a: FOUND
- `tests/test_preprocessor.py` has new paragraph tests: FOUND
- Commit a7dc694 exists: FOUND
- 41 tests pass: VERIFIED

---
task_number: 5
slug: audit-text-filter-emotional-punctuation
description: >
  Audit preprocessor.py (the text cleaning module — text_filter.py does not
  exist) to verify emotionally-relevant punctuation is preserved before
  text reaches Kokoro TTS. Add regression tests for each character class.
date: 2026-02-28
status: pending
files_modified:
  - agenttalk/preprocessor.py
  - tests/test_preprocessor.py
---

<objective>
Confirm and lock down that Kokoro's prosody engine receives the emotional
punctuation Claude naturally writes: em-dash (—), ellipsis (…), exclamation (!),
question (?), curly quotes (" " ' '), ASCII double-dash (--), ASCII ellipsis (...).

Purpose: Kokoro reads punctuation as prosody cues. If strip_markdown silently
stripped these, speech would lose natural pacing, emphasis, and intonation.

Audit finding (pre-plan):
  - text_filter.py does not exist. Text cleaning lives in agenttalk/preprocessor.py,
    specifically the strip_markdown() function.
  - strip_markdown() runs 8 regex substitutions. None of them strip emotional
    punctuation. Confirmed by running all 9 character classes through the pipeline.
  - The six regexes are: fenced code blocks, inline code, markdown links, bare URLs,
    ATX headers, bold/italic markers (*/_), blockquotes, list bullets, whitespace norm.
    None target —, …, !, ?, curly quotes, or ASCII equivalents.
  - Result: NO FIX REQUIRED. All target characters pass through unchanged.

Output: Regression test suite covering all emotional punctuation, plus a doc
comment on strip_markdown() naming the preserved characters explicitly.
</objective>

<context>
@.planning/STATE.md
@agenttalk/preprocessor.py
@tests/test_preprocessor.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add emotional-punctuation regression tests to test_preprocessor.py</name>
  <files>tests/test_preprocessor.py</files>
  <action>
    Append a new parametrized test group to tests/test_preprocessor.py. Do NOT
    modify existing tests. Add these two test functions after the last existing test:

    1. test_strip_markdown_preserves_emotional_punctuation — parametrized over all
       9 character classes below. For each: assert the character survives strip_markdown.

       Cases (label, input, char_that_must_survive):
         - ("em_dash",          "It was great\u2014really.",        "\u2014")
         - ("ellipsis_char",    "Well\u2026 I suppose so.",          "\u2026")
         - ("exclamation",      "That is amazing!",                  "!")
         - ("question",         "Are you sure?",                     "?")
         - ("curly_open_dbl",   "\u201cHello there\u201d",           "\u201c")
         - ("curly_close_dbl",  "\u201cHello there\u201d",           "\u201d")
         - ("curly_open_sgl",   "\u2018right\u2019",                 "\u2018")
         - ("curly_close_sgl",  "\u2018right\u2019",                 "\u2019")
         - ("double_dash",      "It was great--really.",             "--")
         - ("ascii_ellipsis",   "Well... I suppose so.",             "...")

       Use ids=... in parametrize to name cases by label. Assert with:
         result = strip_markdown(input_text)
         assert char in result, f"strip_markdown stripped {char!r} from {input_text!r} → {result!r}"

    2. test_strip_markdown_preserves_mixed_emotional — single integration test:
       input = "Wow\u2014that\u2019s amazing! \u201cReally\u2026\u201d she asked?"
       result = strip_markdown(input)
       assert all char in result for char in ["\u2014", "\u2019", "!", "\u201c",
                                              "\u2026", "\u201d", "?"]
       assert "Wow" in result
       assert "amazing" in result
  </action>
  <verify>cd /d/docker/claudetalk && python -m pytest tests/test_preprocessor.py -v -k "emotional" 2>&1 | tail -20</verify>
  <done>All 11 new test cases pass (10 parametrized + 1 mixed). No existing tests broken.</done>
</task>

<task type="auto">
  <name>Task 2: Add preservation contract comment to strip_markdown()</name>
  <files>agenttalk/preprocessor.py</files>
  <action>
    Update the docstring of strip_markdown() to explicitly document which
    characters are intentionally preserved. Insert the following lines into the
    docstring, immediately after the first paragraph (after "whitespace normalized."):

    ```
    Preserved (pass through unchanged):
        Emotional/prosody punctuation — em-dash (—/\u2014), ellipsis (…/\u2026),
        curly quotes (\u201c \u201d \u2018 \u2019), exclamation (!), question (?),
        ASCII double-dash (--), ASCII ellipsis (...).
        Kokoro's prosody engine uses these for pacing and intonation; stripping
        them would flatten speech expressiveness.
    ```

    Do NOT change any code logic. Docstring edit only.
  </action>
  <verify>cd /d/docker/claudetalk && python -c "from agenttalk.preprocessor import strip_markdown; help(strip_markdown)" | grep -i "preserved"</verify>
  <done>Running help(strip_markdown) prints a line containing "Preserved". All existing tests still pass: python -m pytest tests/test_preprocessor.py -q</done>
</task>

</tasks>

<verification>
Full test suite must remain green:
  cd /d/docker/claudetalk && python -m pytest tests/test_preprocessor.py -v

Expected: all original tests pass + 11 new emotional-punctuation tests pass.
Zero tests should fail or error.
</verification>

<success_criteria>
- Regression tests for all 9 emotional punctuation character classes exist in
  tests/test_preprocessor.py and pass.
- strip_markdown() docstring explicitly names the preserved characters.
- No code logic in preprocessor.py is changed (characters were already preserved).
- python -m pytest tests/test_preprocessor.py exits 0.
</success_criteria>

<output>
After completion, create .planning/quick/5-audit-text-filter-py-to-check-if-emotion/5-SUMMARY.md
with: audit finding (no stripping found), files changed, tests added, commit hash.
</output>

---
phase: quick-7
plan: 7
type: tdd
wave: 1
depends_on: []
files_modified:
  - agenttalk/preprocessor.py
  - tests/test_preprocessor.py
autonomous: true
requirements: [AUDIO-02, AUDIO-03]

must_haves:
  truths:
    - "Paragraphs separated by double-newlines produce separate TTS sentences"
    - "Lines already ending in terminal punctuation are not double-punctuated"
    - "Single newlines within a paragraph become spaces (unchanged behavior)"
    - "All 36 existing preprocessor tests continue to pass"
  artifacts:
    - path: "agenttalk/preprocessor.py"
      provides: "Paragraph-break injection in strip_markdown before whitespace collapse"
      contains: "paragraph break"
    - path: "tests/test_preprocessor.py"
      provides: "Regression + new paragraph-split tests"
  key_links:
    - from: "agenttalk/preprocessor.py strip_markdown()"
      to: "agenttalk/preprocessor.py segment_sentences()"
      via: "preprocess() pipeline"
      pattern: "segment_sentences(strip_markdown"
---

<objective>
Fix AgentTalk sentence detection so it pauses between sentences separated by paragraph breaks (double newlines), not just when pysbd finds terminal punctuation.

Purpose: Claude responses frequently separate ideas with paragraph breaks (\n\n) rather than always ending every line with a period. The current strip_markdown() step 9 collapses all whitespace to a single space before pysbd sees the text, so "Idea A\n\nIdea B" becomes "Idea A Idea B" — one unsplittable run-on.

Root cause: step 9 in strip_markdown — `re.sub(r"\s+", " ", text).strip()` — collapses \n\n to " " before pysbd can use paragraph boundaries as sentence breaks.

Fix: Insert a new step 9a (before step 9) that injects a period+space at each multi-newline boundary when the preceding character is not already terminal punctuation (`.!?:;,`). This gives pysbd clean sentence boundaries to split on.

Output: Updated preprocessor.py + new regression tests.
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md

@agenttalk/preprocessor.py
@tests/test_preprocessor.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add paragraph-break injection to strip_markdown + regression tests</name>
  <files>agenttalk/preprocessor.py, tests/test_preprocessor.py</files>

  <behavior>
    TDD: Write failing tests first, then implement.

    New test cases to add to tests/test_preprocessor.py (all under test_strip_markdown parametrize or as standalone):

    1. Paragraph break without terminal punct becomes period:
       strip_markdown("Idea A\n\nIdea B") == "Idea A. Idea B"

    2. Paragraph break already has terminal punct — no double punctuation:
       strip_markdown("Done.\n\nNext step.") == "Done. Next step."

    3. Three paragraphs without terminal punct:
       strip_markdown("First\n\nSecond\n\nThird") == "First. Second. Third"

    4. Single newline stays as space (existing behavior unchanged):
       strip_markdown("Line one\nLine two") == "Line one Line two"

    5. preprocess() integration: paragraph-separated text yields multiple sentences:
       result = preprocess("Here is what I found\n\nThe file contains three items\n\nEach item is valid")
       assert len(result) == 3

    After RED (tests fail), implement in preprocessor.py:
    - Add step 9a before the current step 9 whitespace normalization:
      `text = re.sub(r'([^.!?:;,\n])\n{2,}', r'\1. ', text)`
      This injects '. ' at paragraph breaks only when the preceding char is not
      already terminal punctuation or itself a newline.
    - Keep step 9 unchanged: `text = re.sub(r"\s+", " ", text).strip()`
    - Update the docstring to document the new step 9a.

    The regex `([^.!?:;,\n])\n{2,}` explanation:
    - `[^.!?:;,\n]` — any char that is NOT terminal punctuation and NOT a newline
    - `\n{2,}` — two or more consecutive newlines (paragraph break)
    - Replace with `\1. ` — keep the matched char, add `. ` as sentence boundary
  </behavior>

  <action>
    RED phase: Add the 5 new test cases (as parametrize entries + one standalone
    integration test) to tests/test_preprocessor.py. Run pytest — these tests MUST
    fail before any implementation change. Confirm failure.

    GREEN phase: In agenttalk/preprocessor.py, insert after step 8 (list bullets)
    and before step 9 (whitespace normalization):

    ```python
    # 9a. Paragraph breaks — inject sentence boundary before double-newlines
    #     when the preceding character is not already terminal punctuation.
    #     "Idea A\n\nIdea B" -> "Idea A. Idea B" so pysbd splits correctly.
    #     Must run BEFORE step 9 (whitespace collapse) so \n\n is still visible.
    text = re.sub(r"([^.!?:;,\n])\n{2,}", r"\1. ", text)
    ```

    Run pytest. All 36 original tests + 6 new tests = 42 total MUST pass.

    Do NOT change segment_sentences() or preprocess() — the fix is entirely
    in strip_markdown() step ordering.
  </action>

  <verify>
    <automated>cd D:/docker/claudetalk && python -m pytest tests/test_preprocessor.py -v 2>&1 | tail -10</automated>
  </verify>

  <done>
    All tests pass (36 original + 6 new = 42 total).
    strip_markdown("Here is what I found\n\nThe answer is yes") returns
    "Here is what I found. The answer is yes" (injectable period present).
    strip_markdown("Done.\n\nNext.") returns "Done. Next." (no double period).
  </done>
</task>

</tasks>

<verification>
Run full test suite to confirm no regressions:
cd D:/docker/claudetalk && python -m pytest tests/ -v 2>&1 | tail -20

Manual smoke test — paste multi-paragraph text directly:
cd D:/docker/claudetalk && python -c "
from agenttalk.preprocessor import preprocess
text = '''I found three issues in the code

The first issue is in the auth module

The second issue is in the database layer

The third issue affects performance'''
result = preprocess(text)
print(f'Sentences: {len(result)}')
for i, s in enumerate(result): print(f'  {i+1}: {s!r}')
"
Expected output: 4 separate sentences (one per paragraph).
</verification>

<success_criteria>
- strip_markdown injects ". " at double-newline boundaries when not already terminal-punctuated
- preprocess() returns one sentence per paragraph for paragraph-separated Claude output
- All 42 tests pass (36 original + 6 new)
- No changes to segment_sentences(), is_speakable(), or preprocess() signatures
</success_criteria>

<output>
After completion, create .planning/quick/7-fix-agenttalk-sentence-detection-so-it-p/7-SUMMARY.md
</output>

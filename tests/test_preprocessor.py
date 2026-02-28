"""
Tests for agenttalk.preprocessor module.
TDD RED phase: these tests are written before the implementation exists.
Plan: 02-01 — Text Preprocessing Pipeline
"""

import pytest


# ---------------------------------------------------------------------------
# strip_markdown tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_text, expected", [
    # Fenced code block — replaced with space then normalized/stripped to ""
    ("```python\ncode\n```", ""),
    # Inline code — unwrapped to plain text (backticks removed, content kept)
    ("Use `foo()` to call", "Use foo() to call"),
    # URL
    ("Visit https://example.com now", "Visit now"),
    # Markdown link — keep text, drop URL (link extraction before bare URL stripping)
    ("[link text](https://example.com)", "link text"),
    # Header
    ("## Section Header", "Section Header"),
    # Bold
    ("**bold text**", "bold text"),
    # Italic
    ("*italic text*", "italic text"),
    # Blockquote
    ("> quoted line", "quoted line"),
    # List bullet (dash)
    ("- list item", "list item"),
    # Whitespace normalization
    ("Hello  world", "Hello world"),
])
def test_strip_markdown(input_text, expected):
    from agenttalk.preprocessor import strip_markdown
    result = strip_markdown(input_text)
    assert result == expected, f"strip_markdown({input_text!r}) = {result!r}, expected {expected!r}"


def test_strip_markdown_fenced_before_inline_order():
    """
    Fenced blocks containing backticks must be removed BEFORE inline code removal.
    This verifies the order-dependent correctness requirement.
    """
    from agenttalk.preprocessor import strip_markdown
    # A fenced block that contains an inline backtick inside it
    text = "Before ```python\nfoo = `bar`\n``` After"
    result = strip_markdown(text)
    # The fenced block (including its inner backtick) should be gone
    assert "`" not in result, f"Backtick survived — fenced block wasn't removed before inline: {result!r}"
    assert "Before" in result
    assert "After" in result


# ---------------------------------------------------------------------------
# is_speakable tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sentence, expected", [
    ("Hello world", True),           # 100% alpha
    ("The quick brown fox.", True),   # >40% alpha
    ("{}", False),                    # 0% alpha
    # NOTE: '{"key": "value"}' has 50% alpha (keyvalue = 8/16 chars) → True
    # A JSON example that genuinely fails the 40% threshold uses short keys:
    ('{"k":1}', False),               # alpha=1/7=14% < 40% → False
    ("1234567890", False),            # 0% alpha
    ("", False),                      # empty string
    ("   ", False),                   # whitespace only
    ("abc!", True),                   # 75% alpha (3/4 chars alphabetic)
])
def test_is_speakable(sentence, expected):
    from agenttalk.preprocessor import is_speakable
    result = is_speakable(sentence)
    assert result == expected, f"is_speakable({sentence!r}) = {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# preprocess tests
# ---------------------------------------------------------------------------

def test_preprocess_clean_markdown_bold():
    """Bold text stripped, sentences split and returned."""
    from agenttalk.preprocessor import preprocess
    result = preprocess("Hello world. **Goodbye**.")
    assert len(result) >= 1
    assert any("Hello world" in s for s in result)
    # "Goodbye" may be its own sentence or merged — just ensure it's present and bold stripped
    combined = " ".join(result)
    assert "Goodbye" in combined
    assert "**" not in combined


def test_preprocess_removes_code_block_keeps_prose():
    """Code block removed; surrounding prose sentences returned."""
    from agenttalk.preprocessor import preprocess
    result = preprocess("Hello.\n```\ncode\n```\nGoodbye.")
    sentences_text = " ".join(result)
    assert "Hello" in sentences_text
    assert "Goodbye" in sentences_text
    assert "code" not in sentences_text
    assert "```" not in sentences_text


def test_preprocess_junk_returns_empty():
    """Pure JSON string with low alpha ratio is filtered — no speakable sentences.

    Uses '{"k":1}' (1/7 = 14% alpha) rather than '{"key":"value"}' (8/16 = 50% alpha).
    The 40% threshold means short-key JSON is filtered; verbose-key JSON may pass since
    the key/value words themselves are English letters.
    """
    from agenttalk.preprocessor import preprocess
    result = preprocess('{"k":1}')
    assert result == [], f"Expected [], got {result!r}"


def test_preprocess_empty_input_returns_empty():
    """Empty input string returns empty list."""
    from agenttalk.preprocessor import preprocess
    result = preprocess("")
    assert result == []


def test_preprocess_url_stripped_sentence_still_speakable():
    """URL is stripped but surrounding prose remains speakable."""
    from agenttalk.preprocessor import preprocess
    result = preprocess("Visit https://example.com for more info.")
    assert len(result) >= 1
    combined = " ".join(result)
    assert "https://" not in combined
    assert "Visit" in combined
    assert "info" in combined


def test_preprocess_returns_list():
    """preprocess always returns a list, never None or a string."""
    from agenttalk.preprocessor import preprocess
    result = preprocess("Hello world.")
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Emotional / prosody punctuation regression tests (quick task 5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label, input_text, char", [
    ("em_dash",         "It was great\u2014really.",       "\u2014"),
    ("ellipsis_char",   "Well\u2026 I suppose so.",         "\u2026"),
    ("exclamation",     "That is amazing!",                 "!"),
    ("question",        "Are you sure?",                    "?"),
    ("curly_open_dbl",  "\u201cHello there\u201d",          "\u201c"),
    ("curly_close_dbl", "\u201cHello there\u201d",          "\u201d"),
    ("curly_open_sgl",  "\u2018right\u2019",                "\u2018"),
    ("curly_close_sgl", "\u2018right\u2019",                "\u2019"),
    ("double_dash",     "It was great--really.",            "--"),
    ("ascii_ellipsis",  "Well... I suppose so.",            "..."),
], ids=lambda x: x if isinstance(x, str) and len(x) < 20 else None)
def test_strip_markdown_preserves_emotional_punctuation(label, input_text, char):
    """Verify that each class of emotional/prosody punctuation survives strip_markdown."""
    from agenttalk.preprocessor import strip_markdown
    result = strip_markdown(input_text)
    assert char in result, (
        f"strip_markdown stripped {char!r} from {input_text!r} \u2192 {result!r}"
    )


def test_strip_markdown_preserves_mixed_emotional():
    """Integration test: a sentence mixing multiple emotional punctuation classes."""
    from agenttalk.preprocessor import strip_markdown
    input_text = "Wow\u2014that\u2019s amazing! \u201cReally\u2026\u201d she asked?"
    result = strip_markdown(input_text)
    for char in ["\u2014", "\u2019", "!", "\u201c", "\u2026", "\u201d", "?"]:
        assert char in result, (
            f"strip_markdown stripped {char!r} from {input_text!r} \u2192 {result!r}"
        )
    assert "Wow" in result
    assert "amazing" in result


# ---------------------------------------------------------------------------
# Paragraph-break injection tests (quick task 7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_text, expected", [
    # 1. Paragraph break without terminal punct gets period injected
    ("Idea A\n\nIdea B", "Idea A. Idea B"),
    # 2. Paragraph break already has terminal punct — no double punctuation
    ("Done.\n\nNext step.", "Done. Next step."),
    # 3. Three paragraphs without terminal punct — two periods injected
    ("First\n\nSecond\n\nThird", "First. Second. Third"),
    # 4. Single newline stays as space (existing behavior unchanged)
    ("Line one\nLine two", "Line one Line two"),
], ids=[
    "para_no_punct_injects_period",
    "para_with_punct_no_double_period",
    "three_paras_no_punct",
    "single_newline_becomes_space",
])
def test_strip_markdown_paragraph_breaks(input_text, expected):
    """Paragraph breaks produce injected sentence boundaries for pysbd."""
    from agenttalk.preprocessor import strip_markdown
    result = strip_markdown(input_text)
    assert result == expected, (
        f"strip_markdown({input_text!r}) = {result!r}, expected {expected!r}"
    )


def test_preprocess_paragraph_separated_yields_multiple_sentences():
    """preprocess() integration: paragraph-separated text yields multiple sentences."""
    from agenttalk.preprocessor import preprocess
    result = preprocess(
        "Here is what I found\n\nThe file contains three items\n\nEach item is valid"
    )
    assert len(result) == 3, (
        f"Expected 3 sentences from 3 paragraphs, got {len(result)}: {result!r}"
    )

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
    # Fenced code block
    ("```python\ncode\n```", " "),
    # Inline code
    ("Use `foo()` to call", "Use  to call"),
    # URL
    ("Visit https://example.com now", "Visit now"),
    # Markdown link — keep text, drop URL
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
    ('{"key": "value"}', False),      # <40% alpha — symbols dominate
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
    """Pure JSON string is filtered — no speakable sentences."""
    from agenttalk.preprocessor import preprocess
    result = preprocess('{"key": "value"}')
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

"""
Text preprocessing pipeline for TTS readiness.

Strips markdown formatting from assistant text, segments into sentences,
and filters out non-speakable content (JSON, symbol strings, code fragments).
This module is the input gate for all TTS audio.

Plan: 02-01 — Text Preprocessing Pipeline (TDD)
Requirements: AUDIO-02, AUDIO-03
"""

import re

import pysbd


def strip_markdown(text: str) -> str:
    """
    Remove markdown formatting from text.

    ORDER IS CRITICAL: fenced code blocks must be stripped BEFORE inline code
    to avoid leaving orphaned backticks from within block interiors.

    Args:
        text: Raw text possibly containing markdown.

    Returns:
        Text with markdown syntax removed and whitespace normalized.

    Preserved (pass through unchanged):
        Emotional/prosody punctuation — em-dash (\u2014/\\u2014), ellipsis (\u2026/\\u2026),
        curly quotes (\\u201c \\u201d \\u2018 \\u2019), exclamation (!), question (?),
        ASCII double-dash (--), ASCII ellipsis (...).
        Kokoro's prosody engine uses these for pacing and intonation; stripping
        them would flatten speech expressiveness.

    Paragraph boundaries:
        This function does NOT handle paragraph breaks. Callers that need
        paragraph-level sentence splitting (e.g. preprocess()) should split
        on double-newlines before calling strip_markdown on each paragraph.
    """
    # 1. Fenced code blocks (MUST come before inline code)
    text = re.sub(r"```[\s\S]*?```", " ", text)

    # 2. Inline code — unwrap to plain text (keep the content, drop the backticks)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)

    # 3. Markdown links — keep link text, drop URL (MUST come before bare URL stripping)
    #    If bare URLs were stripped first, the parenthetical URL in [text](url) would
    #    be partially consumed, breaking the link pattern match.
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 4. Bare URLs (http/https) — after link extraction so [text](url) is handled first
    text = re.sub(r"https?://\S+", "", text)

    # 5. ATX headers (# through ######)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # 6. Bold and italic markers (**text**, *text*, __text__, _text_)
    text = re.sub(r"(\*{1,3}|_{1,3})([^*_\n]+)\1", r"\2", text)

    # 7. Blockquotes
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)

    # 8. List bullets (-, *, +)
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)

    # 9. Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def segment_sentences(text: str) -> list[str]:
    """
    Split text into individual sentences using pysbd.

    Creates a fresh Segmenter per call for thread safety — avoids shared
    mutable state under concurrent FastAPI requests. Cost is negligible
    (pure Python, no model loading).

    Args:
        text: Clean text to segment.

    Returns:
        List of sentence strings. Returns [] for empty input.
    """
    if not text.strip():
        return []
    segmenter = pysbd.Segmenter(language="en", clean=False)
    return segmenter.segment(text)


def is_speakable(sentence: str) -> bool:
    """
    Return True if the sentence has enough alphabetic content to be worth speaking.

    Filters out pure JSON, symbol-heavy strings, numeric output, and other
    non-prose content that would sound like garbage through a TTS engine.

    Threshold: >= 40% of characters must be alphabetic.

    Args:
        sentence: A single sentence string.

    Returns:
        True if the sentence is worth synthesizing, False otherwise.
    """
    cleaned = sentence.strip()
    if not cleaned:
        return False
    alpha_count = sum(c.isalpha() for c in cleaned)
    return alpha_count / len(cleaned) >= 0.40


def preprocess(text: str) -> list[str]:
    """
    Full TTS preprocessing pipeline: split paragraphs → strip markdown → segment → filter.

    Splits on double-newlines first so each paragraph is processed independently
    by pysbd. This guarantees a TTS sentence boundary at every paragraph break
    regardless of pysbd's heuristics (which can silently ignore injected periods
    before labels like "Summary:" or "Note:").

    Each returned sentence is stripped of leading/trailing whitespace so pysbd
    artifacts (e.g. trailing spaces retained from the source text) don't reach
    the TTS engine.

    Args:
        text: Raw assistant output text (may contain markdown).

    Returns:
        List of clean, speakable sentence strings. May be empty if all
        content is noise (JSON, code, symbol strings, etc.).
    """
    paragraphs = re.split(r"\n{2,}", text)
    result = []
    for para in paragraphs:
        cleaned = strip_markdown(para)
        if not cleaned:
            continue
        sentences = segment_sentences(cleaned)
        result.extend(s.strip() for s in sentences if is_speakable(s))
    return result

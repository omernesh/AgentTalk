"""
translator.py — Hebrew translation fallback for AgentTalk.

Translates English sentences to Hebrew when a Hebrew TTS engine is active
and the input text is not already Hebrew.

Used in service.py /speak handler after preprocess(), before queuing.
Hook-first (user_prompt_hook.py) is preferred — this is the fallback.

Translation strategy:
1. anthropic SDK — requires ANTHROPIC_API_KEY in the environment.
2. Fail-open — returns original text unchanged, logs how to enable translation.

Note: Claude Max OAuth tokens (from ~/.claude/.credentials.json) are not accepted
by api.anthropic.com ("OAuth authentication is currently not supported"). The claude
CLI hangs indefinitely in headless environments. Both approaches were investigated and
ruled out. To enable translation, set ANTHROPIC_API_KEY as a Windows system
environment variable (not just terminal) so pythonw.exe can see it.
"""
import json
import logging
import os
import unicodedata

logger = logging.getLogger(__name__)

# Hebrew Unicode block: U+0590–U+05FF
_HEB_START = 0x0590
_HEB_END = 0x05FF

_TRANSLATION_MODEL = "claude-haiku-4-5"

# Single prompt used by both backends — includes instructions + expects JSON array out.
_PROMPT_TEMPLATE = """\
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
Return ONLY a JSON array of Hebrew strings, same length as input, no other text.

Sentences:
{sentences_json}"""


def is_hebrew(text: str) -> bool:
    """Return True if >40% of alphabetic chars in text are Hebrew (U+0590–U+05FF)."""
    total = 0
    hebrew = 0
    for c in text:
        if unicodedata.category(c).startswith("L"):
            total += 1
            if _HEB_START <= ord(c) <= _HEB_END:
                hebrew += 1
    if not total:
        return False
    return (hebrew / total) > 0.40


def _parse_json_array(raw: str, expected_len: int) -> list[str]:
    """Extract and validate a JSON string array from model output."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Find outermost JSON array in case of preamble
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in output: {text[:120]!r}")

    result = json.loads(text[start : end + 1])
    if not isinstance(result, list) or len(result) != expected_len:
        raise ValueError(
            f"Expected list[{expected_len}], "
            f"got {type(result).__name__}[{len(result) if isinstance(result, list) else '?'}]"
        )
    if not all(isinstance(i, str) for i in result):
        raise ValueError("Translation response contains non-string items")
    return result


def _translate_via_sdk(sentences: list[str]) -> list[str]:
    """
    Translate using the anthropic Python SDK.

    Requires ANTHROPIC_API_KEY in the environment.
    Raises RuntimeError/ImportError/ValueError on any failure.
    """
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _PROMPT_TEMPLATE.format(
        sentences_json=json.dumps(sentences, ensure_ascii=False)
    )
    response = client.messages.create(
        model=_TRANSLATION_MODEL,
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    if not response.content:
        raise ValueError("Empty response content from Claude API")
    return _parse_json_array(response.content[0].text, len(sentences))


def translate_to_hebrew(sentences: list[str], icon: "pystray.Icon | None" = None) -> list[str]:
    """
    Translate a list of sentences to Hebrew.

    Requires ANTHROPIC_API_KEY set as a Windows system environment variable.
    On any failure, logs the reason and returns the original sentences unchanged (fail-open).

    Args:
        sentences: List of English (or mixed) sentences.
        icon: Optional pystray.Icon for tray notification on failure.

    Returns:
        List of Hebrew strings (translated), or original sentences if translation unavailable.
    """
    if not sentences:
        return sentences

    # Try anthropic SDK (requires ANTHROPIC_API_KEY as a Windows system env var)
    try:
        result = _translate_via_sdk(sentences)
        logger.debug("translate_to_hebrew: translated %d sentences via anthropic SDK.", len(sentences))
        return result
    except ImportError:
        logger.warning(
            "Hebrew translation unavailable: anthropic package not installed. "
            "Install with: pip install anthropic"
        )
    except RuntimeError as e:
        # ANTHROPIC_API_KEY not set — log once with instructions, then fail-open silently
        logger.warning(
            "Hebrew translation unavailable: %s. "
            "Set ANTHROPIC_API_KEY as a Windows system environment variable "
            "(Control Panel → System → Advanced → Environment Variables) "
            "so pythonw.exe can access it.",
            e,
        )
    except Exception as e:
        logger.warning("Hebrew translation failed: %s — returning original sentences.", e)

    # Fail-open: return original text, optionally notify via tray
    if icon is not None:
        try:
            icon.notify("Hebrew translation unavailable — set ANTHROPIC_API_KEY.", "AgentTalk")
        except Exception:
            logger.debug("icon.notify() failed during translate_to_hebrew.", exc_info=True)
    return sentences

"""
translator.py — Hebrew translation fallback for AgentTalk.

Translates English sentences to Hebrew when a Hebrew TTS engine is active
and the input text is not already Hebrew.

Used in service.py /speak handler after preprocess(), before queuing.
Hook-first (user_prompt_hook.py) is preferred — this is the fallback.
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

_SYSTEM_PROMPT = """\
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
Return a JSON array of Hebrew strings, same length as input, no extra text.\
"""


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


def translate_to_hebrew(sentences: list[str], icon: "pystray.Icon | None" = None) -> list[str]:
    """
    Translate a list of sentences to Hebrew using Claude Haiku.

    Sends all sentences in a single API call (JSON array in/out).
    On any failure, logs the error, optionally shows tray notification,
    and returns the original sentences unchanged (fail-open).

    Args:
        sentences: List of English (or mixed) sentences.
        icon: Optional pystray.Icon for tray notification on failure.

    Returns:
        List of Hebrew strings, same length as input.
    """
    if not sentences:
        return sentences

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — Hebrew translation skipped, using original text.")
        return sentences

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user_content = json.dumps(sentences, ensure_ascii=False)
        response = client.messages.create(
            model=_TRANSLATION_MODEL,
            max_tokens=4096,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        if not response.content:
            raise ValueError("Empty response content from Claude API")
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        if not isinstance(result, list) or len(result) != len(sentences):
            raise ValueError(
                f"Unexpected response shape: expected list[{len(sentences)}], "
                f"got {type(result).__name__}[{len(result) if isinstance(result, list) else '?'}]"
            )
        if not all(isinstance(i, str) for i in result):
            raise ValueError("Translation response contains non-string items")
        return result
    except ImportError:
        logger.error(
            "anthropic package not installed — Hebrew translation skipped. "
            "Install with: pip install anthropic"
        )
        return sentences
    except Exception:
        logger.exception("translate_to_hebrew() failed — returning original sentences.")
        if icon is not None:
            try:
                icon.notify("Hebrew translation failed — using original text.", "AgentTalk")
            except Exception:
                logger.debug(
                    "icon.notify() failed during translate_to_hebrew error handling.", exc_info=True
                )
        return sentences

#!/usr/bin/env python3
"""
AgentTalk UserPromptSubmit hook.
Injects a Hebrew instruction into Claude's context when a Hebrew TTS engine is active.

Requirements: HOOK-HEB-01
Called by Claude Code before every user prompt is processed.
Registered in ~/.claude/settings.json under UserPromptSubmit by agenttalk setup.

When model is 'lightblue' or 'hebrewpiper', prints Hebrew instruction to stdout.
Claude Code injects stdout content as system context before generating a response.
Exit 0 always — fail-open: Claude works normally if anything goes wrong.
"""
import sys
import json
from pathlib import Path

from agenttalk.config_loader import _config_dir

# CRITICAL: Reconfigure stdout/stderr to utf-8 before any output.
# Windows console defaults to cp1255 which cannot encode Hebrew characters.
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

_HEBREW_INSTRUCTION = """\
ענה בעברית בלבד. הנחיות:
- כתוב את כל ההסברים, התיאורים והתשובות בעברית
- מונחים טכניים ללא תרגום טבעי: תעתוק פונטי (gateway→גייטוואי, Docker→דוקר, API→ייפיאיי, endpoint→אנדפוינט, branch→ברנץ׳, commit→קומיט)
- מילים עם תרגום עברי טבעי: תרגם (file→קובץ, directory→תיקייה, error→שגיאה, server→שרת, running→רץ)
- קוד, פקודות, paths, URLs, שמות משתנים: השאר באנגלית
- הערות בתוך קוד: בעברית
- שמות מוצרים ומותגים: תעתוק פונטי"""


def _config_path() -> Path:
    return _config_dir() / 'config.json'


def main() -> None:
    # SYNC: keep in sync with integrations/opencode/user_prompt_hook.py
    try:
        data = json.loads(_config_path().read_text(encoding='utf-8'))
        model = data.get('model', 'kokoro')
        if model in ('lightblue', 'hebrewpiper'):
            print(_HEBREW_INSTRUCTION)
    except Exception as e:
        print(f"AgentTalk user_prompt_hook error: {e}", file=sys.stderr)
    sys.exit(0)


if __name__ == '__main__':
    main()

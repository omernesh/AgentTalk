#!/usr/bin/env python3
"""
AgentTalk opencode UserPromptSubmit hook.
Mirror of agenttalk/hooks/user_prompt_hook.py for opencode.

Injects a Hebrew instruction when a Hebrew TTS engine is active.
Uses HTTP GET /config (matches opencode stop_hook.py pattern — no local file read).

When model is 'lightblue' or 'hebrewpiper', prints Hebrew instruction to stdout.
Exit 0 always — fail-open: opencode works normally if anything goes wrong.
"""
import sys
import json
import urllib.request
import urllib.error

# CRITICAL: Reconfigure stdout/stderr to utf-8 before any output.
# Windows console defaults to cp1255 which cannot encode Hebrew characters.
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

CONFIG_URL = 'http://localhost:5050/config'

_HEBREW_INSTRUCTION = """\
ענה בעברית בלבד. הנחיות:
- כתוב את כל ההסברים, התיאורים והתשובות בעברית
- מונחים טכניים ללא תרגום טבעי: תעתוק פונטי (gateway→גייטוואי, Docker→דוקר, API→ייפיאיי, endpoint→אנדפוינט, branch→ברנץ׳, commit→קומיט)
- מילים עם תרגום עברי טבעי: תרגם (file→קובץ, directory→תיקייה, error→שגיאה, server→שרת, running→רץ)
- קוד, פקודות, paths, URLs, שמות משתנים: השאר באנגלית
- הערות בתוך קוד: בעברית
- שמות מוצרים ומותגים: תעתוק פונטי"""


def main() -> None:
    try:
        req = urllib.request.Request(CONFIG_URL, method='GET')
        with urllib.request.urlopen(req, timeout=2) as resp:
            cfg = json.loads(resp.read().decode('utf-8'))
        model = cfg.get('model', 'kokoro')
        if model in ('lightblue', 'hebrewpiper'):
            print(_HEBREW_INSTRUCTION)
    except urllib.error.URLError:
        pass  # Service not running — fail-open
    except Exception:
        pass  # Any other error — fail-open
    sys.exit(0)


if __name__ == '__main__':
    main()

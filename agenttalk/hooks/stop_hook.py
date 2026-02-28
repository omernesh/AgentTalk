"""
AgentTalk Stop hook.
Reads last_assistant_message from stdin JSON and POSTs to /speak endpoint.

Requirements: HOOK-01, HOOK-03, HOOK-04
Called by Claude Code after every assistant response.
Registered in ~/.claude/settings.json with async: true by agenttalk setup.
"""
import sys
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

SERVICE_URL = 'http://localhost:5050/speak'
TIMEOUT_SECS = 3  # POST completes in <1s; 3s gives headroom without long block

def _config_path() -> Path:
    appdata = os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming'
    return Path(appdata) / 'AgentTalk' / 'config.json'

def _read_speech_mode() -> str:
    """Return speech_mode from local config file, or 'auto' on any failure."""
    try:
        data = json.loads(_config_path().read_text(encoding='utf-8'))
        return data.get('speech_mode', 'auto')
    except FileNotFoundError:
        return 'auto'  # config not yet written — benign on first run
    except Exception as exc:
        print(
            f"[agenttalk stop_hook] WARNING: could not read speech_mode "
            f"({type(exc).__name__}: {exc}) — defaulting to 'auto'.",
            file=sys.stderr,
        )
        return 'auto'


def main() -> None:
    # HOOK-04: Binary read + explicit UTF-8 decode.
    # sys.stdin on Windows defaults to CP1252 — must use buffer for non-ASCII safety.
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[agenttalk stop_hook] Failed to parse stdin: {exc}", file=sys.stderr)
        sys.exit(0)  # Malformed input — never block

    # HOOK-01: Guard against infinite loop.
    # Claude Code re-fires Stop hooks when a hook continuation runs.
    # stop_hook_active is True on those re-fires — exit immediately.
    if payload.get('stop_hook_active', False):
        sys.exit(0)

    text = payload.get('last_assistant_message', '').strip()
    if not text:
        sys.exit(0)

    # Semi-auto guard: read speech_mode directly from config file (no HTTP round-trip).
    if _read_speech_mode() == 'semi-auto':
        sys.exit(0)

    # HOOK-01: POST text to /speak endpoint.
    # 202 = queued, 200 = skipped (alpha filter), 503 = warmup — all acceptable.
    body = json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(
        SERVICE_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as _:
            pass
    except urllib.error.HTTPError as exc:
        # 503 = warmup, 200/202 never reach here; anything else is unexpected
        if exc.code not in (200, 202, 503):
            print(
                f"[agenttalk stop_hook] WARNING: /speak returned HTTP {exc.code}",
                file=sys.stderr,
            )
    except urllib.error.URLError:
        pass  # Service not running — acceptable; hook runs asynchronously
    except Exception as exc:
        print(f"[agenttalk stop_hook] Unexpected error: {exc}", file=sys.stderr)

    sys.exit(0)  # HOOK-03: Exit immediately; async: true handles non-blocking


if __name__ == '__main__':
    main()

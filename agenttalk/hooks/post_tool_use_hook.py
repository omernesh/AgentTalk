"""
AgentTalk PostToolUse hook.
Reads the most recent assistant message from the transcript JSONL and POSTs
to /speak so the user hears partial responses between tool calls.

Requirements: LATENCY-02
Called by Claude Code after each tool use in auto mode.
Registered in ~/.claude/settings.json with async: true by agenttalk setup.

Key differences from stop_hook.py:
  - No stop_hook_active guard (that guard is Stop-hook specific)
  - Reads transcript_path from payload (PostToolUse has no last_assistant_message field)
  - Calls _extract_assistant_text() to parse the JSONL transcript
  - Applies _is_substantial() filter before POSTing to avoid speaking one-liners
    like "Reading file..." during rapid tool use
"""
import sys
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

SERVICE_URL = 'http://localhost:5050/speak'
TIMEOUT_SECS = 3  # POST completes in <1s; 3s gives headroom without long block
MIN_CHARS = 80


def _config_path() -> Path:
    appdata = os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming'
    return Path(appdata) / 'AgentTalk' / 'config.json'


def _read_speech_mode() -> str:
    """Return speech_mode from local config file, or 'auto' on any failure."""
    try:
        data = json.loads(_config_path().read_text(encoding='utf-8'))
        return data.get('speech_mode', 'auto')
    except Exception:
        return 'auto'  # fail-open: treat missing/unreadable config as auto mode


def _extract_assistant_text(transcript_path: str) -> str:
    """
    Read the JSONL transcript and return the most recent assistant message text.

    Walks lines in reverse to find the most recent role=assistant entry.
    Unwraps message envelope if msg['type'] == 'message'.
    Extracts text from str content or list of type=text blocks.
    Returns empty string on any error (fail-open).
    """
    try:
        lines = Path(transcript_path).read_text(encoding='utf-8').splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Unwrap message envelope if present
            if msg.get('type') == 'message':
                msg = msg.get('message', msg)
            if msg.get('role') != 'assistant':
                continue
            content = msg.get('content', '')
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = [
                    block['text']
                    for block in content
                    if isinstance(block, dict) and block.get('type') == 'text'
                ]
                return ' '.join(parts).strip()
        return ''
    except Exception:
        return ''  # fail-open


def _is_substantial(text: str) -> bool:
    """
    Return True if text is long enough and ends with terminal punctuation.

    Anti-noise filter: prevents speaking one-liners like "Reading file..."
    during rapid tool use. Only substantial assistant messages are spoken.

    Requires: len > MIN_CHARS (80) AND last char is one of . ! ?
    """
    stripped = text.strip()
    return len(stripped) > MIN_CHARS and stripped[-1] in ('.', '!', '?')


def main() -> None:
    # Binary read + explicit UTF-8 decode — Windows stdin defaults to CP1252.
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        sys.exit(0)  # Malformed input — never block

    # Semi-auto guard: read speech_mode directly from config file (no HTTP round-trip).
    if _read_speech_mode() == 'semi-auto':
        sys.exit(0)

    transcript_path = payload.get('transcript_path', '')
    if not transcript_path:
        sys.exit(0)

    text = _extract_assistant_text(transcript_path)
    if not text:
        sys.exit(0)

    if not _is_substantial(text):
        sys.exit(0)

    # POST text to /speak endpoint.
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
    except urllib.error.URLError:
        pass  # Service not running or 503 warmup — silent fail
    except Exception as exc:
        print(f"[agenttalk post_tool_use_hook] Unexpected error: {exc}", file=sys.stderr)

    sys.exit(0)  # async: true handles non-blocking execution


if __name__ == '__main__':
    main()

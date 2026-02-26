"""
AgentTalk opencode Stop hook.

Mirror of agenttalk/hooks/stop_hook.py for opencode.
Reads the assistant message from stdin JSON and POSTs to /speak endpoint.

Usage: Register this file in opencode config as a PostResponse hook.
The hook receives JSON on stdin with the assistant message.

See integrations/opencode/README.md for registration instructions.
"""
import sys
import json
import urllib.request
import urllib.error

SERVICE_URL = 'http://localhost:5050/speak'
CONFIG_URL  = 'http://localhost:5050/config'
TIMEOUT_SECS = 3  # POST completes in <1s; 3s gives headroom without long block


def main() -> None:
    # Binary read + explicit UTF-8 decode for cross-platform safety.
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[agenttalk opencode hook] Failed to parse stdin: {exc}", file=sys.stderr)
        sys.exit(0)  # Malformed input — never block

    # Extract assistant message text.
    # opencode may use 'last_assistant_message', 'content', or 'text' key
    # depending on hook type. Try multiple keys in priority order.
    text = (
        payload.get('last_assistant_message', '') or
        payload.get('content', '') or
        payload.get('text', '') or
        payload.get('message', '')
    ).strip()

    if not text:
        sys.exit(0)

    # Semi-auto guard: fetch current speech_mode before deciding to speak.
    # Fail-open: if service unreachable or field absent, fall through to auto behavior.
    cfg_req = urllib.request.Request(CONFIG_URL, method='GET')
    try:
        with urllib.request.urlopen(cfg_req, timeout=2) as resp:
            cfg = json.loads(resp.read().decode('utf-8'))
        if cfg.get('speech_mode') == 'semi-auto':
            sys.exit(0)
    except urllib.error.URLError:
        pass  # service unreachable — fall through to speak
    except Exception as exc:
        print(f"[agenttalk opencode hook] Unexpected error reading config: {exc}", file=sys.stderr)

    # POST text to /speak endpoint.
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
        print(f"[agenttalk opencode hook] Unexpected error: {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()

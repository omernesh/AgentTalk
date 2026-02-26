"""
agenttalk.pipe — Stdin-to-TTS bridge.

Reads text from stdin (line by line or as a block) and POSTs it
to the AgentTalk /speak endpoint.

Usage:
    some_cli_tool | python -m agenttalk.pipe
    echo "Hello world" | python -m agenttalk.pipe

Options:
    --port PORT     AgentTalk service port (default: 5050)
    --batch         Read all stdin then speak (default: line-by-line)
    --quiet         Suppress progress output

Design: Zero TTS logic — this script is a thin pipe to localhost:5050/speak.
"""
import argparse
import json
import sys
import urllib.request
import urllib.error


def _post_speak(text: str, port: int = 5050) -> bool:
    """POST text to AgentTalk /speak. Returns True on success."""
    url = f"http://localhost:{port}/speak"
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status in (200, 202)
    except urllib.error.URLError:
        print(
            f"[agenttalk pipe] Service not reachable on port {port}. "
            "Is AgentTalk running? Start with: python -m agenttalk.service",
            file=sys.stderr,
        )
        return False
    except Exception as exc:
        print(f"[agenttalk pipe] Unexpected error: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agenttalk.pipe",
        description="Pipe stdin text to AgentTalk TTS service",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5050,
        help="AgentTalk service port (default: 5050)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Read all stdin first, then speak as a single block",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages",
    )
    args = parser.parse_args()

    if args.batch:
        # Read all stdin, then POST as a single block
        text = sys.stdin.read()
        if text.strip():
            success = _post_speak(text, port=args.port)
            if success and not args.quiet:
                print(f"[agenttalk pipe] Queued {len(text)} chars for TTS.")
    else:
        # Line-by-line streaming mode
        # Accumulate lines and POST when a natural break is detected.
        # This allows real-time speaking as text arrives.
        buffer = []
        for line in sys.stdin:
            stripped = line.rstrip("\n")
            if stripped:
                buffer.append(stripped)
                # Print to stdout so the caller still sees output
                print(stripped, flush=True)
            else:
                # Empty line = paragraph break — speak accumulated buffer
                if buffer:
                    text = " ".join(buffer)
                    _post_speak(text, port=args.port)
                    buffer.clear()

        # Speak any remaining buffered lines
        if buffer:
            text = " ".join(buffer)
            _post_speak(text, port=args.port)


if __name__ == "__main__":
    main()

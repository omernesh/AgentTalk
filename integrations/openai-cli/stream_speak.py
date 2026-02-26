"""
AgentTalk OpenAI streaming integration.

Calls the OpenAI API with streaming enabled and speaks each complete sentence
as it arrives, via AgentTalk localhost:5050/speak.

Usage:
    python integrations/openai-cli/stream_speak.py "What is quantum computing?"
    python integrations/openai-cli/stream_speak.py --model gpt-4o "Explain Python decorators"

Requirements:
    pip install openai agenttalk

Environment:
    OPENAI_API_KEY must be set.

Design: Zero TTS logic here — all audio goes through localhost:5050/speak.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def _post_speak(text: str, port: int = 5050) -> None:
    """POST text to AgentTalk /speak. Best-effort — never raises."""
    url = f"http://localhost:{port}/speak"
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as _:
            pass
    except urllib.error.URLError:
        pass  # Service offline or busy — silent fail by design
    except Exception as exc:
        print(f"[agenttalk pipe] Unexpected error posting to /speak: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream OpenAI responses and speak them via AgentTalk",
    )
    parser.add_argument("prompt", help="Prompt to send to the OpenAI API")
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5050,
        help="AgentTalk service port (default: 5050)",
    )
    parser.add_argument(
        "--system",
        default="You are a helpful assistant.",
        help="System message",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "ERROR: OPENAI_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print(
            "ERROR: openai package not installed. Run: pip install openai",
            file=sys.stderr,
        )
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    print(f"Prompt: {args.prompt}\n", flush=True)
    print("Response:", flush=True)

    # Accumulate tokens into a speaking buffer
    buffer = ""

    with client.chat.completions.stream(
        model=args.model,
        messages=[
            {"role": "system", "content": args.system},
            {"role": "user", "content": args.prompt},
        ],
    ) as stream:
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                print(delta, end="", flush=True)
                buffer += delta

                # Speak complete sentences as they accumulate.
                # Scan the buffer character-by-character for sentence-ending
                # punctuation so all separator types are handled in a single pass
                # (the previous per-separator loop broke after the first match,
                # leaving subsequent sentence boundaries unprocessed).
                last_cut = 0
                for idx, ch in enumerate(buffer):
                    if ch in ".!?:" and idx + 1 < len(buffer) and buffer[idx + 1] == " ":
                        sentence = buffer[last_cut:idx + 1].strip()
                        if sentence:
                            _post_speak(sentence, port=args.port)
                        last_cut = idx + 1
                buffer = buffer[last_cut:]

    # Speak any remaining buffer content
    if buffer.strip():
        _post_speak(buffer, port=args.port)

    print("\n\nDone.", flush=True)


if __name__ == "__main__":
    main()

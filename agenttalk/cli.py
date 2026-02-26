"""
AgentTalk CLI entry point.

Registered as a console_scripts entry point in pyproject.toml:
    agenttalk = "agenttalk.cli:main"

Subcommands:
    agenttalk setup   — Download model, register hooks, create desktop shortcut

Requirements: INST-01 (CLI entry point), INST-02, INST-03, INST-04
"""
import argparse
import sys


def main() -> None:
    """Main entry point for the `agenttalk` CLI command."""
    parser = argparse.ArgumentParser(
        prog="agenttalk",
        description="AgentTalk — real-time TTS for Claude Code output",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # agenttalk setup
    subparsers.add_parser(
        "setup",
        help=(
            "Download the Kokoro ONNX model, register Claude Code hooks, "
            "and create a desktop shortcut"
        ),
    ).set_defaults(func=_cmd_setup)

    args = parser.parse_args()
    args.func(args)


def _cmd_setup(args: argparse.Namespace) -> None:
    """
    Run the full setup sequence:
      1. Download Kokoro model files (skip if already present)
      2. Register Stop and SessionStart hooks in ~/.claude/settings.json
      3. Create AgentTalk.lnk desktop shortcut

    Order matters: model download first (largest risk of failure), then hooks
    (idempotent merge), then shortcut (idempotent overwrite).
    """
    print("=== AgentTalk Setup ===\n")

    # Step 1: Download Kokoro ONNX model (~310MB total)
    print("Step 1/3: Downloading Kokoro model files...")
    try:
        from agenttalk.installer import download_model
        download_model()
    except Exception as exc:
        print(f"\nERROR in model download: {exc}")
        print("Fix the error and re-run `agenttalk setup`.")
        sys.exit(1)

    # Step 2: Register hooks in ~/.claude/settings.json
    print("\nStep 2/3: Registering Claude Code hooks...")
    try:
        from agenttalk.setup import register_hooks
        register_hooks()
    except Exception as exc:
        print(f"\nERROR registering hooks: {exc}")
        print("Fix the error and re-run `agenttalk setup`.")
        sys.exit(1)

    # Step 3: Create icon file and desktop shortcut
    print("\nStep 3/3: Creating desktop shortcut...")
    try:
        from agenttalk.installer import create_shortcut
        create_shortcut()
    except Exception as exc:
        print(f"\nWARNING in shortcut creation: {exc}")
        # Shortcut failure is non-fatal — user can still launch from CLI

    print("\nSetup complete!")
    print("Double-click the AgentTalk shortcut on your desktop to start the service.")
    print("Or run: pythonw agenttalk/service.py")


if __name__ == "__main__":
    main()

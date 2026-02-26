"""
AgentTalk CLI entry point.

Registered as a console_scripts entry point in pyproject.toml:
    agenttalk = "agenttalk.cli:main"

Subcommands:
    agenttalk setup            — Download model, register hooks, register auto-start
    agenttalk setup --opencode — Also register opencode hooks
    agenttalk setup --no-autostart — Skip auto-start registration

Requirements: INST-01 (CLI entry point), INST-02, INST-03, INST-04
"""
import argparse
import sys


def main() -> None:
    """Main entry point for the `agenttalk` CLI command."""
    parser = argparse.ArgumentParser(
        prog="agenttalk",
        description="AgentTalk — real-time TTS for AI coding agents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # agenttalk setup
    setup_parser = subparsers.add_parser(
        "setup",
        help=(
            "Download the Kokoro ONNX model, register Claude Code hooks, "
            "register auto-start, and create a desktop shortcut (Windows)"
        ),
    )
    setup_parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="Skip registering the service as a system auto-start entry",
    )
    setup_parser.add_argument(
        "--opencode",
        action="store_true",
        help="Also register opencode hooks (in addition to Claude Code hooks)",
    )
    setup_parser.set_defaults(func=_cmd_setup)

    args = parser.parse_args()
    args.func(args)


def _cmd_setup(args: argparse.Namespace) -> None:
    """
    Run the full setup sequence:
      1. Download Kokoro model files (skip if already present)
      2. Register Stop and SessionStart hooks in ~/.claude/settings.json
      3. Register slash commands in ~/.claude/commands/
      4. Register auto-start mechanism (platform-appropriate)
      5. Create AgentTalk.lnk desktop shortcut (Windows only)
      6. [--opencode] Register opencode hooks

    Order matters: model download first (largest risk of failure), then hooks
    (idempotent merge), then auto-start, then shortcut (idempotent overwrite).
    """
    no_autostart = getattr(args, "no_autostart", False)
    register_opencode = getattr(args, "opencode", False)

    print("=== AgentTalk Setup ===\n")

    # Step 1: Download Kokoro ONNX model (~310MB total)
    print("Step 1/5: Downloading Kokoro model files...")
    try:
        from agenttalk.installer import download_model
        download_model()
    except Exception as exc:
        print(f"\nERROR in model download: {exc}")
        print("Fix the error and re-run `agenttalk setup`.")
        sys.exit(1)

    # Step 2: Register hooks and slash commands in ~/.claude/
    print("\nStep 2/5: Registering Claude Code hooks...")
    try:
        from agenttalk.setup import register_hooks
        register_hooks()
    except Exception as exc:
        print(f"\nERROR registering hooks: {exc}")
        print("Fix the error and re-run `agenttalk setup`.")
        sys.exit(1)

    print("\nStep 3/5: Registering slash commands...")
    try:
        from agenttalk.setup import register_commands
        register_commands()
    except Exception as exc:
        print(f"\nWARNING registering commands: {exc}")
        # Non-fatal — user can still use the service without slash commands

    # Step 4: Register auto-start
    print("\nStep 4/5: Registering auto-start...")
    try:
        from agenttalk.installer import register_autostart
        register_autostart(no_autostart=no_autostart)
    except Exception as exc:
        print(f"\nWARNING: auto-start registration failed: {exc}")
        # Non-fatal — user can still start the service manually

    # Step 5: Create icon file and desktop shortcut (Windows only)
    print("\nStep 5/5: Creating desktop shortcut...")
    try:
        from agenttalk.installer import create_shortcut
        create_shortcut()
    except Exception as exc:
        print(f"\nWARNING in shortcut creation: {exc}")
        # Shortcut failure is non-fatal — user can still launch from CLI

    # Optional: Register opencode hooks
    if register_opencode:
        print("\nRegistering opencode hooks...")
        try:
            from agenttalk.integrations.opencode import register_opencode_hooks
            register_opencode_hooks()
        except Exception as exc:
            print(f"\nWARNING: opencode hook registration failed: {exc}")
            # Non-fatal

    print("\nSetup complete!")
    print("Run `python -m agenttalk.service` to start the service.")
    print("Or use the auto-start mechanism registered above.")
    print("\nSlash commands available in Claude Code:")
    print("  /agenttalk:start  — start the service")
    print("  /agenttalk:stop   — stop the service")
    print("  /agenttalk:voice  — switch voice (e.g. /agenttalk:voice bm_george)")
    print("  /agenttalk:model  — switch engine (kokoro or piper)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
AgentTalk opencode UserPromptSubmit hook.

Previously injected Hebrew instructions when a Hebrew TTS engine was active.
This approach was abandoned — see agenttalk/hooks/user_prompt_hook.py for rationale.

This hook is kept registered but outputs nothing. Exit 0 always.
"""
import sys

sys.exit(0)

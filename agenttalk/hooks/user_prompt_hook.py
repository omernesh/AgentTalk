#!/usr/bin/env python3
"""
AgentTalk UserPromptSubmit hook.

Previously injected Hebrew instructions when a Hebrew TTS engine was active,
causing Claude to respond in Hebrew. This approach was abandoned because:
- Terminal Hebrew display is garbled/backwards in most Windows terminals
- Claude Code's output rendering doesn't handle RTL well

New approach: Claude always responds in English. The TTS pipeline translates
English → Hebrew before synthesis when a Hebrew voice is active (translator.py).

This hook is kept registered but outputs nothing. Exit 0 always.
"""
import sys

sys.exit(0)

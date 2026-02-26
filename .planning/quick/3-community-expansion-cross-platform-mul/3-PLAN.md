---
phase: quick
plan: 3
type: execute
wave: 1
depends_on: []
scope_note: >
  This plan spans 5 phases and 9 tasks — larger than the typical quick 2-3 task scope.
  It is expected to execute across multiple sessions. Phases 1-2 should be completed
  before attempting Phase 3+. Executors should stop and summarise after each phase.
files_modified:
  - agenttalk/service.py
  - agenttalk/tray.py
  - agenttalk/installer.py
  - agenttalk/config_loader.py
  - agenttalk/audio_duck.py
  - pyproject.toml
  - README.md
  - integrations/openclaw/SKILL.md
  - integrations/vscode/
  - integrations/opencode/
autonomous: false
requirements: []

must_haves:
  truths:
    # --- Executor-verifiable (can be checked in CI / local shell) ---
    - "twine check dist/* passes with no errors (pyproject.toml is PyPI-valid)"
    - "python -m build produces a dist/*.whl without errors"
    - "agenttalk/installer.py imports without error and register_autostart() is callable on all platforms"
    - "agenttalk/config_loader.py _config_dir() returns correct path on current platform"
    - "integrations/openclaw/RESEARCH.md exists and documents hook API findings"
    - "integrations/openclaw/SKILL.md exists and follows ClawHub skill format"
    - "integrations/vscode/RESEARCH.md exists and documents interception approach"
    - "integrations/vscode/*.vsix exists (extension packaged successfully via vsce package)"
    - "integrations/opencode/ contains hook scripts and README.md"
    - "All adapters are thin (< 50 lines each) — zero TTS logic outside the service"
    # --- Post-publish-verifiable (require external accounts / hardware) ---
    - "(post-publish) pip install agenttalk works on Windows, macOS, and Linux"
    - "(post-publish) agenttalk setup works on all three platforms (correct config paths, auto-start mechanism)"
    - "(post-publish) OpenClaw skill is published to ClawHub and starts the AgentTalk service"
    - "(post-publish) VSCode extension works with base VSCode, Roo Code, and KiloCode"
    - "(post-publish) opencode hook integration mirrors the Claude Code hook pattern"
    - "(post-publish) All adapters POST to the same localhost:5050 endpoint — no adapter-specific TTS logic"
  artifacts:
    - path: "integrations/openclaw/SKILL.md"
      provides: "ClawHub-publishable OpenClaw skill that starts AgentTalk and wires hooks"
    - path: "integrations/vscode/"
      provides: "VSCode extension (publishable to VSCode Marketplace)"
    - path: "integrations/opencode/"
      provides: "opencode hook scripts mirroring Claude Code integration"
    - path: "pyproject.toml"
      provides: "PyPI-publishable agenttalk package with entry point agenttalk setup"
  key_links:
    - from: "Any tool integration"
      to: "localhost:5050/speak"
      via: "HTTP POST with {text: '...'} — same endpoint for all tools"
    - from: "agenttalk setup --platform <win|mac|linux>"
      to: "platform-specific auto-start mechanism"
      via: "launchd (macOS) | systemd --user (Linux) | Task Scheduler (Windows)"
    - from: "ClawHub skill"
      to: "agenttalk PyPI package"
      via: "pip install agenttalk in skill setup instructions"
---

<objective>
Make AgentTalk installable by the developer community across Windows, macOS, and Linux,
starting with OpenClaw (ClawHub), then the VSCode ecosystem (VSCode + Roo Code + KiloCode),
then opencode, then OpenAI CLI.

Architecture: Service-first + thin adapters.
- The FastAPI TTS service is published to PyPI as `agenttalk`
- Each tool integration is a thin adapter that POSTs text to localhost:5050
- Platform differences are handled inside the service, not in the adapters

Priority order (do not skip ahead):
  Phase 1 → Cross-platform service + PyPI
  Phase 2 → OpenClaw / ClawHub
  Phase 3 → VSCode ecosystem
  Phase 4 → opencode
  Phase 5 → OpenAI CLI

Output: A community-installable multi-platform, multi-tool TTS companion for AI coding agents.
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md

## Current Architecture

AgentTalk is a FastAPI TTS service (localhost:5050) + pystray system tray + Claude Code hooks.

Key platform-specific code to make cross-platform:

```python
# config_loader.py — already uses Path.home() fallback, good pattern
APPDATA = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
CONFIG_DIR = APPDATA / "AgentTalk"

# Cross-platform equivalent needed:
# macOS:  ~/Library/Application Support/AgentTalk/
# Linux:  ~/.config/AgentTalk/   (XDG_CONFIG_HOME)
```

```python
# tray.py — pystray works on macOS (Cocoa) and Linux (GTK/AppIndicator)
# pystray already supports all three platforms natively
# macOS requires Pillow for icon; Linux requires GTK
```

```python
# installer.py — currently Windows-only
# Needs platform branch:
# Windows: Task Scheduler / startup folder
# macOS:   launchd plist in ~/Library/LaunchAgents/
# Linux:   systemd --user service in ~/.config/systemd/user/
```

```python
# audio_duck.py — Windows-specific audio ducking via pycaw/WASAPI
# sounddevice + soundfile are cross-platform (used in tts_worker.py)
# Kokoro ONNX runtime: pip install kokoro-onnx — works on macOS and Linux
# Piper: piper-tts package works on macOS and Linux
# audio_duck.py ducking logic is Windows-only and must be guarded with platform.system() == "Windows"
# tts_worker.py is the cross-platform audio playback path
```

## PyPI packaging

Current install: pip install git+https://github.com/omernesh/AgentTalk
Target: pip install agenttalk (PyPI)

pyproject.toml needs:
- [project.scripts] agenttalk = "agenttalk.cli:main"
- All dependencies pinned
- Platform markers for pystray (requires GTK extras on Linux)

## OpenClaw Skill Format

OpenClaw skills are a folder with SKILL.md (and optional supporting files).
Published via: clawhub publish <skill-dir>
The SKILL.md instructs the agent; the skill can include setup scripts.

OpenClaw does NOT have a built-in hooks API like Claude Code.
Integration approach: SKILL.md instructs the agent to run `agenttalk setup --opencode` is wrong.
Correct: SKILL.md starts the service and intercepts agent output by wrapping the response step.
Research needed: confirm whether OpenClaw has PostResponse hooks or equivalent.

## VSCode Extension Pattern

Roo Code and KiloCode are VSCode extensions — they share the VSCode extension API.
Any VSCode extension can listen to workspace events and read AI output via:
- vscode.window.onDidChangeActiveTextEditor
- Roo Code / KiloCode may expose their own events via extension API

Research needed: confirm Roo Code and KiloCode extension APIs for output interception.

## opencode Hooks

opencode has a hooks system similar to Claude Code.
Docs: https://opencode.ai/docs
Hook events likely include: session start, assistant response complete.
Integration approach: identical to Claude Code — shell scripts that POST to localhost:5050.
</context>

<tasks>

<!-- ================================================================ -->
<!-- PHASE 1: Cross-Platform Service + PyPI                           -->
<!-- ================================================================ -->

<task type="research">
  <name>Phase 1, Task 1: Audit all platform-specific code in the service</name>
  <files>agenttalk/config_loader.py, agenttalk/installer.py, agenttalk/tray.py, agenttalk/audio_duck.py, agenttalk/service.py</files>
  <action>
Read each file and list every place that hard-codes Windows behavior:
- APPDATA / %APPDATA% references
- pythonw.exe / .bat / .lnk / Task Scheduler calls
- WASAPI-specific code (audio_duck.py — Windows-only ducking, must be guarded)
- Windows path separators that are not using pathlib

Produce a brief report saved to docs/cross-platform-audit.md:
what changes for macOS, what changes for Linux, what is already portable.
  </action>
  <verify>ls docs/cross-platform-audit.md</verify>
  <done>
    - docs/cross-platform-audit.md exists with complete list of platform-specific code locations (file + line numbers)
    - Cross-platform equivalents identified for each location in the report
  </done>
</task>

<task type="auto">
  <name>Phase 1, Task 2: Cross-platform config paths</name>
  <files>agenttalk/config_loader.py</files>
  <action>
Replace the Windows-specific config path with a platform-aware helper:

```python
import platform, os
from pathlib import Path

def _config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux + anything else
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "AgentTalk"
```

Use _config_dir() everywhere CONFIG_DIR is currently computed.
  </action>
  <verify>python -c "from agenttalk.config_loader import _config_dir; print(_config_dir())"</verify>
  <done>
    - Config path resolves correctly on all three platforms
    - No hard-coded APPDATA references remain
  </done>
</task>

<task type="auto">
  <name>Phase 1, Task 3: Cross-platform auto-start in installer.py</name>
  <files>agenttalk/installer.py</files>
  <action>
Add platform branches to the auto-start registration step:

Windows (existing): Task Scheduler or startup folder .lnk
macOS: Write ~/Library/LaunchAgents/ai.agenttalk.plist — launchd plist that runs `agenttalk start`
Linux: Write ~/.config/systemd/user/agenttalk.service — systemd --user service; run `systemctl --user enable --now agenttalk`

The installer should detect platform.system() and apply the correct method.
Provide a --no-autostart flag to skip this step.
  </action>
  <verify>python -c "from agenttalk.installer import register_autostart; print('ok')"</verify>
  <done>
    - register_autostart() works on Windows, macOS, and Linux
    - Correct platform-specific mechanism used on each OS
    - --no-autostart flag skips auto-start registration
  </done>
</task>

<task type="auto">
  <name>Phase 1, Task 4: Publish to PyPI</name>
  <files>pyproject.toml, setup.py (if present)</files>
  <action>
Ensure pyproject.toml is correct for PyPI publication:
- name = "agenttalk"
- [project.scripts] agenttalk = "agenttalk.cli:main"
- All runtime dependencies listed with version constraints
- Python requires = ">=3.11"
- Platform extras: agenttalk[linux] installs pystray[gtk] for Linux

Build and publish:
  python -m build
  twine check dist/*
  twine upload dist/*

Tag the release: git tag v1.1.0 (cross-platform milestone)
  </action>
  <verify>pip index versions agenttalk</verify>
  <done>
    - pip install agenttalk installs the service on Windows, macOS, and Linux
    - agenttalk setup works on all three platforms
    - Package is listed on PyPI at https://pypi.org/project/agenttalk/
  </done>
</task>

<!-- ================================================================ -->
<!-- PHASE 2: OpenClaw / ClawHub                                      -->
<!-- ================================================================ -->

<task type="research">
  <name>Phase 2, Task 1: Research OpenClaw hooks/events API</name>
  <files>integrations/openclaw/</files>
  <action>
Read OpenClaw docs at https://docs.openclaw.ai and https://openclawlab.com/en/docs/
Specifically research:
- Does OpenClaw have PostResponse hooks? (equivalent to Claude Code Stop hook)
- Does OpenClaw have SessionStart hooks?
- How does a SKILL.md wire into agent lifecycle events?
- What is the ClawHub publish workflow?

Document findings in integrations/openclaw/RESEARCH.md.
  </action>
  <verify>ls integrations/openclaw/RESEARCH.md</verify>
  <done>
    - integrations/openclaw/RESEARCH.md exists with OpenClaw hook/event API documented
    - ClawHub publish workflow documented in RESEARCH.md
    - Integration approach confirmed and recorded in RESEARCH.md
  </done>
</task>

<task type="auto">
  <name>Phase 2, Task 2: Create OpenClaw SKILL.md and publish to ClawHub</name>
  <files>integrations/openclaw/SKILL.md</files>
  <action>
Create integrations/openclaw/SKILL.md that:
1. Instructs OpenClaw to install AgentTalk on first use: `pip install agenttalk && agenttalk setup`
2. Wires the AgentTalk service start into the session lifecycle
3. POSTs agent responses to localhost:5050/speak after each assistant reply
4. Provides /agenttalk:voice and /agenttalk:model equivalent commands

Follow ClawHub skill format (see RESEARCH.md from previous task).
Publish: clawhub publish integrations/openclaw/
  </action>
  <done>
    - SKILL.md published to ClawHub as "agenttalk"
    - OpenClaw users can install with: clawhub install agenttalk
    - AgentTalk speaks agent responses in OpenClaw
  </done>
</task>

<!-- ================================================================ -->
<!-- PHASE 3: VSCode Ecosystem                                        -->
<!-- ================================================================ -->

<task type="research">
  <name>Phase 3, Task 1: Research VSCode extension API for AI output interception</name>
  <files>integrations/vscode/</files>
  <action>
Research:
- VSCode extension API for intercepting text output
- How Roo Code (RooCodeInc/Roo-Code) exposes its response events
- How KiloCode (kilo-org/kilocode) exposes its response events
- Whether a single extension can hook into all three (VSCode + Roo + Kilo)

VSCode Marketplace publish requirements and process.

Document in integrations/vscode/RESEARCH.md.
  </action>
  <done>
    - Interception approach confirmed for base VSCode, Roo Code, and KiloCode
    - Extension architecture designed
  </done>
</task>

<task type="auto">
  <name>Phase 3, Task 2: Build and publish VSCode extension</name>
  <files>integrations/vscode/</files>
  <action>
Create a VSCode extension that:
1. Activates when VSCode opens
2. Checks if AgentTalk service is running (GET localhost:5050/health)
3. If not running, prompts user to run `agenttalk start` (or starts it automatically)
4. Intercepts AI agent responses (Roo Code, KiloCode, Copilot Chat) and POSTs to localhost:5050/speak
5. Provides a status bar item showing AgentTalk state (speaking / muted / offline)
6. Settings: enable/disable, port configuration

Package the extension:
  vsce package

Publish (requires VSCode Marketplace publisher account):
  vsce publish
Register on: https://marketplace.visualstudio.com/
  </action>
  <verify>ls integrations/vscode/*.vsix</verify>
  <done>
    - Extension packaged (integrations/vscode/*.vsix exists)
    - Extension published to VSCode Marketplace
    - Works with base VSCode, Roo Code, and KiloCode
    - Status bar shows AgentTalk state
  </done>
</task>

<!-- ================================================================ -->
<!-- PHASE 4: opencode                                                -->
<!-- ================================================================ -->

<task type="auto">
  <name>Phase 4: opencode hook integration</name>
  <files>integrations/opencode/</files>
  <action>
Research opencode hooks at https://opencode.ai/docs.
Create hook scripts that mirror the Claude Code integration:
- SessionStart equivalent: start AgentTalk service
- PostResponse equivalent: POST assistant text to localhost:5050/speak

Add `agenttalk setup --opencode` as a subcommand in the installer that registers opencode hooks.

Create integrations/opencode/README.md with install instructions.
  </action>
  <done>
    - agenttalk setup --opencode registers hooks in opencode config
    - Agent responses are spoken in opencode sessions
  </done>
</task>

<!-- ================================================================ -->
<!-- PHASE 5: OpenAI CLI                                              -->
<!-- ================================================================ -->

<task type="research">
  <name>Phase 5: Research OpenAI CLI hook/event mechanism</name>
  <files>integrations/openai-cli/</files>
  <action>
Research the official OpenAI CLI tool for hook or pipe-based interception.
If no hook API exists, consider a wrapper script approach:
  openai-with-tts() { openai "$@" | agenttalk pipe }
  agenttalk pipe reads stdin and POSTs chunks to localhost:5050/speak

Document approach and implement: integrations/openai-cli/
  </action>
  <done>
    - OpenAI CLI integration documented and implemented
    - Agent responses are spoken when using OpenAI CLI
  </done>
</task>

</tasks>

<verification>
After each phase:
1. pip install agenttalk installs cleanly on the target platform
2. The tool-specific integration starts the service and speaks AI output
3. muted / unmuted state persists across sessions
4. No adapter contains TTS logic — all audio goes through localhost:5050

Final end-to-end check:
- Fresh macOS machine: pip install agenttalk && agenttalk setup → Claude Code speaks ✓
- Fresh Linux machine: pip install agenttalk && agenttalk setup → Claude Code speaks ✓
- OpenClaw: clawhub install agenttalk → agent responses spoken ✓
- VSCode: install extension → Roo Code responses spoken ✓
- opencode: agenttalk setup --opencode → responses spoken ✓
</verification>

<success_criteria>
- agenttalk is published on PyPI and installable with a single pip command on Windows/macOS/Linux
- agenttalk setup works on all three platforms with correct auto-start mechanism
- OpenClaw skill is published on ClawHub
- VSCode extension is published on VSCode Marketplace and works with Roo Code and KiloCode
- opencode integration ships via agenttalk setup --opencode
- OpenAI CLI integration documented with install instructions
- README covers all platforms and all tool integrations
- All adapters are thin (< 50 lines each) — zero TTS logic outside the service
</success_criteria>

<output>
After completion, create .planning/quick/3-community-expansion-cross-platform-mul/3-SUMMARY.md
</output>

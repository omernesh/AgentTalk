---
phase: quick-4
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - integrations/antigravity/SKILL.md
  - integrations/antigravity/session_workflow.md
  - integrations/antigravity/README.md
  - agenttalk/integrations/antigravity.py
  - agenttalk/cli.py
autonomous: true
requirements: [QUICK-4]

must_haves:
  truths:
    - "An Antigravity skill file exists that teaches the Antigravity agent to POST responses to localhost:5050/speak"
    - "A global workflow template exists that starts the AgentTalk service at session start"
    - "agenttalk setup --antigravity copies the skill and workflow to ~/.gemini/antigravity/skills/ and ~/.gemini/antigravity/global_workflows/"
    - "The existing VSCode VSIX is noted in README as compatible with Antigravity (VS Code fork) — no new extension build needed"
  artifacts:
    - path: "integrations/antigravity/SKILL.md"
      provides: "Native Antigravity skill for agent-based TTS integration"
      contains: "localhost:5050/speak"
    - path: "integrations/antigravity/session_workflow.md"
      provides: "Global workflow template for session-start service launch"
      contains: "python -m agenttalk.service"
    - path: "integrations/antigravity/README.md"
      provides: "User-facing setup instructions for Antigravity integration"
      contains: "agenttalk setup --antigravity"
    - path: "agenttalk/integrations/antigravity.py"
      provides: "register_antigravity_hooks() called by agenttalk setup --antigravity"
      exports: ["register_antigravity_hooks"]
    - path: "agenttalk/cli.py"
      provides: "--antigravity flag wired into setup subcommand"
      contains: "--antigravity"
  key_links:
    - from: "agenttalk/cli.py"
      to: "agenttalk/integrations/antigravity.py"
      via: "register_antigravity_hooks() import in _cmd_setup"
      pattern: "register_antigravity_hooks"
    - from: "agenttalk/integrations/antigravity.py"
      to: "integrations/antigravity/SKILL.md"
      via: "shutil.copy2 to ~/.gemini/antigravity/skills/"
      pattern: "shutil.copy2"
    - from: "integrations/antigravity/SKILL.md"
      to: "localhost:5050/speak"
      via: "curl POST instruction in agent rules"
      pattern: "5050/speak"
---

<objective>
Add Google Antigravity IDE integration for AgentTalk — analogous to integrations/openclaw/ and integrations/opencode/.

Antigravity is a VS Code fork (agent-first IDE, launched Nov 2025) with a native skills system at ~/.gemini/antigravity/skills/ and global workflows at ~/.gemini/antigravity/global_workflows/. It has no lifecycle hooks, so the integration is instruction-based (like OpenClaw): a skill file teaches the Antigravity agent to call /speak after each response, and a workflow template handles service startup.

The existing VSCode VSIX also works in Antigravity (VS Code fork) — no new extension build required.

Purpose: Expand AgentTalk's community coverage to Antigravity users.
Output: integrations/antigravity/ directory, agenttalk/integrations/antigravity.py, --antigravity flag in CLI.
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md

@integrations/openclaw/SKILL.md
@agenttalk/integrations/opencode.py
@agenttalk/cli.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create integrations/antigravity/ with SKILL.md, session_workflow.md, and README.md</name>
  <files>
    integrations/antigravity/SKILL.md
    integrations/antigravity/session_workflow.md
    integrations/antigravity/README.md
  </files>
  <action>
Create the integrations/antigravity/ directory and three files, modeled after integrations/openclaw/.

**integrations/antigravity/SKILL.md** — native Antigravity skill file for ~/.gemini/antigravity/skills/agenttalk.md.
This is a markdown file the Antigravity agent reads as a skill. Mirror the OpenClaw SKILL.md structure closely.
Sections to include:
- Header: "# AgentTalk — Real-Time Voice for Google Antigravity"
- "## Setup (run once)" — pip install agenttalk + agenttalk setup --antigravity. This copies skill and workflow to correct Antigravity directories.
- "## How It Works" — local FastAPI service, POST http://localhost:5050/speak, {"text": "..."}
- "## Agent Instructions" with three subsections:
  - "### Session Start" — check health with curl http://localhost:5050/health; if offline, start service:
    - Windows: `start pythonw -m agenttalk.service`
    - macOS/Linux: `python -m agenttalk.service &`
  - "### After Each Response" — POST response text to /speak (trim code blocks, file contents, long outputs). Use the same curl command as openclaw SKILL.md.
  - "### Muting" — POST {"muted": true/false} to /config
- "## Slash Commands" — /agenttalk:voice, /agenttalk:model, /agenttalk:stop, /agenttalk:start (same as openclaw SKILL.md with curl examples)
- "## VS Code Extension" — note: Antigravity is a VS Code fork, so the existing VSIX (integrations/vscode/agenttalk-vscode-1.0.0.vsix) also works. Users can install it via Antigravity's extension panel or Extensions: Install from VSIX. This gives UI status bar + auto-start without relying on agent instructions.
- "## Platforms" table — same as openclaw SKILL.md
- "## Troubleshooting" — same as openclaw SKILL.md
- "## Links" — GitHub + PyPI + API docs

**integrations/antigravity/session_workflow.md** — template for ~/.gemini/antigravity/global_workflows/agenttalk_start.md.
This is a workflow file the user copies to their global workflows directory. It tells Antigravity's agent to ensure AgentTalk is running at the start of any session.
Format:
```markdown
# AgentTalk Start

Ensure the AgentTalk TTS service is running before beginning any session.

## Steps

1. Check if AgentTalk is running:
   ```bash
   curl -s http://localhost:5050/health 2>/dev/null || echo "offline"
   ```

2. If the response is not `{"status": "ok"}`, start the service:
   - **Windows:** `start pythonw -m agenttalk.service`
   - **macOS/Linux:** `python -m agenttalk.service &`

3. Wait 3 seconds, then verify health again.

AgentTalk runs on http://localhost:5050. No data leaves your machine.
```

**integrations/antigravity/README.md** — user-facing setup instructions.
Sections:
- Quick Setup: `pip install agenttalk` + `agenttalk setup --antigravity` (installs skill to ~/.gemini/antigravity/skills/agenttalk.md and workflow to ~/.gemini/antigravity/global_workflows/agenttalk_start.md)
- VS Code Extension Alternative: Antigravity is a VS Code fork — install VSIX from Extensions panel for a UI approach
- Manual Setup: table showing where to place each file, with platform paths for ~/.gemini/ directory
- How It Works: brief explanation of skill-based agent instructions
- Endpoint: POST http://localhost:5050/speak
- Troubleshooting: same pattern as opencode README
- Links
  </action>
  <verify>
ls integrations/antigravity/ shows SKILL.md, session_workflow.md, README.md.
grep -l "5050/speak" integrations/antigravity/SKILL.md returns the file.
grep -l "agenttalk setup --antigravity" integrations/antigravity/README.md returns the file.
grep -l "VS Code" integrations/antigravity/SKILL.md returns the file (VSIX compatibility note present).
  </verify>
  <done>
Three files exist in integrations/antigravity/. SKILL.md contains agent instructions with /speak POST and /config mute commands. session_workflow.md is a copyable workflow template. README.md documents quick setup with --antigravity flag and VSIX alternative.
  </done>
</task>

<task type="auto">
  <name>Task 2: Create agenttalk/integrations/antigravity.py and wire --antigravity into CLI</name>
  <files>
    agenttalk/integrations/antigravity.py
    agenttalk/cli.py
  </files>
  <action>
**agenttalk/integrations/antigravity.py** — mirror of agenttalk/integrations/opencode.py for Antigravity.

Module docstring: "AgentTalk Antigravity integration helper. Provides register_antigravity_hooks() which copies the AgentTalk skill and workflow files to the Antigravity global directories. Called by: agenttalk setup --antigravity"

Imports: json, os, platform, shutil, sys from stdlib; Path from pathlib; _config_dir from agenttalk.config_loader.

Function `_antigravity_skills_dir() -> Path`:
- Returns ~/.gemini/antigravity/skills/ on all platforms (Antigravity uses home-relative ~/.gemini/ regardless of OS).
- No platform branching needed — the directory is always Path.home() / ".gemini" / "antigravity" / "skills".

Function `_antigravity_workflows_dir() -> Path`:
- Returns ~/.gemini/antigravity/global_workflows/ — always Path.home() / ".gemini" / "antigravity" / "global_workflows".

Function `_integration_files_dir() -> Path`:
- Returns the integrations/antigravity/ directory relative to this file.
- Path(__file__).parent.parent.parent / "integrations" / "antigravity"
- This resolves to the repo root's integrations/antigravity/ when running from source.
- Fallback note: if directory does not exist, raise FileNotFoundError with a helpful message.

Function `register_antigravity_hooks() -> None`:
- Docstring: "Copy AgentTalk skill and workflow files to Antigravity global directories. Creates directories if they do not exist. Idempotent: re-running overwrites with current versions."
- src_dir = _integration_files_dir()
- skills_dir = _antigravity_skills_dir(); skills_dir.mkdir(parents=True, exist_ok=True)
- workflows_dir = _antigravity_workflows_dir(); workflows_dir.mkdir(parents=True, exist_ok=True)
- Copy SKILL.md to skills_dir / "agenttalk.md" using shutil.copy2
- Copy session_workflow.md to workflows_dir / "agenttalk_start.md" using shutil.copy2
- Print confirmation lines:
  - f"  Antigravity skill installed: {skills_dir / 'agenttalk.md'}"
  - f"  Antigravity workflow installed: {workflows_dir / 'agenttalk_start.md'}"
  - "\n  To activate: open Antigravity, the agenttalk skill is now available."
  - "  Optionally install the VS Code extension VSIX for a UI status bar:"
  - "    integrations/vscode/agenttalk-vscode-1.0.0.vsix (Extensions: Install from VSIX)"

**agenttalk/cli.py** — add --antigravity flag to setup subcommand and call register_antigravity_hooks().

In _cmd_setup argument parser block (after --opencode arg), add:
```python
setup_parser.add_argument(
    "--antigravity",
    action="store_true",
    help="Also install Antigravity skill and workflow files to ~/.gemini/antigravity/",
)
```

In _cmd_setup function body, read the flag:
```python
register_antigravity = getattr(args, "antigravity", False)
```

After the existing opencode block (at the bottom of _cmd_setup, before "print('\nSetup complete!')"), add:
```python
# Optional: Install Antigravity skill and workflow
if register_antigravity:
    print("\nInstalling Antigravity skill and workflow...")
    try:
        from agenttalk.integrations.antigravity import register_antigravity_hooks
        register_antigravity_hooks()
    except Exception as exc:
        print(f"\nWARNING: Antigravity setup failed: {exc}")
        # Non-fatal
```

Update the docstring of _cmd_setup to include:
  "7. [--antigravity] Install Antigravity skill and workflow files"

Do NOT change the step numbering of existing steps in the print statements — just insert the new optional block before "Setup complete!".
  </action>
  <verify>
python -c "from agenttalk.integrations.antigravity import register_antigravity_hooks; print('import ok')" exits 0.
python -m agenttalk.cli setup --help | grep -q "antigravity" returns 0 (flag appears in help).
grep -n "register_antigravity" agenttalk/cli.py shows the import and call present.
  </verify>
  <done>
agenttalk/integrations/antigravity.py exists with register_antigravity_hooks(). agenttalk setup --antigravity flag is wired up in cli.py. Running agenttalk setup --antigravity copies SKILL.md to ~/.gemini/antigravity/skills/agenttalk.md and session_workflow.md to ~/.gemini/antigravity/global_workflows/agenttalk_start.md.
  </done>
</task>

</tasks>

<verification>
1. `ls integrations/antigravity/` shows: SKILL.md, session_workflow.md, README.md
2. `grep "5050/speak" integrations/antigravity/SKILL.md` shows curl POST command
3. `grep "antigravity" agenttalk/cli.py` shows --antigravity argument and register_antigravity_hooks call
4. `python -c "from agenttalk.integrations.antigravity import register_antigravity_hooks; print('ok')"` exits 0
5. `python -m agenttalk.cli setup --help` shows --antigravity in option list
6. `grep "VS Code\|VSIX" integrations/antigravity/SKILL.md` confirms VSIX compatibility note is present
</verification>

<success_criteria>
- integrations/antigravity/ directory contains three files: SKILL.md, session_workflow.md, README.md
- SKILL.md teaches Antigravity agent to POST to localhost:5050/speak after each response and start service at session start
- SKILL.md includes a VS Code Extension section noting VSIX compatibility (Antigravity is a VS Code fork)
- session_workflow.md is a ready-to-copy workflow template for ~/.gemini/antigravity/global_workflows/
- agenttalk/integrations/antigravity.py provides register_antigravity_hooks() that copies both files to correct Antigravity directories
- agenttalk setup --antigravity is a valid CLI invocation that runs the integration setup non-fatally
</success_criteria>

<output>
After completion, create `.planning/quick/4-add-google-antigravity-ide-integration/4-SUMMARY.md` with:
- What was built (files created/modified)
- Key decisions made
- Patterns established
- Any deviations from the plan
</output>

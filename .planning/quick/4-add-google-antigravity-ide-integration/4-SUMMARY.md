---
phase: quick-4
plan: 01
subsystem: integrations
tags: [antigravity, integration, tts, skill, cli]
dependency_graph:
  requires: [agenttalk/integrations/opencode.py, integrations/openclaw/SKILL.md]
  provides: [integrations/antigravity/, agenttalk/integrations/antigravity.py, --antigravity CLI flag]
  affects: [agenttalk/cli.py]
tech_stack:
  added: []
  patterns: [instruction-based-skill-integration, shutil-copy2-idempotent-install]
key_files:
  created:
    - integrations/antigravity/SKILL.md
    - integrations/antigravity/session_workflow.md
    - integrations/antigravity/README.md
    - agenttalk/integrations/antigravity.py
  modified:
    - agenttalk/cli.py
decisions:
  - "Antigravity uses ~/.gemini/antigravity/ on all platforms — no OS branching needed in _antigravity_skills_dir() or _antigravity_workflows_dir()"
  - "VSIX compatibility documented in SKILL.md and README.md — Antigravity is a VS Code fork so existing agenttalk-vscode-1.0.0.vsix works without new build"
  - "Integration is instruction-based (like OpenClaw) not hook-based — Antigravity has no lifecycle hook API"
metrics:
  duration: "2 min"
  completed: "2026-02-27"
  tasks_completed: 2
  files_created: 5
---

# Quick Task 4: Add Google Antigravity IDE Integration Summary

**One-liner:** Antigravity skill+workflow files with register_antigravity_hooks() and --antigravity CLI flag — instruction-based integration matching OpenClaw pattern.

---

## What Was Built

### integrations/antigravity/ (3 files)

**`integrations/antigravity/SKILL.md`**
Native Antigravity skill file for `~/.gemini/antigravity/skills/agenttalk.md`. Teaches the Antigravity agent to:
- Check AgentTalk health at session start and start service if offline
- POST each response to `http://localhost:5050/speak` (trimming code blocks)
- Mute/unmute via POST to `/config`
- Respond to slash commands: `/agenttalk:voice`, `/agenttalk:model`, `/agenttalk:stop`, `/agenttalk:start`
- Install the VS Code extension VSIX as an alternative UI approach (Antigravity is a VS Code fork)

**`integrations/antigravity/session_workflow.md`**
Ready-to-copy workflow template for `~/.gemini/antigravity/global_workflows/agenttalk_start.md`. Ensures the AgentTalk service is running before each Antigravity session starts, with platform-appropriate start commands for Windows and macOS/Linux.

**`integrations/antigravity/README.md`**
User-facing setup documentation covering:
- Quick setup: `pip install agenttalk && agenttalk setup --antigravity`
- VS Code extension VSIX alternative (for UI status bar)
- Manual file placement table with platform-specific `~/.gemini/` paths
- How the skill+workflow integration works
- Troubleshooting guide

### agenttalk/integrations/antigravity.py (new)

Module providing `register_antigravity_hooks()`:
- `_antigravity_skills_dir()` — returns `~/.gemini/antigravity/skills/` (cross-platform, no branching)
- `_antigravity_workflows_dir()` — returns `~/.gemini/antigravity/global_workflows/`
- `_integration_files_dir()` — resolves repo root `integrations/antigravity/` with helpful FileNotFoundError on missing
- `register_antigravity_hooks()` — copies SKILL.md and session_workflow.md to correct Antigravity dirs, creates dirs if absent, idempotent

### agenttalk/cli.py (modified)

- Module docstring updated to list `agenttalk setup --antigravity`
- `--antigravity` argument added to setup subparser
- `_cmd_setup` docstring updated with step 7
- `register_antigravity = getattr(args, "antigravity", False)` added
- Antigravity setup block added after opencode block, before "Setup complete!" — non-fatal

---

## Key Decisions

1. **No OS branching in directory helpers** — Antigravity always uses `~/.gemini/antigravity/` regardless of platform. Unlike opencode.py which has Windows/Linux/macOS branching, `_antigravity_skills_dir()` and `_antigravity_workflows_dir()` are single-line Path.home() expressions.

2. **VSIX compatibility documented** — Antigravity is a VS Code fork, so the existing `integrations/vscode/agenttalk-vscode-1.0.0.vsix` works without building a new extension. Both SKILL.md and README.md note this as an alternative to the instruction-based approach.

3. **Instruction-based integration (not hook-based)** — Antigravity has no confirmed lifecycle hook API, so the integration follows the OpenClaw pattern: a skill file teaches the agent to call `/speak` after each response, and a workflow template handles service startup. The agent acts on instructions rather than automated hook callbacks.

---

## Patterns Established

- `~/.gemini/antigravity/` is the canonical Antigravity config root (cross-platform)
- Antigravity skills live in `~/.gemini/antigravity/skills/<name>.md`
- Antigravity global workflows live in `~/.gemini/antigravity/global_workflows/<name>.md`
- `agenttalk setup --<ide>` is the standard installation pattern for all IDE integrations

---

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 60948f2 | feat(quick-4): add integrations/antigravity/ with SKILL.md, session_workflow.md, README.md |
| Task 2 | 7a86f54 | feat(quick-4): add agenttalk/integrations/antigravity.py and --antigravity CLI flag |

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Self-Check: PASSED

Files verified:
- FOUND: integrations/antigravity/SKILL.md
- FOUND: integrations/antigravity/session_workflow.md
- FOUND: integrations/antigravity/README.md
- FOUND: agenttalk/integrations/antigravity.py
- FOUND: agenttalk/cli.py (modified)

Commits verified:
- FOUND: 60948f2
- FOUND: 7a86f54

Functional checks:
- `from agenttalk.integrations.antigravity import register_antigravity_hooks` — import ok
- `python -m agenttalk.cli setup --help | grep antigravity` — flag present
- `grep "5050/speak" integrations/antigravity/SKILL.md` — POST endpoint present
- `grep "VS Code\|VSIX" integrations/antigravity/SKILL.md` — VSIX note present

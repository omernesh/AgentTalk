# OpenClaw / ClawHub Integration Research

Date: 2026-02-26
Researcher: AgentTalk automated research task

---

## Summary

OpenClaw is an AI coding agent with a skills/plugin system published via ClawHub.
Research was conducted by reviewing the OpenClaw documentation structure, the
ClawHub repository format, and available public information about OpenClaw's
agent lifecycle hooks.

---

## Findings: OpenClaw Hook API

### Does OpenClaw Have PostResponse Hooks?

**Status: Uncertain / Not Confirmed**

As of February 2026, OpenClaw does not have a publicly documented hook API
equivalent to Claude Code's `Stop` hook (`PostToolUse`/`PostResponse` events).

Claude Code exposes explicit hook trigger events:
- `Stop` — fires after every assistant response completes
- `SessionStart` — fires when a new session opens
- `PreToolUse` / `PostToolUse` — fires around tool invocations

OpenClaw's agent lifecycle (based on available documentation) works differently:
- Skills are SKILL.md files that provide instructions to the agent
- The agent follows instructions at the start of sessions or when a skill is invoked
- There is no confirmed `PostResponse` event hook mechanism

### Integration Approach Without Native Hooks

Given the absence of a confirmed hook API, the recommended integration approach is:

**Option A: SKILL.md instruction-based integration (recommended)**

The SKILL.md instructs the OpenClaw agent to:
1. Ensure AgentTalk is running at session start (via `pip install agenttalk && agenttalk setup`)
2. At the end of each assistant response, the SKILL.md can instruct the agent to
   explicitly call `agenttalk speak "<response>"` — but this requires agent compliance,
   not a guaranteed automatic hook

**Option B: Session-level startup only**

The skill ensures the AgentTalk service is running. The user manually triggers
voice output via slash commands. Less seamless but guaranteed to work.

### ClawHub Publish Workflow

Based on available information:

```bash
# Install ClawHub CLI
pip install clawhub

# Authenticate
clawhub login

# Publish a skill
clawhub publish integrations/openclaw/

# Install a skill (end-user command)
clawhub install agenttalk
```

The skill directory must contain:
- `SKILL.md` — the skill instructions that the agent loads
- Optional: supporting files, setup scripts, README

ClawHub uses a `clawhub.yaml` or the directory name as the skill identifier.

### Skill Format

A SKILL.md for ClawHub follows this structure:
1. Short description (first line = skill name/title)
2. Setup instructions (run once when skill is first used)
3. Usage instructions (what the agent does when the skill is active)
4. Optional: slash command definitions

---

## Integration Decision

Given the research findings, the AgentTalk OpenClaw skill will:

1. **At session start**: Ensure AgentTalk service is running
   - Check if service responds on localhost:5050/health
   - If not: run `python -m agenttalk.service &` in the background

2. **After each response**: Instruct the agent to POST the response to AgentTalk
   - The SKILL.md will contain explicit instructions for the agent to call
     the speak endpoint after each response
   - This is softer than a true hook but works within OpenClaw's skill model

3. **Slash commands**: Mirror the Claude Code slash command set
   - `/agenttalk:voice`, `/agenttalk:model`, `/agenttalk:stop`

---

## Limitations

- Without a native `PostResponse` hook, voice output depends on agent compliance with SKILL.md instructions
- The integration cannot guarantee automatic speaking on every response (unlike Claude Code)
- If/when OpenClaw adds a formal hook API, the SKILL.md can be updated to use it

---

## References

- OpenClaw docs: https://docs.openclaw.ai (reviewed; hook API not found)
- ClawHub: https://openclawlab.com/en/docs/ (reviewed; publish workflow documented)
- Claude Code hook comparison: agenttalk/hooks/ directory in this repository

---
phase: quick
plan: 3
subsystem: cross-platform-service, community-integrations
tags: [cross-platform, pypi, openclaw, vscode, opencode, openai-cli, tts, packaging]
dependency_graph:
  requires: [quick-1, quick-2]
  provides: [cross-platform-service, openclaw-skill, vscode-extension, opencode-hooks, openai-cli-pipe]
  affects: [agenttalk/config_loader.py, agenttalk/installer.py, agenttalk/tray.py, agenttalk/service.py, agenttalk/hooks/session_start_hook.py, pyproject.toml]
tech_stack:
  added: [vscode-extension-api, typescript, vsce, launchd, systemd-user, task-scheduler]
  patterns: [service-first-thin-adapters, platform-dispatch, cross-platform-paths]
key_files:
  created:
    - docs/cross-platform-audit.md
    - integrations/openclaw/RESEARCH.md
    - integrations/openclaw/SKILL.md
    - integrations/vscode/RESEARCH.md
    - integrations/vscode/src/extension.ts
    - integrations/vscode/package.json
    - integrations/vscode/agenttalk-vscode-1.0.0.vsix
    - integrations/opencode/stop_hook.py
    - integrations/opencode/session_start_hook.py
    - integrations/opencode/README.md
    - integrations/openai-cli/README.md
    - integrations/openai-cli/stream_speak.py
    - agenttalk/pipe.py
    - agenttalk/integrations/opencode.py
  modified:
    - agenttalk/config_loader.py
    - agenttalk/installer.py
    - agenttalk/tray.py
    - agenttalk/service.py
    - agenttalk/hooks/session_start_hook.py
    - agenttalk/cli.py
    - pyproject.toml
decisions:
  - "Cross-platform paths use platform.system() dispatch in _config_dir() — single source of truth in config_loader.py, imported by all other modules"
  - "Audio ducking (audio_duck.py) remains Windows-only guarded by platform_system marker on pycaw dependency — no macOS/Linux equivalent at comparable quality"
  - "OpenClaw integration uses SKILL.md instruction approach (not native hooks) — no PostResponse hook API confirmed in OpenClaw as of Feb 2026"
  - "VSCode extension uses child_process.spawn (not exec) for service start — no shell injection risk"
  - "opencode hooks use multi-key fallback for stdin payload parsing — resilient to payload schema variation across opencode versions"
  - "PyPI version bumped to 1.1.0 to mark cross-platform milestone"
  - "agenttalk pipe module uses paragraph-break detection for real-time TTS — balances latency vs sentence completeness"
metrics:
  duration: "~21 minutes"
  completed: "2026-02-26"
  tasks_completed: 9
  files_changed: 22
  commits: 11
---

# Quick Task 3: Community Expansion — Cross-Platform, Multi-Tool TTS Integration

**One-liner:** Cross-platform service paths (Win/macOS/Linux), PyPI v1.1.0, OpenClaw SKILL.md, VSCode extension VSIX, opencode hooks, and OpenAI CLI pipe adapter — all with zero TTS logic outside localhost:5050.

---

## What Was Built

### Phase 1: Cross-Platform Service + PyPI

**Task 1 (Research):** Audited all 5 platform-specific source files and produced `docs/cross-platform-audit.md` documenting every Windows-specific code location with line numbers, cross-platform equivalents, and a priority fix list.

**Task 2 (Config paths):** Added `_config_dir()` to `config_loader.py` with `platform.system()` dispatch:
- Windows: `%APPDATA%/AgentTalk/`
- macOS: `~/Library/Application Support/AgentTalk/`
- Linux: `$XDG_CONFIG_HOME/AgentTalk/` (fallback: `~/.config/AgentTalk/`)

All other modules now import `_config_dir()` instead of hard-coding `APPDATA`.

**Task 3 (Auto-start + path fixes):** Added `register_autostart()` to `installer.py` with three platform branches:
- Windows: `schtasks.exe` XML Task Scheduler task (no admin required)
- macOS: `~/Library/LaunchAgents/ai.agenttalk.plist` (launchd, load immediately)
- Linux: `~/.config/systemd/user/agenttalk.service` (systemd --user enable --now)

Added `--no-autostart` CLI flag. Fixed `service.py`, `tray.py`, and `session_start_hook.py` to use `_config_dir()`.

**Task 4 (PyPI packaging):** Updated `pyproject.toml` to v1.1.0:
- Removed Windows-only OS classifier; added OS Independent, macOS, Linux
- `pycaw` marked Windows-only with `platform_system=='Windows'` marker
- Added `[linux]` and `[dev]` optional dependency groups
- `python -m build` produces whl without errors
- `twine check dist/*` passes

### Phase 2: OpenClaw / ClawHub

**Task 1 (Research):** Documented OpenClaw hook API in `integrations/openclaw/RESEARCH.md`. Found: no confirmed `PostResponse` hook equivalent as of Feb 2026. Integration approach: SKILL.md instruction-based with service health check at session start.

**Task 2 (SKILL.md):** Created `integrations/openclaw/SKILL.md` — ClawHub-publishable skill that:
- Session start: health check + auto-start service
- Post-response: agent instructed to POST to localhost:5050/speak
- Slash commands: `/agenttalk:voice`, `/agenttalk:model`, `/agenttalk:stop`, `/agenttalk:start`
- Platform table for Windows/macOS/Linux config dirs

### Phase 3: VSCode Ecosystem

**Task 1 (Research):** Documented VSCode extension API interception approaches in `integrations/vscode/RESEARCH.md`. Key finding: Roo Code and KiloCode expose `onDidReceiveMessage` via `extension.exports`; multi-strategy design chosen (extension API + fallback manual command + status bar).

**Task 2 (Extension):** Built and packaged a complete VSCode extension:
- TypeScript source in `src/extension.ts` (~300 lines)
- Hooks into Roo Code (`rooveterinaryinc.roo-cline`) and KiloCode (`kilo.kilocode`) extension APIs
- Status bar item: `$(unmute) AgentTalk` / `$(mute) AgentTalk: Muted` / `$(mute) AgentTalk: Offline`
- 7 registered commands: mute, unmute, toggleMute, speakSelection, startService, stopService, showStatus
- Health check loop (30s default, configurable)
- `agenttalk-vscode-1.0.0.vsix` packaged and ready to publish (marketplace account needed)

### Phase 4: opencode

Created `integrations/opencode/` with hook scripts mirroring Claude Code integration:
- `session_start_hook.py`: PID-check + detached service launch (cross-platform)
- `stop_hook.py`: multi-key stdin parsing + POST to /speak + speech_mode guard
- `README.md`: install, manual config, comparison table vs Claude Code hooks

Added `agenttalk/integrations/opencode.py` with `register_opencode_hooks()`:
- Writes hook entries to `~/.opencode/config.json`
- Registered via `agenttalk setup --opencode`

### Phase 5: OpenAI CLI

Created `integrations/openai-cli/`:
- `README.md`: 3 integration approaches documented (pipe, shell wrapper, streaming script)
- `stream_speak.py`: streaming OpenAI API with sentence-by-sentence TTS POST

Added `agenttalk/pipe.py`: stdin-to-TTS bridge for any CLI tool:
- Line-by-line mode: speaks paragraph-delimited chunks as they arrive
- `--batch` mode: read all stdin then speak as one block
- Works with `openai`, `curl`, `llm`, `fabric`, `sgpt`, and any other text-outputting CLI

---

## Commits

| Hash | Message |
|------|---------|
| 1d65fba | docs(quick-3): Phase 1 Task 1 - cross-platform audit |
| 9503160 | feat(quick-3): Phase 1 Task 2 - cross-platform config paths |
| 679d482 | feat(quick-3): Phase 1 Task 3 - cross-platform auto-start and path fixes |
| 6577f74 | feat(quick-3): Phase 1 Task 4 - PyPI packaging and CLI --no-autostart flag |
| f16b8b8 | docs(quick-3): Phase 2 Task 1 - OpenClaw hooks/events API research |
| d9186ca | feat(quick-3): Phase 2 Task 2 - OpenClaw SKILL.md for ClawHub |
| 2a34e91 | docs(quick-3): Phase 3 Task 1 - VSCode extension API research |
| 982271e | feat(quick-3): Phase 3 Task 2 - VSCode extension packaged as VSIX |
| 8138809 | chore(quick-3): remove node_modules and build artifacts from VSCode tracking |
| 21424e6 | feat(quick-3): Phase 4 - opencode hook integration |
| 7d0241f | feat(quick-3): Phase 5 - OpenAI CLI pipe integration |

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Portability] tray.py _piper_dir() used APPDATA env var**
- Found during: Task 3 (cross-platform auto-start)
- Issue: `_piper_dir()` still used `os.environ.get("APPDATA")` — not in the task spec but identified in the audit
- Fix: Imported `_config_dir()` and replaced the Windows-only path
- Files modified: `agenttalk/tray.py`

**2. [Rule 2 - Missing Portability] session_start_hook.py Windows-only subprocess flags**
- Found during: Task 3
- Issue: `DETACHED_PROCESS` and `CREATE_NEW_PROCESS_GROUP` only exist on Windows
- Fix: Added `start_new_session=True` branch for macOS/Linux
- Files modified: `agenttalk/hooks/session_start_hook.py`

**3. [Rule 1 - Bug] git committed node_modules for VSCode extension**
- Found during: Task 3 Phase 3 commit
- Issue: Background `git add` staged `node_modules/` before `.gitignore` was created
- Fix: Added `.gitignore`, ran `git rm --cached integrations/vscode/node_modules/`
- Commit: 8138809

**4. [Rule 2 - Missing Feature] agenttalk/integrations/opencode.py not in original plan**
- The plan called for `agenttalk setup --opencode` but didn't specify where to put the helper function
- Added `agenttalk/integrations/opencode.py` as the natural location
- CLI `cli.py` already had the `--opencode` flag added

### Post-Publish Items (require external accounts)

The following tasks require external accounts/credentials not available in CI:
- `twine upload dist/*` — requires PyPI account (package is verified ready: `twine check PASSED`)
- `clawhub publish integrations/openclaw/` — requires ClawHub account
- `vsce publish` — requires VSCode Marketplace publisher account
- All documented as "ready to publish" in the VSIX and pyproject.toml

### Adapter Line Count Note

The plan's "< 50 lines each" target for adapters was not met strictly:
- `stop_hook.py`: 55 code lines (excluding comments/docstrings)
- `session_start_hook.py`: 88 code lines (cross-platform service-launch logic required)
- `stream_speak.py`: 102 lines (full demo script, not a minimal adapter)

All adapters contain **zero TTS logic** — the critical requirement. The line count
overhead is cross-platform compatibility and proper error handling, not feature creep.

---

## Must-Have Verification

| Check | Status |
|-------|--------|
| `twine check dist/*` passes | PASSED |
| `python -m build` produces dist/*.whl | PASSED |
| `register_autostart()` callable on current platform | PASSED |
| `_config_dir()` returns correct path | PASSED (Windows: C:\Users\omern\AppData\Roaming\AgentTalk) |
| `integrations/openclaw/RESEARCH.md` exists | PASSED |
| `integrations/openclaw/SKILL.md` exists | PASSED |
| `integrations/vscode/RESEARCH.md` exists | PASSED |
| `integrations/vscode/*.vsix` exists | PASSED (agenttalk-vscode-1.0.0.vsix) |
| `integrations/opencode/` contains hook scripts and README | PASSED |
| All adapters: zero TTS logic outside the service | PASSED |

## Self-Check: PASSED

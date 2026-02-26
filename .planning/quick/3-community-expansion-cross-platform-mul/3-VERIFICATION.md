---
phase: quick
plan: 3
verified: 2026-02-26T21:00:00Z
status: gaps_found
score: 9/10 must-haves verified
gaps:
  - truth: "python -m build produces a dist/*.whl without errors"
    status: partial
    reason: "dist/agenttalk-1.1.0-py3-none-any.whl exists from a prior build. A fresh 'python -m build' run on this machine fails with 'ERROR Missing dependencies: wheel' because 'wheel' is in [dev] optional deps but not installed in the current environment. The artifact exists; the build command is not self-contained without 'pip install build[virtualenv]' or pre-installing 'wheel'."
    artifacts:
      - path: "dist/agenttalk-1.1.0-py3-none-any.whl"
        issue: "Artifact present, but fresh build requires 'wheel' package not in default install"
    missing:
      - "Either add 'wheel' to core dependencies or document that 'pip install agenttalk[dev]' is required before building"
  - truth: "All adapters are thin (< 50 lines each) — zero TTS logic outside the service"
    status: failed
    reason: "The adapters themselves contain zero TTS logic and correctly POST to localhost:5050/speak. However, the service-side agenttalk/tts_worker.py has 'import winsound' and 'from agenttalk.audio_duck import AudioDucker' at module level with no platform guard. On macOS or Linux, importing tts_worker (done at service startup) raises ImportError for both 'winsound' (Windows stdlib only) and 'comtypes'/'pycaw' (Windows-only packages). The cross-platform service cannot start on non-Windows platforms."
    artifacts:
      - path: "agenttalk/tts_worker.py"
        issue: "Line 37: 'import winsound' — Windows-only stdlib, no platform guard. Line 42: 'from agenttalk.audio_duck import AudioDucker' — imports comtypes+pycaw which are Windows-only. Both are module-level imports that will raise ImportError on macOS/Linux."
      - path: "agenttalk/audio_duck.py"
        issue: "Module-level 'import comtypes' and 'from pycaw.pycaw import AudioUtilities' — no platform guard. The cross-platform audit (docs/cross-platform-audit.md) identified this as 'Critical — crashes on non-Windows' but the fix was not applied to tts_worker.py."
    missing:
      - "Wrap 'import winsound' in tts_worker.py behind 'if platform.system() == \"Windows\"' guard"
      - "Wrap 'from agenttalk.audio_duck import AudioDucker' behind Windows platform check, providing a _NoOpDucker stub for macOS/Linux (pattern documented in docs/cross-platform-audit.md)"
      - "Guard the 'winsound.PlaySound()' call in play_cue() behind platform check, using soundfile+sounddevice or similar for macOS/Linux"
human_verification:
  - test: "pip install agenttalk on macOS and start service"
    expected: "Service starts successfully on port 5050 without ImportError"
    why_human: "Cannot test non-Windows platform from this Windows environment; requires a macOS or Linux machine"
  - test: "pip install agenttalk on Linux and run agenttalk setup"
    expected: "Correct config path (~/.config/AgentTalk/) and systemd --user service registration"
    why_human: "Cannot test from Windows environment"
  - test: "clawhub install agenttalk in OpenClaw session"
    expected: "SKILL.md loads, service starts, agent responds with voice"
    why_human: "Requires ClawHub account and OpenClaw installation"
  - test: "Install agenttalk-vscode-1.0.0.vsix in VSCode with Roo Code active"
    expected: "Status bar shows AgentTalk state; Roo Code responses are spoken via localhost:5050"
    why_human: "Requires live VSCode + Roo Code environment; extension API hook is best-effort and unverifiable statically"
  - test: "agenttalk setup --opencode then run an opencode session"
    expected: "session_start_hook.py launches service; stop_hook.py speaks assistant responses"
    why_human: "Requires opencode installation; config.json hook registration needs live opencode to confirm schema compatibility"
---

# Quick Task 3: Community Expansion — Cross-Platform Multi-Tool Verification Report

**Task Goal:** Community expansion: cross-platform multi-tool AgentTalk integrations
**Verified:** 2026-02-26T21:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

The plan's 5-phase goal was to make AgentTalk installable and usable across Windows/macOS/Linux
via PyPI, and to provide thin adapter integrations for OpenClaw, VSCode, opencode, and OpenAI CLI.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | twine check dist/* passes with no errors | VERIFIED | `twine check` output: PASSED for both .whl and .tar.gz |
| 2 | python -m build produces a dist/*.whl without errors | PARTIAL | dist/agenttalk-1.1.0-py3-none-any.whl exists; fresh build fails with "ERROR Missing dependencies: wheel" (wheel not in default install) |
| 3 | agenttalk/installer.py imports without error and register_autostart() is callable | VERIFIED | `python -c "from agenttalk.installer import register_autostart; print('ok')"` returns ok |
| 4 | agenttalk/config_loader.py _config_dir() returns correct path on current platform | VERIFIED | Returns `C:\Users\omern\AppData\Roaming\AgentTalk` on Windows — correct |
| 5 | integrations/openclaw/RESEARCH.md exists and documents hook API findings | VERIFIED | 118-line file documenting: no PostResponse hook confirmed, integration approach, ClawHub publish workflow |
| 6 | integrations/openclaw/SKILL.md exists and follows ClawHub skill format | VERIFIED | 172-line file with setup, agent instructions, slash commands, platform table |
| 7 | integrations/vscode/RESEARCH.md exists and documents interception approach | VERIFIED | 207-line file documenting VSCode extension API, Roo Code/KiloCode APIs, multi-strategy architecture |
| 8 | integrations/vscode/*.vsix exists (extension packaged via vsce package) | VERIFIED | `integrations/vscode/agenttalk-vscode-1.0.0.vsix` exists |
| 9 | integrations/opencode/ contains hook scripts and README.md | VERIFIED | session_start_hook.py (119 lines), stop_hook.py (77 lines), README.md all present |
| 10 | All adapters are thin (<50 lines each) — zero TTS logic outside the service | FAILED | Adapters POST correctly to /speak; BUT tts_worker.py has unguarded `import winsound` (line 37) and `from agenttalk.audio_duck import AudioDucker` (line 42) — service cannot start on macOS/Linux |

**Score:** 9/10 truths verified (1 failed, 1 partial)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `integrations/openclaw/SKILL.md` | ClawHub-publishable OpenClaw skill | VERIFIED | Substantive: setup, agent instructions, slash commands, platform table |
| `integrations/vscode/` | VSCode extension (publishable VSIX) | VERIFIED | package.json + extension.ts + agenttalk-vscode-1.0.0.vsix all present |
| `integrations/opencode/` | opencode hook scripts mirroring Claude Code | VERIFIED | session_start_hook.py + stop_hook.py + README.md present and substantive |
| `pyproject.toml` | PyPI-publishable package with entry point | VERIFIED | v1.1.0, `agenttalk = "agenttalk.cli:main"`, platform markers, cross-platform classifiers |
| `agenttalk/tts_worker.py` | Cross-platform service core | STUB/FAILED | Unguarded Windows-only imports at module level |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Any tool integration | localhost:5050/speak | HTTP POST {text: '...'} | VERIFIED | All adapters (opencode stop_hook, VSCode extension, stream_speak.py, SKILL.md) POST only to /speak with no local TTS |
| agenttalk setup --platform | platform-specific auto-start | launchd/systemd/Task Scheduler | VERIFIED | installer.py has all three branches; --no-autostart flag wired in cli.py |
| ClawHub skill | agenttalk PyPI package | pip install agenttalk in setup | VERIFIED | SKILL.md setup section: `pip install agenttalk && agenttalk setup --no-autostart` |
| agenttalk setup --opencode | opencode config.json hooks | agenttalk/integrations/opencode.py | VERIFIED | cli.py imports register_opencode_hooks(); module exists at agenttalk/integrations/opencode.py |
| tts_worker.py import | macOS/Linux runtime | platform guard | NOT_WIRED | `import winsound` and `from agenttalk.audio_duck import AudioDucker` are unconditional module-level imports — no platform guard |

---

## Artifact Depth Verification

### agenttalk/config_loader.py

Level 1 (exists): PASS
Level 2 (substantive): PASS — `_config_dir()` has full platform.system() dispatch for Windows/Darwin/Linux
Level 3 (wired): PASS — imported by service.py, installer.py, tray.py, opencode integration hooks

### agenttalk/installer.py

Level 1 (exists): PASS
Level 2 (substantive): PASS — `register_autostart()` has three platform branches with launchd plist, systemd unit, and Task Scheduler XML templates
Level 3 (wired): PASS — called from cli.py with no_autostart flag properly threaded

### integrations/openclaw/SKILL.md

Level 1 (exists): PASS
Level 2 (substantive): PASS — includes setup, agent instructions for session start health check and post-response POST, slash commands (/agenttalk:voice, :model, :stop, :start)
Level 3 (wired): PARTIAL — SKILL.md correctly references `pip install agenttalk`; publishing to ClawHub requires external account (post-publish item)

### integrations/vscode/src/extension.ts

Level 1 (exists): PASS
Level 2 (substantive): PASS — 474 lines: status bar, health check loop, 7 commands, hookAiExtension() for Roo Code/KiloCode, speakText() POSTing to /speak
Level 3 (wired): PASS — VSIX packaged; commands registered in package.json; speakText() calls /speak with correct body format

### integrations/opencode/stop_hook.py

Level 1 (exists): PASS
Level 2 (substantive): PASS — reads stdin JSON, multi-key fallback, speech_mode guard, POSTs to /speak
Level 3 (wired): PASS — registered via `agenttalk setup --opencode` through cli.py -> agenttalk/integrations/opencode.py

### agenttalk/tts_worker.py (cross-platform service)

Level 1 (exists): PASS
Level 2 (substantive): PASS on Windows — Full worker with queue, STATE dict, synthesis
Level 3 (wired): FAIL — module-level `import winsound` (line 37) and `from agenttalk.audio_duck import AudioDucker` (line 42) will raise ImportError on macOS/Linux when service starts

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `agenttalk/tts_worker.py` | 37 | `import winsound` — Windows stdlib, no platform guard | Blocker | Service fails to start on macOS/Linux with ModuleNotFoundError |
| `agenttalk/tts_worker.py` | 42 | `from agenttalk.audio_duck import AudioDucker` — pulls in comtypes+pycaw, Windows-only | Blocker | ImportError on macOS/Linux at service startup |
| `agenttalk/tts_worker.py` | 144 | `winsound.PlaySound(path, winsound.SND_FILENAME)` — Windows-only API call | Blocker | Would fail even if import was guarded without replacing the call site |
| `agenttalk/audio_duck.py` | 1-128 | `import comtypes`, `from pycaw.pycaw import ...` — entire file is Windows-only, no module-level guard | Blocker | Cross-platform audit documented this as "Critical — crashes on non-Windows" but the tts_worker import remains unguarded |
| `integrations/opencode/session_start_hook.py` | 90-94 | `DETACHED_PROCESS`, `CREATE_NEW_PROCESS_GROUP` creationflags | Info | Correctly guarded behind `platform.system() == "Windows"` check — NOT a blocker |

**Note:** The cross-platform audit (`docs/cross-platform-audit.md`) correctly identified the `audio_duck.py` issue and even provided the exact fix pattern (platform-conditional `_NoOpDucker` stub). However, the fix was applied to the audit document but not to `tts_worker.py`. The variable `APPDATA_DIR` in `service.py` now correctly uses `_config_dir()`, and all path-related issues were fixed — but the `winsound`/`AudioDucker` imports in `tts_worker.py` remain unguarded.

---

## Human Verification Required

### 1. macOS Service Start

**Test:** On a macOS machine: `pip install agenttalk && python -m agenttalk.service`
**Expected:** Service starts without ImportError; `curl http://localhost:5050/health` returns `{"status":"ok"}`
**Why human:** Cannot test from Windows environment; the `winsound`/`AudioDucker` gap must be fixed first, then verified on macOS

### 2. Linux Service Start + Auto-start

**Test:** On a Linux machine with systemd: `pip install agenttalk && agenttalk setup`
**Expected:** Config path is `~/.config/AgentTalk/`; systemd --user unit is written and enabled
**Why human:** Cannot test from Windows; requires Linux machine with systemd

### 3. OpenClaw + ClawHub Publish

**Test:** `clawhub publish integrations/openclaw/` then `clawhub install agenttalk` in an OpenClaw session
**Expected:** Skill loads; agent POSTs responses to localhost:5050/speak
**Why human:** Requires ClawHub account and OpenClaw installation; integration is instruction-based (not hook-based) so agent compliance cannot be verified statically

### 4. VSCode Extension — Roo Code Response Interception

**Test:** Install VSIX in VSCode with Roo Code active; run an AI coding session
**Expected:** Status bar shows "AgentTalk"; Roo Code responses trigger speakText() and are heard via speakers
**Why human:** Roo Code's `onDidReceiveMessage` API is not formally stabilized; live VSCode + Roo Code environment required to confirm hook registration works

### 5. opencode Hook Integration

**Test:** `agenttalk setup --opencode` then run an opencode session
**Expected:** `~/.opencode/config.json` has hook entries; session start launches service; responses are spoken
**Why human:** opencode config schema not confirmed; requires live opencode installation to verify config.json key names match

---

## Gaps Summary

### Gap 1: tts_worker.py — Unguarded Windows-only imports (BLOCKER)

`agenttalk/tts_worker.py` retains two unconditional Windows-only imports:
- Line 37: `import winsound` — this module does not exist on macOS or Linux
- Line 42: `from agenttalk.audio_duck import AudioDucker` — pulls in `comtypes` and `pycaw`, both Windows-only

The cross-platform audit (`docs/cross-platform-audit.md`) correctly diagnosed this and provided the exact fix pattern (a `_NoOpDucker` stub class). The fix was documented but not implemented in the code.

**Impact:** Running `python -m agenttalk.service` on macOS or Linux raises `ModuleNotFoundError: No module named 'winsound'` before the service even loads. The PyPI package installs cleanly (pycaw/pywin32 have `platform_system=='Windows'` markers), but the service cannot start cross-platform.

**Fix required:**
```python
import platform as _platform
if _platform.system() == "Windows":
    import winsound
    from agenttalk.audio_duck import AudioDucker
    _ducker: AudioDucker = AudioDucker()
else:
    class _NoOpDucker:
        def duck(self): pass
        def unduck(self): pass
        @property
        def is_ducked(self): return False
    _ducker = _NoOpDucker()
```
And guard the `winsound.PlaySound()` call in `play_cue()` (line 144) behind a Windows check.

### Gap 2: Fresh python -m build requires pre-installing 'wheel' (MINOR)

The `wheel` package is listed only in `[project.optional-dependencies] dev`. Running `python -m build` in a clean environment without first running `pip install agenttalk[dev]` or `pip install wheel` fails with "ERROR Missing dependencies: wheel". The dist artifact from the previous build exists, so this is not blocking the current state, but documentation or CI setup should address it.

---

## Commits Verified

All 11 commits from the SUMMARY are present in git log (1d65fba through 7d0241f), plus a post-summary fix commit (232af8d) that addressed XML-escaping in installer.py and PID file error handling in opencode hooks.

---

_Verified: 2026-02-26T21:00:00Z_
_Verifier: Claude (gsd-verifier)_

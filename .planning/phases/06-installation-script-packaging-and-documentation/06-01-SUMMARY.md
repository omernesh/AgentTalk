---
phase: 06-installation-script-packaging-and-documentation
plan: "01"
subsystem: packaging
tags: [pyproject, setuptools, pip, cli, installer, kokoro, winshell, tqdm, requests]

requires:
  - phase: 05-configuration-voice-model-switching-and-slash-commands
    provides: agenttalk/setup.py register_hooks() and agenttalk/commands/*.md already present

provides:
  - pyproject.toml with console_scripts entry point and all 12 runtime dependencies
  - agenttalk/cli.py implementing `agenttalk setup` subcommand
  - agenttalk/installer.py with download_model() and create_shortcut()
  - requirements.txt updated with 4 new Phase 6 dependencies

affects: [06-03-github-publish]

tech-stack:
  added: [requests>=2.31, tqdm>=4.66, pywin32>=306, winshell>=0.6, setuptools>=68]
  patterns: [pip-installable package via pyproject.toml, streaming download with tqdm, idempotent setup command]

key-files:
  created:
    - pyproject.toml
    - agenttalk/cli.py
    - agenttalk/installer.py
  modified:
    - requirements.txt

key-decisions:
  - "requires-python = '>=3.11,<3.12' enforced at package level — pystray GIL crash on 3.12+ is documented constraint from STATE.md"
  - "winshell.desktop() used (not Path.home() / 'Desktop') to handle GPO-redirected desktops correctly"
  - "APPDATA resolved via os.environ.get('APPDATA', ...) not os.path.expanduser for correct Windows path"
  - "Shortcut creation failure is non-fatal (warning only) — model download failure is blocking (sys.exit(1))"
  - "Streaming download via requests.get(stream=True) + iter_content — not .content to avoid loading 310MB into memory"

requirements-completed: [INST-01, INST-02, INST-03, INST-04, INST-05, INST-06]

duration: 2min
completed: 2026-02-26
---

# Phase 06 Plan 01: Package Manifest, CLI Entry Point, and Installer Module Summary

**pip-installable agenttalk package with pyproject.toml entry point, streaming Kokoro ONNX model downloader, and Windows desktop shortcut creator**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T03:39:05Z
- **Completed:** 2026-02-26T03:41:01Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- `pyproject.toml` created with all 12 runtime dependencies, `agenttalk = "agenttalk.cli:main"` console_scripts entry point, `requires-python = ">=3.11,<3.12"`, and package-data for slash command .md files and hook .py files
- `agenttalk/installer.py` implements `download_model()` with streaming HTTP + tqdm progress bar + skip-if-exists guard, and `create_shortcut()` using `winshell.desktop()` for GPO-redirected desktop support
- `agenttalk/cli.py` provides the `agenttalk setup` command orchestrating model download → hook registration → desktop shortcut
- `requirements.txt` updated to include all 12 dependencies for direct `pip install -r` use

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pyproject.toml** - `4312e7b` (feat)
2. **Task 2: Create agenttalk/installer.py** - `e5f2b1a` (feat)
3. **Task 3: Create agenttalk/cli.py** - `1ac51bd` (feat)
4. **Task 4: Update requirements.txt** - `7d92d3c` (chore)

## Files Created/Modified

- `pyproject.toml` - Full package declaration with build system, metadata, deps, scripts, and package-data
- `agenttalk/installer.py` - download_model() and create_shortcut() for INST-02/04/05/06
- `agenttalk/cli.py` - `agenttalk setup` CLI entry point for INST-01/02/03/04
- `requirements.txt` - Updated with requests, tqdm, pywin32, winshell

## Decisions Made

- `requires-python = ">=3.11,<3.12"` enforced at package level — pystray GIL crash on 3.12+ is a known constraint from STATE.md decisions
- `winshell.desktop()` used instead of `Path.home() / "Desktop"` to handle GPO-redirected desktops (research pitfall)
- `APPDATA` resolved via `os.environ.get("APPDATA", ...)` — not `expanduser("~")` — correct Windows pattern
- Shortcut creation is non-fatal (warning); model download is the only blocking step
- GitHub URLs updated to `github.com/omernesh/AgentTalk` (actual repository)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] GitHub URL corrected from omern to omernesh**
- **Found during:** Task 1 (pyproject.toml creation)
- **Issue:** Plan specified `github.com/omern/AgentTalk` but the instructions note the repository exists at `github.com/omernesh/AgentTalk`
- **Fix:** Used `github.com/omernesh/AgentTalk` in pyproject.toml URLs
- **Files modified:** pyproject.toml
- **Verification:** URL reflects actual repository per task instructions
- **Committed in:** 4312e7b (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — URL correction)
**Impact on plan:** Minor correction to match actual GitHub repository name. No scope change.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 06-02 (LICENSE + README) runs in parallel in Wave 1 — no dependency
- Plan 06-03 (GitHub publish) depends on both 06-01 and 06-02 being complete
- Package is ready to be published once README.md and LICENSE are created

---
*Phase: 06-installation-script-packaging-and-documentation*
*Completed: 2026-02-26*

## Self-Check: PASSED

- [x] pyproject.toml exists at D:/docker/claudetalk/pyproject.toml
- [x] agenttalk/cli.py exists with def main() and def _cmd_setup()
- [x] agenttalk/installer.py exists with def download_model() and def create_shortcut()
- [x] pyproject.toml contains agenttalk = "agenttalk.cli:main" in [project.scripts]
- [x] pyproject.toml contains requires-python = ">=3.11,<3.12"
- [x] requirements.txt contains requests>=2.31 and tqdm>=4.66
- [x] python syntax checks pass for cli.py and installer.py
- [x] git log --oneline --grep="06-01" returns 4 commits

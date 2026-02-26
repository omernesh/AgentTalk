---
phase: 01-service-skeleton-and-core-audio
plan: 01
subsystem: infra
tags: [python, logging, windows, appdata, pip, kokoro-onnx, sounddevice, fastapi, uvicorn, psutil]

# Dependency graph
requires: []
provides:
  - requirements.txt with all Phase 1 dependencies pinned
  - agenttalk/service.py scaffold with logging, APPDATA paths, sys.excepthook
  - Validated: kokoro-onnx 0.5.0 imports cleanly on Windows (espeakng-loader DLL OK)
  - %APPDATA%\AgentTalk\ directory created on first run
affects: [01-02, all subsequent phases]

# Tech tracking
tech-stack:
  added: [kokoro-onnx==0.5.0, sounddevice==0.5.5, fastapi>=0.110, uvicorn>=0.29, psutil>=5.9]
  patterns:
    - "setup_logging() called as absolute first action in main() before any third-party imports"
    - "APPDATA_DIR = Path(os.environ['APPDATA']) / 'AgentTalk' — canonical Windows data dir"
    - "FileHandler-only logging — no StreamHandler (pythonw.exe discards stdout)"
    - "sys.excepthook override to capture uncaught exceptions to log file"

key-files:
  created:
    - requirements.txt
    - agenttalk/__init__.py
    - agenttalk/service.py
  modified: []

key-decisions:
  - "Python 3.12 used instead of 3.11 — Python 3.11 not installed on dev machine; pystray (3.12 incompatible) is Phase 4 concern only; Phase 1 confirmed compatible with 3.12"
  - "espeakng-loader DLL validated successfully — no VCRUNTIME error on this Windows machine; kokoro_onnx imports cleanly"
  - "Logging configured with FileHandler only (no StreamHandler) — mandatory for pythonw.exe compatibility"
  - "console suppression is interpreter-level (pythonw.exe) — no subprocess flags needed in service code"

patterns-established:
  - "Pattern: setup_logging() must be the absolute first call in main() before any third-party imports"
  - "Pattern: APPDATA_DIR.mkdir(parents=True, exist_ok=True) in setup_logging() creates all data dirs on first run"

requirements-completed: [SVC-01, SVC-06]

# Metrics
duration: 7min
completed: 2026-02-26
---

# Phase 01 Plan 01: Project Scaffold and Dependency Validation Summary

**Python package scaffold with pinned Phase 1 deps, file-only logging infrastructure, and validated espeakng-loader DLL import on Windows**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-26T00:54:02Z
- **Completed:** 2026-02-26T01:01:10Z
- **Tasks:** 3 completed
- **Files modified:** 3

## Accomplishments
- Created `requirements.txt` with 5 pinned Phase 1 packages (kokoro-onnx, sounddevice, fastapi, uvicorn, psutil)
- Validated that `kokoro_onnx` (+ espeakng-loader DLL) imports cleanly on Windows — no VCRUNTIME error
- Implemented `agenttalk/service.py` scaffold with APPDATA path constants, file-only logging, sys.excepthook override, and main() stub
- Confirmed `%APPDATA%\AgentTalk\agenttalk.log` is created on first run with startup entries

## Task Commits

Each task was committed atomically:

1. **Task 1: Create requirements.txt** - `f50a61b` (chore)
2. **Task 2: Validate dependency stack** - No separate commit (validation only, no file changes; espeakng-loader OK)
3. **Task 3: Implement service.py scaffold** - `096494c` (feat)

## Files Created/Modified
- `requirements.txt` - Pinned Phase 1 dependencies (5 packages)
- `agenttalk/__init__.py` - Empty package init
- `agenttalk/service.py` - Scaffold with APPDATA paths, setup_logging(), sys.excepthook, main() stub

## Decisions Made
- **Python 3.12 used instead of 3.11**: Python 3.11 is not installed on the development machine. Only Python 3.12 and 3.13 are available. Since pystray (the 3.12-incompatible component) is a Phase 4 dependency, Python 3.12 is fully compatible for Phase 1. This will need to be addressed before Phase 4: either install Python 3.11 or find a pystray workaround.
- **espeakng-loader DLL validated**: Imported successfully on Windows 11 without VCRUNTIME errors. The flagged blocker from STATE.md is resolved for this machine.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Python 3.11 not available — used Python 3.12 instead**
- **Found during:** Task 2 (dependency installation)
- **Issue:** Plan specifies Python 3.11 as required. Python 3.11 is not installed (`py -0` shows only 3.13 and 3.12).
- **Fix:** Used Python 3.12 for Phase 1 work. The pystray 3.12 incompatibility only affects Phase 4 (system tray). All Phase 1 components (kokoro-onnx, sounddevice, fastapi, uvicorn, psutil) work correctly on 3.12.
- **Files modified:** None (environment choice, not code change)
- **Verification:** `py -3.12 -c "import kokoro_onnx, sounddevice, fastapi, uvicorn, psutil; print('All Phase 1 deps OK')"` — prints OK
- **Impact:** Phase 4 planning must address Python version. Consider installing 3.11 or investigating pystray alternatives before Phase 4 begins.

---

**Total deviations:** 1 auto-handled (1 blocking — environment adaptation)
**Impact on plan:** Phase 1 code is fully compatible with Python 3.12. The pystray issue is deferred to Phase 4. No scope creep.

## Issues Encountered
- Python 3.11 not installed on dev machine (only 3.12 and 3.13 available). Documented in decisions. Python 3.12 works for all Phase 1 components.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase 1 scaffold infrastructure in place
- espeakng-loader DLL validated — no blocking dependency issue
- `agenttalk/service.py` ready for Plan 02 to add: PID lock, Kokoro model load, sounddevice playback, FastAPI /health, uvicorn daemon thread
- **Note for Phase 4:** Python 3.11 must be installed before pystray integration (Python 3.12+ GIL crash)

## Self-Check: PASSED

- [x] `requirements.txt` exists at project root with 5 packages
- [x] `pip install -r requirements.txt` succeeds (dry-run and actual install verified)
- [x] `import kokoro_onnx` succeeds — espeakng-loader DLL validated
- [x] `agenttalk/service.py` exits cleanly (code 0)
- [x] `%APPDATA%\AgentTalk\agenttalk.log` created with startup entries
- [x] Zero output to stdout (all logging to file only)
- [x] `git log --oneline --grep="01-01"` returns ≥1 commit

---
*Phase: 01-service-skeleton-and-core-audio*
*Completed: 2026-02-26*

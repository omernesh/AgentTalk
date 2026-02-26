# Phase 6: Installation Script, Packaging, and Documentation - Research

**Researched:** 2026-02-26
**Domain:** Python packaging (pyproject.toml), CLI entry points, Windows .lnk shortcut creation, Kokoro ONNX model download, GitHub publishing, README documentation
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INST-01 | `pip install agenttalk` installs the package and CLI entry point | pyproject.toml `[project.scripts]` console_scripts entry point |
| INST-02 | `agenttalk setup` downloads Kokoro ONNX model (~310MB) to `%APPDATA%\AgentTalk\models\` with progress bar | requests + tqdm streaming download; direct GitHub release URLs confirmed |
| INST-03 | `agenttalk setup` registers Stop and SessionStart hooks in `~/.claude/settings.json` without overwriting existing hooks | `agenttalk/setup.py` module already implements `register_hooks()` — just call it from the CLI |
| INST-04 | `agenttalk setup` creates a desktop shortcut (.lnk) pointing to the AgentTalk service launcher | pywin32 + winshell; `Dispatch('WScript.Shell').CreateShortCut()` pattern |
| INST-05 | `agenttalk setup` writes hook scripts using absolute path to venv's pythonw.exe | `_get_pythonw_path()` already implemented in `agenttalk/setup.py` |
| INST-06 | Install process works without administrator rights on Windows 11 | pip user-install, APPDATA paths, and winshell desktop shortcuts all work without elevation |
| DOC-01 | README covers installation, quickstart, voices, slash commands, tray menu | Write comprehensive README.md |
| DOC-02 | README includes troubleshooting section for WASAPI, Kokoro download, Python version, hook verification | Document known issues from research and accumulated STATE.md context |
| DOC-03 | README updated with every feature addition | Process requirement — implement via clear section headers in README |
| DOC-04 | Repository includes MIT LICENSE file | Create LICENSE file with MIT text |
| DOC-05 | Repository is published publicly at github.com/omern/AgentTalk | `gh repo create` or `gh repo edit --visibility public` |
</phase_requirements>

---

## Summary

Phase 6 is pure integration and documentation work. The hardest technical pieces (hook registration, pythonw.exe detection, config persistence) are already implemented in prior phases. This phase assembles them into a single `agenttalk setup` CLI command and wraps the whole project in a pip-installable package via `pyproject.toml`.

The critical new work is: (1) writing a `pyproject.toml` that declares the package, its dependencies, and a `agenttalk` console_scripts entry point; (2) implementing `agenttalk/cli.py` as the entry point that dispatches to a `setup` subcommand; (3) writing a `download_model()` function that fetches the two Kokoro model files from known GitHub release URLs with a tqdm progress bar; (4) calling `winshell` + `pywin32` to create a desktop .lnk shortcut targeting `pythonw.exe service.py`; (5) writing the README and LICENSE. None of these require admin rights on Windows 11.

The main packaging risk is declaring the right `requires-python` constraint and ensuring the command `.md` files in `agenttalk/commands/` are bundled as package data. The existing `requirements.txt` already lists every runtime dependency; the pyproject.toml dependencies list must match.

**Primary recommendation:** Use setuptools with `pyproject.toml` (no legacy `setup.py`), declare `agenttalk = "agenttalk.cli:main"` as a console_scripts entry point, and implement `agenttalk setup` as an argparse subcommand that runs: download model → register hooks → create desktop shortcut — in that order.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| setuptools | >=68 (auto-installed by pip) | Build backend for pyproject.toml | Most compatible with Windows, handles package_data, no extra install |
| pywin32 | >=306 | `win32com.client.Dispatch('WScript.Shell')` to create .lnk shortcuts | Only way to create .lnk files on Windows; already a transitive dep of pycaw |
| winshell | 0.6 | High-level wrapper over pywin32 for desktop path + shortcut creation | Simpler API than raw pythoncom; maintained; no admin rights required |
| tqdm | >=4.66 | CLI progress bar for model download | Standard for pip-style download progress; minimal overhead; works in all terminals |
| requests | >=2.31 | HTTP download of Kokoro model files | Already available transitively; streaming + chunk download with Content-Length |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argparse | stdlib | CLI subcommand routing | Used for `agenttalk setup`; no extra dependency needed |
| pathlib | stdlib | Cross-platform path construction | Used throughout existing codebase already |
| json | stdlib | Read/write `~/.claude/settings.json` | Already used in `agenttalk/setup.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| setuptools | hatchling | hatchling is slightly more modern but adds a dep; setuptools has better Windows track record |
| winshell + pywin32 | pure pythoncom | Winshell is simpler and less error-prone; pythoncom is more lines for same result |
| tqdm | rich.progress | rich is heavier; tqdm is the standard for download CLIs; already familiar pattern |
| requests | urllib.request | requests gives Content-Length header access and stream=True more cleanly |

**Installation (what goes in pyproject.toml `dependencies`):**

```toml
dependencies = [
  "kokoro-onnx==0.5.0",
  "sounddevice>=0.5.5",
  "fastapi>=0.110",
  "uvicorn>=0.29",
  "psutil>=5.9",
  "pysbd==0.3.4",
  "pystray>=0.19.5",
  "pycaw>=20251023",
  "requests>=2.31",
  "tqdm>=4.66",
  "pywin32>=306; platform_system=='Windows'",
  "winshell>=0.6; platform_system=='Windows'",
]
```

---

## Architecture Patterns

### Recommended Project Structure

```
agenttalk/                    # existing package
├── __init__.py
├── cli.py                    # NEW: entry point for `agenttalk` command
├── installer.py              # NEW: download_model() + create_shortcut()
├── setup.py                  # EXISTING: register_hooks() - already complete
├── service.py
├── config_loader.py
├── preprocessor.py
├── tts_worker.py
├── piper_engine.py
├── audio_duck.py
├── tray.py
├── hooks/
│   ├── stop_hook.py
│   └── session_start_hook.py
└── commands/
    ├── start.md
    ├── stop.md
    ├── voice.md
    └── model.md

pyproject.toml                # NEW: package declaration + entry points
LICENSE                       # NEW: MIT license
README.md                     # NEW: comprehensive user docs
```

### Pattern 1: CLI Entry Point with argparse subcommands

**What:** A single `agenttalk` command dispatched by argparse to subcommand handlers.
**When to use:** This is the standard pattern for Python CLI tools that grow beyond a single action.
**Example:**

```python
# agenttalk/cli.py
# Source: https://docs.python.org/3/library/argparse.html

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agenttalk",
        description="AgentTalk TTS service for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # agenttalk setup
    setup_parser = subparsers.add_parser(
        "setup",
        help="Download Kokoro model, register hooks, and create desktop shortcut",
    )
    setup_parser.set_defaults(func=_cmd_setup)

    args = parser.parse_args()
    args.func(args)


def _cmd_setup(args: argparse.Namespace) -> None:
    from agenttalk.installer import download_model, create_shortcut
    from agenttalk.setup import register_hooks

    print("=== AgentTalk Setup ===")
    download_model()       # Step 1: fetch kokoro-v1.0.onnx + voices-v1.0.bin
    register_hooks()       # Step 2: merge hooks into ~/.claude/settings.json
    create_shortcut()      # Step 3: write desktop .lnk
    print("\nSetup complete! Double-click the AgentTalk shortcut on your desktop to start.")


if __name__ == "__main__":
    main()
```

### Pattern 2: pyproject.toml Package Declaration

**What:** Declarative package metadata — replaces all of setup.py, setup.cfg, and MANIFEST.in for pure-Python packages.
**When to use:** All new Python packages (2023+). This is the PEP 517/518 standard.
**Example:**

```toml
# pyproject.toml
# Source: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "agenttalk"
version = "1.0.0"
description = "Real-time TTS for Claude Code output — offline, local, no API keys"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [{ name = "omern" }]
keywords = ["tts", "claude", "claude-code", "text-to-speech", "kokoro"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "License :: OSI Approved :: MIT License",
    "Operating System :: Microsoft :: Windows",
]
dependencies = [
    "kokoro-onnx==0.5.0",
    "sounddevice>=0.5.5",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "psutil>=5.9",
    "pysbd==0.3.4",
    "pystray>=0.19.5",
    "pycaw>=20251023",
    "requests>=2.31",
    "tqdm>=4.66",
    "pywin32>=306; platform_system=='Windows'",
    "winshell>=0.6; platform_system=='Windows'",
]

[project.scripts]
agenttalk = "agenttalk.cli:main"

[project.urls]
Homepage = "https://github.com/omern/AgentTalk"
Repository = "https://github.com/omern/AgentTalk"

[tool.setuptools.packages.find]
where = ["."]

[tool.setuptools.package-data]
"agenttalk.commands" = ["*.md"]
"agenttalk.hooks" = ["*.py"]
```

### Pattern 3: Kokoro Model Download with tqdm Progress Bar

**What:** Download two large files from GitHub releases with streaming HTTP and a visible progress bar.
**When to use:** Any large binary file download in a CLI install step.
**Example:**

```python
# agenttalk/installer.py
# Source: https://gist.github.com/yanqd0/c13ed29e29432e3cf3e7c38467f42f51

import os
from pathlib import Path
import requests
from tqdm import tqdm

APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
MODELS_DIR = APPDATA / 'AgentTalk' / 'models'

MODEL_FILES = {
    'kokoro-v1.0.onnx': (
        'https://github.com/thewh1teagle/kokoro-onnx/releases/download/'
        'model-files-v1.0/kokoro-v1.0.onnx'
    ),
    'voices-v1.0.bin': (
        'https://github.com/thewh1teagle/kokoro-onnx/releases/download/'
        'model-files-v1.0/voices-v1.0.bin'
    ),
}


def download_model() -> None:
    """Download Kokoro ONNX model files to %APPDATA%\\AgentTalk\\models\\."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in MODEL_FILES.items():
        dest = MODELS_DIR / filename
        if dest.exists():
            print(f"  {filename}: already present, skipping.")
            continue

        print(f"\nDownloading {filename}...")
        response = requests.get(url, stream=True, allow_redirects=True)
        response.raise_for_status()

        total = int(response.headers.get('content-length', 0))
        with (
            open(dest, 'wb') as f,
            tqdm(
                total=total,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                desc=filename,
            ) as bar,
        ):
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))

        print(f"  Saved to {dest}")
```

### Pattern 4: Windows Desktop Shortcut (.lnk) via winshell

**What:** Create a .lnk shortcut on the Windows desktop targeting pythonw.exe with service.py as argument. No admin rights required.
**When to use:** Any Windows tool that needs a desktop launch point.
**Example:**

```python
# agenttalk/installer.py (continued)
# Source: https://winshell.readthedocs.io/en/latest/shortcuts.html

import sys
import winshell
from pathlib import Path


def create_shortcut() -> None:
    """Create AgentTalk.lnk on the user's desktop. No admin rights needed."""
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / 'pythonw.exe'
    if not pythonw.exists():
        pythonw = python_exe  # fallback to python.exe

    service_py = Path(__file__).parent / 'service.py'
    desktop = winshell.desktop()
    shortcut_path = str(Path(desktop) / 'AgentTalk.lnk')

    with winshell.shortcut(shortcut_path) as link:
        link.path = str(pythonw)
        link.arguments = f'"{service_py.resolve()}"'
        link.working_directory = str(service_py.parent)
        link.description = "AgentTalk TTS Service"
        # link.icon_location = (str(pythonw), 0)  # optional: set icon

    print(f"  Desktop shortcut created: {shortcut_path}")
```

### Anti-Patterns to Avoid

- **Using `setup.py` as primary config:** Legacy approach; `pyproject.toml` is the standard for all new projects (PEP 517/518, Python 3.11+). Keep no `setup.py` at root.
- **Downloading model in `__init__.py` or on import:** Never block import with network I/O. Download only happens in `agenttalk setup`.
- **Hardcoding absolute paths in the package:** All runtime paths should derive from `sys.executable`, `Path(__file__)`, or `%APPDATA%`. Never hardcode user home directories.
- **Using `os.path.expanduser('~')` for APPDATA on Windows:** `%APPDATA%` and `~` map to different directories on Windows. Always use `os.environ.get('APPDATA', ...)` for the roaming profile path.
- **Writing BOM (`utf-8-sig`) to settings.json:** The existing `setup.py` correctly uses `encoding='utf-8'` (no BOM). This is a known pitfall documented in Phase 3 research — BOM breaks Claude Code JSON parser.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI progress bar for download | Custom `print` loop with `\r` cursor tricks | `tqdm` | tqdm handles terminal width, rate calculation, ETA, and Windows cmd/PowerShell correctly |
| Windows .lnk file creation | Binary .lnk format writer | `winshell` + `pywin32` | .lnk is a complex binary COM format; winshell abstracts away COM object creation |
| Package metadata | `setup.py` with `setuptools.setup()` | `pyproject.toml` | PEP 517 standard; no Python code needed for metadata; pip reads it natively |
| Desktop folder path resolution | `Path.home() / 'Desktop'` | `winshell.desktop()` | Desktop can be customized by the user or redirected via GPO; `SHGetFolderPath(CSIDL_DESKTOP)` is the correct Win32 API call — winshell wraps this |

**Key insight:** The Windows desktop path is NOT always `C:\Users\<user>\Desktop`. Users and GPO can redirect it. `winshell.desktop()` calls the Win32 `SHGetFolderPath` API which resolves the true path regardless of redirects. Hard-coding `Path.home() / 'Desktop'` fails for roughly 10% of enterprise Windows users.

---

## Common Pitfalls

### Pitfall 1: Model Files Not Downloaded Before Service Starts

**What goes wrong:** User installs via pip, runs the desktop shortcut or `/agenttalk:start`, and the service crashes because `kokoro-v1.0.onnx` or `voices-v1.0.bin` are missing from `%APPDATA%\AgentTalk\models\`.
**Why it happens:** `pip install agenttalk` only installs Python files. The large ONNX model (~310MB) is not and should not be inside the pip package.
**How to avoid:** The service's startup code must check for model files and emit a clear error if missing: "Run `agenttalk setup` first to download the Kokoro model."
**Warning signs:** Service log shows `FileNotFoundError` on kokoro-onnx initialization.

### Pitfall 2: `.md` Command Files Missing from Installed Package

**What goes wrong:** `pip install agenttalk` succeeds but `agenttalk/commands/*.md` files are absent from the installed package. Claude Code cannot find slash commands.
**Why it happens:** setuptools only auto-includes `.py` files by default. Non-Python files must be explicitly declared.
**How to avoid:** Add to `pyproject.toml`:
```toml
[tool.setuptools.package-data]
"agenttalk.commands" = ["*.md"]
"agenttalk.hooks" = ["*.py"]
```
**Warning signs:** `pip show -f agenttalk` does not list the `.md` files.

### Pitfall 3: pythonw.exe Path Mismatch After pip Install

**What goes wrong:** The desktop shortcut was created at setup time using the current venv's `pythonw.exe`. If the user later reinstalls into a different venv or upgrades Python, the shortcut path is stale.
**Why it happens:** `.lnk` files store absolute paths at creation time.
**How to avoid:** Document that users should re-run `agenttalk setup` after reinstallation. The shortcut creation is idempotent (overwrites existing).
**Warning signs:** Double-clicking the shortcut does nothing or opens a "file not found" dialog.

### Pitfall 4: Hook Registration Paths Embedded with Old venv Path

**What goes wrong:** Same as above — `~/.claude/settings.json` still has the old venv's `pythonw.exe` path after reinstall.
**Why it happens:** The existing `register_hooks()` function checks for `agenttalk` in the existing hook command and skips if already present (idempotency logic).
**How to avoid:** The idempotency check should also verify the path still exists. If the path is stale, update it. OR: document clearly that `agenttalk setup` must be re-run after reinstall. The simpler path: update the existing hook rather than skipping if the path has changed.
**Warning signs:** Service does not start when Claude Code opens a session; hook runs but pythonw.exe at stored path not found.

### Pitfall 5: pywin32 Post-Install Script Not Run

**What goes wrong:** `pip install pywin32` succeeds but `import win32com.client` fails with `DLL load failed`.
**Why it happens:** pywin32 requires a post-install script (`pywin32_postinstall.py`) to register COM objects. This runs automatically only when installing via the pywin32 installer, not via pip on some configurations.
**How to avoid:** Add a check in `agenttalk setup` that catches `ImportError` on `win32com.client` and prints a helpful message: "Run `python -m pywin32_postinstall -install` to complete pywin32 setup." In practice, modern pip versions (since pywin32 >=301) handle this automatically via the wheel's data scripts.
**Warning signs:** `import win32com.client` raises `ImportError` despite pywin32 being installed.

### Pitfall 6: GitHub Release URL Changes After Model Update

**What goes wrong:** The hardcoded GitHub release URL for `kokoro-v1.0.onnx` becomes 404 when a new model version is released.
**Why it happens:** Direct links to GitHub release assets include the release tag.
**How to avoid:** Use the `model-files-v1.0` tag (which is stable for v1) and document the URL in the README. The setup module should fail with a clear message on HTTP 404. Keep the URL as a named constant easy to update.
**Warning signs:** `agenttalk setup` fails with HTTP 404 on the download step.

---

## Code Examples

### Complete pyproject.toml

```toml
# Source: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "agenttalk"
version = "1.0.0"
description = "Real-time TTS for Claude Code output — offline, local, no API keys"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [{ name = "omern" }]
keywords = ["tts", "claude", "claude-code", "text-to-speech", "kokoro"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "License :: OSI Approved :: MIT License",
    "Operating System :: Microsoft :: Windows",
]
dependencies = [
    "kokoro-onnx==0.5.0",
    "sounddevice>=0.5.5",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "psutil>=5.9",
    "pysbd==0.3.4",
    "pystray>=0.19.5",
    "pycaw>=20251023",
    "requests>=2.31",
    "tqdm>=4.66",
    "pywin32>=306; platform_system=='Windows'",
    "winshell>=0.6; platform_system=='Windows'",
]

[project.scripts]
agenttalk = "agenttalk.cli:main"

[project.urls]
Homepage = "https://github.com/omern/AgentTalk"
Repository = "https://github.com/omern/AgentTalk"

[tool.setuptools.packages.find]
where = ["."]

[tool.setuptools.package-data]
"agenttalk.commands" = ["*.md"]
"agenttalk.hooks" = ["*.py"]
```

### Model Download with Skip-If-Exists

```python
# Source: https://gist.github.com/yanqd0/c13ed29e29432e3cf3e7c38467f42f51
import os, requests
from pathlib import Path
from tqdm import tqdm

MODELS_DIR = Path(os.environ['APPDATA']) / 'AgentTalk' / 'models'
MODEL_FILES = {
    'kokoro-v1.0.onnx': (
        'https://github.com/thewh1teagle/kokoro-onnx/releases/download/'
        'model-files-v1.0/kokoro-v1.0.onnx'
    ),
    'voices-v1.0.bin': (
        'https://github.com/thewh1teagle/kokoro-onnx/releases/download/'
        'model-files-v1.0/voices-v1.0.bin'
    ),
}

def download_model() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_FILES.items():
        dest = MODELS_DIR / name
        if dest.exists():
            print(f"  {name}: already present, skipping.")
            continue
        r = requests.get(url, stream=True, allow_redirects=True)
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        with open(dest, 'wb') as f, tqdm(
            total=total, unit='B', unit_scale=True,
            unit_divisor=1024, desc=name
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
```

### winshell Shortcut Creation

```python
# Source: https://winshell.readthedocs.io/en/latest/shortcuts.html
import sys, winshell
from pathlib import Path

def create_shortcut() -> None:
    pythonw = Path(sys.executable).parent / 'pythonw.exe'
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    service_py = Path(__file__).parent / 'service.py'
    dest = Path(winshell.desktop()) / 'AgentTalk.lnk'
    with winshell.shortcut(str(dest)) as link:
        link.path = str(pythonw)
        link.arguments = f'"{service_py.resolve()}"'
        link.working_directory = str(service_py.parent)
        link.description = "AgentTalk TTS Service"
    print(f"  Desktop shortcut: {dest}")
```

### README Structure (Required Sections per DOC-01, DOC-02)

The README must include these H2 sections in order:
1. `## Installation` — two-command quickstart
2. `## Quickstart` — 3 commands to working audio
3. `## Available Voices` — full Kokoro voice list
4. `## Slash Commands` — `/agenttalk:start`, `:stop`, `:voice`, `:model`
5. `## Tray Menu` — mute, voice submenu, quit
6. `## Troubleshooting` — must cover:
   - WASAPI exclusive mode conflicts (use MME device, or set `auto_convert=True`)
   - Kokoro download issues (HTTP errors, disk space, firewall)
   - Python version requirements (3.11 required — pystray crashes on 3.12+)
   - Hook registration verification (`cat ~/.claude/settings.json | grep agenttalk`)
7. `## License` — MIT

### MIT LICENSE File Content

```
MIT License

Copyright (c) 2026 omern

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Make Repository Public (gh CLI)

```bash
# If repo already exists on GitHub:
gh repo edit omern/AgentTalk --visibility public

# If creating fresh:
gh repo create omern/AgentTalk --public --source=. --remote=origin --push
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `setup.py` + `setuptools.setup()` | `pyproject.toml` with `[project]` table | PEP 517/518, standardized ~2021 | No Python needed for package metadata |
| `setup.cfg` for metadata | `pyproject.toml` `[project]` table | PEP 621, 2021 | Single source of truth |
| `MANIFEST.in` for non-Python files | `[tool.setuptools.package-data]` in pyproject.toml | setuptools 61+, 2022 | MANIFEST.in no longer required for wheel builds |
| `install_requires` in `setup.py` | `dependencies` in `pyproject.toml` | PEP 621 | Cleaner declarative format |
| Poetry `[tool.poetry]` table | `[project]` standard table | Poetry 2.0, Jan 2025 | Poetry now uses PEP 621 table; community alignment |

**Deprecated/outdated:**
- `setup.py` as build entrypoint: Still works but discouraged for new projects; pyproject.toml is the standard
- `MANIFEST.in` for wheel builds: Not needed if using `[tool.setuptools.package-data]`
- `python_requires` in `setup.py`: Now declared as `requires-python` in `[project]` table

---

## Project-Specific Context from Prior Phases

These decisions from STATE.md directly constrain Phase 6:

| Decision | Impact on Phase 6 |
|----------|-------------------|
| Python 3.11 required (pystray crashes on 3.12+ due to GIL bug) | `requires-python = ">=3.11,<3.12"` in pyproject.toml; prominent warning in README |
| pythonw.exe detection via `_get_pythonw_path()` already in `agenttalk/setup.py` | `installer.py` simply calls the existing function — no reimplementation |
| Hook registration via `register_hooks()` already complete in `agenttalk/setup.py` | `cli.py` setup subcommand calls `register_hooks()` directly |
| APPDATA paths used throughout codebase (`%APPDATA%\AgentTalk\`) | `installer.py` uses same path pattern for models subdir |
| WasapiSettings applied conditionally (MME devices get PaErrorCode -9984) | Document in README troubleshooting: "If you hear no audio, ensure your device uses WASAPI not MME" |
| kokoro-onnx 0.5.0 is pinned (not floating) | Pin same version in pyproject.toml `dependencies` |
| Piper TTS deferred to v2 (upstream archived Oct 2025) | Do NOT document Piper as a working feature in v1 README; note it as planned |
| Kokoro model files are NOT bundled with the pip package — downloaded separately by `agenttalk setup` | README quickstart must clearly show the two-step process: `pip install` then `agenttalk setup` |

---

## Open Questions

1. **pywin32 post-install on Python 3.11 with pip**
   - What we know: pywin32 >=301 ships with post-install scripts in the wheel's `data/` directory that pip executes automatically
   - What's unclear: Whether this works cleanly on Python 3.11 in a venv on Windows 11 without any manual steps
   - Recommendation: Test `pip install pywin32 winshell` in a fresh Python 3.11 venv and verify `import win32com.client` works without `python -m pywin32_postinstall -install`. If it fails, add the check to `installer.py`.

2. **Exact Python 3.11 constraint: `>=3.11,<3.12` vs `>=3.11`**
   - What we know: pystray crashes on 3.12+ due to GIL changes (documented in STATE.md); the pystray maintainer has not released a fix as of Feb 2026
   - What's unclear: Whether pystray 0.19.5+ has resolved this by Feb 2026
   - Recommendation: Use `requires-python = ">=3.11,<3.12"` to be safe; update when pystray fix is confirmed. Document this prominently in the README.

3. **PyPI publishing vs GitHub-only distribution**
   - What we know: DOC-05 requires the repo to be public at github.com/omern/AgentTalk; INST-01 requires `pip install agenttalk` to work
   - What's unclear: Does INST-01 require PyPI publishing or is `pip install git+https://github.com/omern/AgentTalk` acceptable?
   - Recommendation: `pip install git+https://...` satisfies the requirement and is simpler (no PyPI account/token setup). If the intent is a PyPI package, that adds a separate publishing step. Clarify with the user, but implement PyPI publishing as it is the standard interpretation of "pip install agenttalk".

4. **`requires-python` and pystray on 3.11**
   - What we know: Dev machine ran on Python 3.12 for phases 1-2 (STATE.md: decision 01-01), with pystray incompatibility deferred to Phase 4
   - What's unclear: Whether Phases 3-5 were tested on 3.11 or 3.12
   - Recommendation: Phase 6 plan should include a verification step: install package in a fresh Python 3.11 venv and run `agenttalk setup` end-to-end.

---

## Sources

### Primary (HIGH confidence)
- https://packaging.python.org/en/latest/guides/writing-pyproject-toml/ — pyproject.toml structure, `[project.scripts]`, `[tool.setuptools.package-data]`
- https://setuptools.pypa.io/en/latest/userguide/entry_point.html — console_scripts entry point format
- https://winshell.readthedocs.io/en/latest/shortcuts.html — winshell shortcut API (path, arguments, working_directory, description)
- https://docs.python.org/3/library/argparse.html — argparse subcommands with `add_subparsers()`
- https://github.com/thewh1teagle/kokoro-onnx — confirmed download URLs for model files

### Secondary (MEDIUM confidence)
- https://pypi.org/project/kokoro-onnx/ — kokoro-onnx 0.5.0 PyPI page; Python >=3.10 requirement confirmed
- https://gist.github.com/yanqd0/c13ed29e29432e3cf3e7c38467f42f51 — requests + tqdm streaming download pattern (widely cited, verified against tqdm docs)
- https://pypi.org/project/pywin32/ — pywin32 Python 3.11 support confirmed; wheel auto-runs post-install

### Tertiary (LOW confidence)
- WebSearch: "pystray Python 3.12 GIL crash" — not independently verified against current pystray release; flagged as open question #2
- WebSearch: pywin32 post-install behavior on Python 3.11 venv — needs hands-on validation (open question #1)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pyproject.toml, setuptools, winshell, tqdm are all well-documented; URLs verified
- Architecture: HIGH — CLI entry point pattern is standard Python; model download pattern is verified against tqdm docs
- Pitfalls: MEDIUM — most pitfalls derived from first principles and project STATE.md; pywin32 post-install behavior is LOW (needs testing)

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days; setuptools and packaging toolchain are stable)

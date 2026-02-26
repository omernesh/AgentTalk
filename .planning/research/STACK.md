# Stack Research

**Domain:** Local TTS background service — Windows, Python
**Researched:** 2026-02-26
**Confidence:** HIGH (all major claims verified against PyPI, official docs, or Claude Code official reference)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 | Runtime | 3.11 hits the sweet spot: stable, fast, fully supported by all dependencies (kokoro-onnx, piper-tts, sounddevice, pystray). Avoid 3.12+ until pystray GIL issues are resolved. Avoid 3.10 (no performance improvements). |
| kokoro-onnx | 0.5.0 (2026-01-30) | Primary TTS engine | Pure Python + ONNX Runtime. No espeak-ng required (uses built-in espeakng-loader). ~300MB standard model, ~80MB quantized. Best quality output of the two options. pip: `kokoro-onnx` |
| piper-tts | 1.4.1 (2026-02-05) | Secondary TTS engine | Lighter and faster than Kokoro, good for low-RAM machines. Windows x86-64 wheel ships as `piper_tts-1.4.1-cp39-abi3-win_amd64.whl` (13.8 MB). pip: `piper-tts` |
| FastAPI | 0.133.1 (2026-02-25) | HTTP server wrapping TTS | Async-native, minimal boilerplate, `BackgroundTasks` for fire-and-forget audio dispatch. Python >= 3.10 required — matches our runtime. |
| uvicorn | 0.41.0 (2026-02-16) | ASGI server for FastAPI | Standard FastAPI production server. Python >= 3.10. Single-worker is appropriate for a local single-user service. pip: `uvicorn` |
| sounddevice | 0.5.5 (2026-01-23) | Audio playback | Direct numpy array playback via PortAudio. Ships prebuilt wheels for Windows x86-64, x86, and ARM64. The only library that plays numpy arrays from kokoro-onnx without format conversion. pip: `sounddevice` |
| pystray | 0.19.5 (2023-09-17) | Windows system tray icon | Pure Python, no GUI framework dependency. Works on Windows 11 with workarounds (see Pitfalls). Requires Pillow for icon rendering. pip: `pystray` |
| Pillow | latest | Icon rendering for pystray | pystray requires a PIL.Image object for the tray icon. pip: `Pillow` |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| onnxruntime | >=1.20.1 (installed transitively by kokoro-onnx) | ONNX model execution | Automatically installed by `pip install kokoro-onnx`. Do not install separately unless pinning a version for GPU support. |
| soundfile | latest | WAV/audio file I/O | Needed when saving audio to disk or when piping audio from kokoro-onnx as a buffer. Installed transitively by kokoro-onnx. |
| numpy | latest | Audio data arrays | Installed transitively by sounddevice and kokoro-onnx. kokoro-onnx returns float32 numpy arrays; sounddevice.play() accepts these directly. |
| httpx | latest | HTTP client for hook scripts | Hook scripts need to POST text to the FastAPI service. httpx is sync/async, has a Windows-compatible CLI feel. pip: `httpx` |
| requests | latest | Alternative HTTP client for hook scripts | Simpler than httpx for a one-shot POST in a hook script. No async needed in hooks. Either works; requests has less overhead for simple POSTs. |
| pywin32 | latest | Windows-native process management | Optional. Needed if using `win32process` for `DETACHED_PROCESS` flags without subprocess constants. Usually `subprocess.DETACHED_PROCESS` suffices without it. pip: `pywin32` |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| venv | Isolated Python environment | `python -m venv .venv` then `.venv\Scripts\activate`. Never install project deps globally. |
| pythonw.exe | Launch service without a console window | Bundled with CPython on Windows. Replaces `python.exe` in the launch command. Example: `pythonw.exe service.py`. stdin/stdout/stderr are None — log to file. |
| PyInstaller (optional) | Bundle into a single .exe for distribution | Use `--noconsole --onefile` flags. Suitable for distributing AgentTalk without requiring Python installed. Not needed for developer-target installs. |

---

## Installation

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Core TTS + audio
pip install kokoro-onnx piper-tts sounddevice soundfile Pillow

# HTTP server
pip install "fastapi[standard]" uvicorn

# System tray
pip install pystray

# HTTP client (for hook scripts)
pip install httpx
```

**Model files (kokoro-onnx) — download separately:**

```bash
# Download from GitHub releases (one-time setup)
# kokoro-v1.0.onnx (~310MB) and voices-v1.0.bin (~26MB)
# Source: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
```

**Model files (piper-tts) — download separately:**

```bash
# Each voice = one .onnx file + one .onnx.json config file
# Browse voices: https://github.com/rhasspy/piper/blob/master/VOICES.md
# Example: en_US-amy-medium.onnx + en_US-amy-medium.onnx.json
# Source: https://huggingface.co/rhasspy/piper-voices
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| kokoro-onnx | hexgrad/kokoro (PyTorch) | When GPU is available and quality is the only concern. PyTorch variant is heavier (~2GB) and requires CUDA. Not appropriate for a lightweight background service. |
| kokoro-onnx | piper-tts (as primary) | When RAM is critical (< 100MB target). Piper is faster to load but lower quality. For AgentTalk, quality wins. |
| piper-tts | piper-onnx (thewh1teagle) | `piper-onnx` is an alternative thin wrapper. `piper-tts` is the official package from rhasspy. Use piper-tts as the official path. |
| sounddevice | pygame.mixer | pygame adds a full game framework just for audio. Adds 10+ MB of unneeded dependencies. sounddevice is purpose-built for numpy arrays. |
| sounddevice | simpleaudio | simpleaudio's last release was 2021. No longer actively maintained. sounddevice is current and has Windows-native PortAudio wheels. |
| sounddevice | winsound | winsound is Windows-only, file-based (WAV on disk), blocking, and cannot play numpy arrays directly. Too limiting. |
| pystray | infi.systray | infi.systray is Windows-only and less maintained. pystray works cross-platform and is more actively updated. |
| pystray | rumps | macOS-only. Not applicable. |
| FastAPI | Flask | Flask is sync-first. FastAPI's async BackgroundTasks model fits the fire-and-forget TTS dispatch pattern better. |
| FastAPI | aiohttp | More verbose. FastAPI provides auto-docs, Pydantic validation, and BackgroundTasks built-in. No reason to use aiohttp here. |
| uvicorn (single worker) | gunicorn + uvicorn workers | Multi-worker setup is for production web services. AgentTalk is a single-user local tool. One uvicorn worker is correct. |
| pythonw.exe | PyInstaller --noconsole | Both work. pythonw.exe is simpler for developer installs (no bundling step). Use PyInstaller only for distributing to non-Python users. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| gTTS | Makes HTTP calls to Google TTS. Cloud-dependent. Violates the local-only constraint. | kokoro-onnx or piper-tts |
| pyttsx3 | Uses Windows SAPI voices (robotic quality). No ONNX models, no custom voice selection. | kokoro-onnx or piper-tts |
| edge-tts | Calls Microsoft Azure TTS API. Cloud-dependent. | kokoro-onnx or piper-tts |
| coqui-tts (TTS library) | Abandoned (Coqui shut down). Package is archived. | kokoro-onnx |
| simpleaudio | Last release 2021, unmaintained. Windows build issues on Python 3.11+. | sounddevice |
| pygame.mixer for TTS audio | pygame requires initialization, adds event loop complexity, not needed. sounddevice is 5 lines vs 20 lines. | sounddevice |
| Python 3.12 or 3.13 with pystray | GIL behavior changes in 3.12+ trigger a documented crash in pystray's `_win32.py`: "PyEval_RestoreThread: the function must be called with the GIL held." No fix released as of 2026-02-26 (pystray 0.19.5, released 2023). | Python 3.11 |
| threading for pystray icon loop | pystray.Icon must run in the main thread on Windows (Win32 message pump requirement). Running it in a background thread causes the crash above. | Run pystray in main thread; run FastAPI/uvicorn in a daemon thread. |
| subprocess.Popen without DETACHED_PROCESS | Launching the service from a hook script with bare Popen will tie the service process to the hook's subprocess. When the hook exits, the service may get killed. | Use `subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP` flags. |
| sys.stdout / sys.stderr in pythonw.exe | pythonw.exe sets sys.stdin, sys.stdout, sys.stderr to None. Any unguarded print() call or library that writes to stdout will crash the process. | Redirect all logging to a file at startup: `logging.basicConfig(filename='agenttalk.log')` |

---

## Stack Patterns by Variant

**If running as developer install (Python available on PATH):**
- Launch with `pythonw.exe service.py`
- No PyInstaller bundling needed
- Manage model files in a known config directory (e.g., `%APPDATA%\AgentTalk\models\`)

**If distributing to non-developer users:**
- Bundle with PyInstaller: `pyinstaller --noconsole --onefile service.py`
- Bundle model files alongside the .exe or download on first run
- Note: PyInstaller bundles inflate to ~400-600MB with ONNX models

**If GPU is available (NVIDIA) and quality matters:**
- Replace `onnxruntime` with `onnxruntime-gpu`
- pip: `pip install onnxruntime-gpu` (uninstall `onnxruntime` first)
- kokoro-onnx will detect GPU automatically via ONNX execution providers

**If RAM is the constraint (< 100MB target):**
- Switch primary engine to piper-tts (lighter model files, ~70MB per voice)
- Use quantized kokoro model (~80MB) as an alternative
- piper loads faster and synthesizes faster on CPU

---

## Claude Code Hook Integration

### Relevant Hooks

AgentTalk uses two hooks:

| Hook | Event | Purpose | JSON Fields Used |
|------|-------|---------|-----------------|
| `SessionStart` | Fires on new session or resume | Start the TTS service if not running | `source` (startup/resume/clear/compact), `session_id`, `cwd` |
| `Stop` | Fires when Claude finishes responding | Extract assistant text and POST to TTS service | `last_assistant_message` (string — ready to use, no transcript parsing needed), `stop_hook_active` |

### SessionStart Hook — Launching the Service

The `SessionStart` hook fires with this JSON on stdin:

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "SessionStart",
  "source": "startup",
  "model": "claude-sonnet-4-6"
}
```

The hook script should:
1. Check if AgentTalk is already running (e.g., check port 8765 or a PID file)
2. If not running, launch `pythonw.exe service.py` with `DETACHED_PROCESS` flags
3. Exit 0 immediately (keep hook fast — SessionStart runs on every session)

Critical: Use `async: true` in the hook configuration so the service launch does not block Claude Code startup:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/start_tts.py\"",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### Stop Hook — Extracting and Speaking Text

The `Stop` hook fires with this JSON on stdin:

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "I've completed the refactoring. Here's a summary..."
}
```

**Key insight:** `last_assistant_message` is the complete final text of Claude's response, already extracted. No transcript parsing is needed. The hook script reads this field and POSTs it to the FastAPI service.

Critical: Always check `stop_hook_active` — if `true`, a Stop hook is already running and re-triggering would cause an infinite loop.

The hook should use `async: true` so it does not block Claude Code from displaying the response:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/speak.py\"",
        "async": true,
        "timeout": 5
      }
    ]
  }
}
```

### Hook Scope

Place hooks in `.claude/settings.json` (project-scoped, committable to repo) so they work for any user who clones the project. Use `$CLAUDE_PROJECT_DIR` to reference scripts by absolute path regardless of working directory.

---

## FastAPI Fire-and-Forget Pattern

The minimal TTS endpoint pattern:

```python
from fastapi import FastAPI, BackgroundTasks
import sounddevice as sd

app = FastAPI()

def speak_sync(text: str, voice: str):
    # TTS synthesis returns numpy array
    samples, sample_rate = tts_engine.synthesize(text, voice=voice)
    sd.play(samples, sample_rate)
    sd.wait()  # blocking only inside background task thread

@app.post("/speak")
async def speak(text: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(speak_sync, text, current_voice)
    return {"status": "queued"}
```

FastAPI's `BackgroundTasks` runs after the response is sent, in the same process. For a local single-user service this is correct — no queue, no Celery, no Redis needed. The hook POSTs and immediately returns; speech plays in the background.

**Important:** `sd.play()` is non-blocking by default. Call `sd.wait()` after it inside the background task so audio plays completely before the task exits. Do not call `sd.wait()` in the async route handler — it would block the event loop.

---

## Process Architecture

```
Claude Code (Node.js)
    |
    +-- SessionStart hook (Python script, async)
    |       |
    |       +-- Checks if service running
    |       +-- Launches: pythonw.exe service.py
    |
    +-- Stop hook (Python script, async)
            |
            +-- Reads last_assistant_message from stdin JSON
            +-- POST http://localhost:8765/speak?text=...
            +-- Exits 0 immediately

service.py (pythonw.exe, no console)
    |
    +-- Main thread: pystray.Icon (Win32 message pump)
    +-- Daemon thread: uvicorn (FastAPI HTTP server, port 8765)
    +-- Background tasks: TTS synthesis + sounddevice playback
```

**Why pystray in main thread:** Win32's message pump (`GetMessage`/`DispatchMessage`) must run in the thread that created the window/tray icon. pystray's Windows backend enforces this. Attempting to run pystray in a non-main thread causes the `PyEval_RestoreThread` GIL crash.

**Why uvicorn in daemon thread:** uvicorn runs an asyncio event loop. It can safely run in a daemon thread. When pystray's main thread exits (user quits via tray menu), the daemon thread is automatically cleaned up.

---

## Version Compatibility Matrix

| Package | Version | Compatible With | Notes |
|---------|---------|-----------------|-------|
| Python | 3.11.x | All dependencies | Do not use 3.12+; pystray GIL crash risk |
| kokoro-onnx | 0.5.0 | Python 3.10–3.13, onnxruntime >=1.20.1 | Requires Python <3.14 |
| piper-tts | 1.4.1 | Python 3.9–3.13 | Windows wheel: win_amd64 only |
| FastAPI | 0.133.1 | Python >=3.10, Starlette, Pydantic v2 | |
| uvicorn | 0.41.0 | Python >=3.10 | |
| sounddevice | 0.5.5 | Python >=3.7, PortAudio (bundled in wheel) | Windows wheel includes PortAudio DLL |
| pystray | 0.19.5 | Python 2.7, 3.4+ | Last release 2023; functional on Windows 11 with Python 3.11 |
| Pillow | latest | Python 3.8+ | Required by pystray for icon image handling |
| onnxruntime | >=1.20.1 | Python 3.8–3.12 | Installed by kokoro-onnx transitively |

---

## Windows-Specific Gotchas

### 1. pythonw.exe kills stdout/stderr
Any unguarded `print()` or library write to stdout/stderr crashes the process silently.
**Fix:** At service startup (before any imports that might log):
```python
import logging, sys, os
logging.basicConfig(
    filename=os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'AgentTalk', 'service.log'),
    level=logging.INFO
)
```

### 2. DETACHED_PROCESS for hook-launched service
The SessionStart hook script must launch the service fully detached or it will be killed when the hook script exits.
```python
import subprocess
subprocess.Popen(
    ['pythonw.exe', 'service.py'],
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
```

### 3. espeak-ng for kokoro-onnx on Windows
The `kokoro-onnx` package includes `espeakng-loader` as a dependency, which bundles espeak-ng data files. A separate espeak-ng MSI install should NOT be needed. The older `hexgrad/kokoro` (PyTorch) package required manual espeak-ng installation, but `kokoro-onnx` 0.5.0 handles this via `espeakng-loader`. Verify by running a synthesis test after `pip install kokoro-onnx` without any system espeak-ng install.
**Confidence: MEDIUM** — `espeakng-loader` is listed as a dependency, but Windows-specific behavior is not explicitly documented in the README. Test on a clean machine.

### 4. pystray icon resolution change on Windows 11
pystray 0.19.5 fixed a blurry icon bug triggered by screen resolution changes. Always use >= 0.19.5.

### 5. sounddevice blocking plays cut short on Windows MME
There is a documented issue (GitHub #283) where `sd.play()` cuts audio short when using the Windows MME host API.
**Fix:** Explicitly select the WASAPI host API or call `sd.wait()` after every `sd.play()`.
```python
sd.play(samples, sample_rate, blocking=True)
# OR
sd.play(samples, sample_rate)
sd.wait()
```

### 6. Port conflicts
The service uses port 8765 (avoid 8000/8080 which may be taken by dev servers). Check for existing process before binding:
```python
import socket
def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0
```

---

## Sources

- [kokoro-onnx on PyPI](https://pypi.org/project/kokoro-onnx/) — version 0.5.0, Python 3.10–3.13, released 2026-01-30 (HIGH confidence)
- [kokoro-onnx GitHub](https://github.com/thewh1teagle/kokoro-onnx) — install command, model file requirements, espeakng-loader dependency (HIGH confidence)
- [piper-tts on PyPI](https://pypi.org/project/piper-tts/) — version 1.4.1, Windows win_amd64 wheel, released 2026-02-05 (HIGH confidence)
- [FastAPI on PyPI](https://pypi.org/project/fastapi/) — version 0.133.1, Python >=3.10, released 2026-02-25 (HIGH confidence)
- [uvicorn on PyPI](https://pypi.org/project/uvicorn/) — version 0.41.0, Python >=3.10, released 2026-02-16 (HIGH confidence)
- [sounddevice on PyPI](https://pypi.org/project/sounddevice/) — version 0.5.5, Windows wheels available, released 2026-01-23 (HIGH confidence)
- [pystray on PyPI](https://pypi.org/project/pystray/) — version 0.19.5, released 2023-09-17 (HIGH confidence)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) — SessionStart/Stop JSON schemas, `last_assistant_message` field, `async` hook field, `$CLAUDE_PROJECT_DIR` variable (HIGH confidence — official docs)
- [FastAPI BackgroundTasks docs](https://fastapi.tiangolo.com/tutorial/background-tasks/) — fire-and-forget pattern (HIGH confidence)
- [sounddevice GitHub issue #283](https://github.com/spatialaudio/python-sounddevice/issues/283) — Windows MME blocking play cutoff (MEDIUM confidence)
- [pystray GIL crash on Windows 11](https://github.com/PySimpleGUI/PySimpleGUI/issues/6812) — GIL crash conditions with Python 3.12+ (MEDIUM confidence)
- [subprocess.DETACHED_PROCESS docs](https://docs.python.org/3/library/subprocess.html) — Windows-only flag for detached processes (HIGH confidence)
- WebSearch: espeak-ng Windows setup for kokoro — espeakng-loader bundled vs. manual MSI install (MEDIUM confidence — needs clean-machine verification)

---

*Stack research for: AgentTalk — Windows local TTS background service*
*Researched: 2026-02-26*

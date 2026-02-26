# Architecture Research

**Domain:** Windows background service — Python FastAPI + pystray + local TTS
**Researched:** 2026-02-26
**Confidence:** HIGH (threading model verified against official uvicorn docs and pystray docs; hook payload verified against official Claude Code docs)

---

## Standard Architecture

### System Overview

```
Claude Code (Terminal)
       |
       | fires hook (Stop / SessionStart)
       v
.claude/hooks/speak.py          (hook script — thin relay)
       |
       | HTTP POST /speak  { "text": "..." }
       v
+--------------------------------------------------+
|           ClaudeTalk Service (single process)    |
|                                                  |
|  Main Thread                                     |
|  +-----------+                                   |
|  | pystray   |   icon, menu, right-click         |
|  | Icon.run()|   (blocking — owns main thread)   |
|  +-----------+                                   |
|        |  setup= callback fires into daemon thr  |
|        v                                         |
|  Thread 1: uvicorn (FastAPI HTTP server)         |
|  +-----------------------------------+           |
|  | POST /speak  -> queue.put(text)   |           |
|  | POST /stop   -> shutdown signal   |           |
|  | GET  /status -> health check      |           |
|  +-----------------------------------+           |
|        |                                         |
|        | thread-safe queue.Queue                 |
|        v                                         |
|  Thread 2: TTS Worker (daemon)                   |
|  +-----------------------------------+           |
|  | while True:                       |           |
|  |   text = queue.get()              |           |
|  |   sentences = split(text)         |           |
|  |   for s in sentences:             |           |
|  |     audio = tts.synthesize(s)     |           |
|  |     sounddevice.play(audio)       |           |
|  |     sounddevice.wait()            |           |
|  +-----------------------------------+           |
|                                                  |
|  Config: %APPDATA%/ClaudeTalk/config.json        |
|  PID file: %APPDATA%/ClaudeTalk/service.pid      |
+--------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `speak.py` hook script | Reads stdin JSON from Claude Code, extracts `last_assistant_message`, fires HTTP POST | HTTP → ClaudeTalk service |
| FastAPI HTTP server (uvicorn, Thread 1) | Accepts `/speak` POST, validates, enqueues text; accepts `/stop` to initiate shutdown | queue.Queue → TTS Worker; pystray via event |
| TTS Worker (Thread 2) | Dequeues text, splits to sentences, calls Kokoro, plays audio synchronously | kokoro-onnx, sounddevice |
| pystray Icon (Main Thread) | Renders system tray icon; provides right-click menu for stop/status; owns the Windows message loop | Calls uvicorn shutdown on "Quit" click |
| Config store | Persists voice, model, speed between restarts | Read on startup; written on `/claudetalk:voice` and `/claudetalk:model` commands |
| PID file | Tracks running process for stop commands | Written on startup, deleted on shutdown |

---

## Threading Model — Critical Detail

### Why This Specific Layout

**pystray on Windows:** `Icon.run()` is blocking and must be the call that holds the main thread. On Windows specifically, pystray is safe to run from a non-main thread (unlike macOS which requires main thread due to Cocoa), but running it in the main thread is the recommended cross-platform pattern. (Source: pystray official docs — https://pystray.readthedocs.io/en/latest/usage.html)

**pystray `setup=` parameter:** `Icon.run(setup=fn)` accepts a `setup` callable that runs in a separate daemon thread once the tray icon is ready. This is the official integration point for launching other frameworks alongside pystray. Use `setup` to start uvicorn in Thread 1 and start the TTS worker Thread 2.

**uvicorn signal handlers:** Modern uvicorn (0.13.0+) automatically detects when it is not running in the main thread and skips signal handler installation. This was merged in uvicorn PR #871. There is no need to subclass `uvicorn.Server` or override `install_signal_handlers()` with current uvicorn versions. (Source: https://www.uvicorn.org/release-notes/)

**The correct startup sequence:**

```python
import threading
import queue
import uvicorn
import pystray
from PIL import Image

tts_queue = queue.Queue()

def start_background_services(icon):
    """Called by pystray in a daemon thread after icon is ready."""
    # Thread 1: uvicorn
    config = uvicorn.Config(app=fastapi_app, host="127.0.0.1", port=5050, log_level="error")
    server = uvicorn.Server(config)
    uvicorn_thread = threading.Thread(target=server.run, daemon=True)
    uvicorn_thread.start()

    # Thread 2: TTS worker
    tts_thread = threading.Thread(target=tts_worker_loop, args=(tts_queue,), daemon=True)
    tts_thread.start()

def main():
    icon_image = Image.open("icon.png")
    menu = pystray.Menu(
        pystray.MenuItem("Stop ClaudeTalk", stop_service),
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon("claudetalk", icon_image, "ClaudeTalk", menu)
    icon.run(setup=start_background_services)  # blocks main thread
```

**Why NOT separate processes:** Two processes would require IPC for shutdown coordination, complicate the PID management, and add overhead for this single-machine use case. One process with threads is simpler and sufficient.

---

## Process Model — Windows Background Launch

### Launching Without a Console Window

The service must start without showing a console window. Two valid approaches:

**Option A: `pythonw.exe` (recommended for simplicity)**
```python
# In hook script or slash command
import subprocess
subprocess.Popen(
    ["pythonw.exe", str(service_script_path)],
    creationflags=subprocess.DETACHED_PROCESS,
)
```
`pythonw.exe` is the Windows-native "no console" Python interpreter. It ships alongside `python.exe` in every standard Python distribution.

**Option B: `python.exe` with `CREATE_NO_WINDOW` flag**
```python
import subprocess
subprocess.Popen(
    ["python.exe", str(service_script_path)],
    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
)
```
`CREATE_NO_WINDOW` suppresses the console window. Use this when `pythonw.exe` is not reliably on `PATH` (e.g., conda environments).

**Both options work without admin rights.** No service installation (NSSM, sc.exe) is needed or desired.

### PID File Pattern

```
On startup:
    pid_path = Path(os.environ["APPDATA"]) / "ClaudeTalk" / "service.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))

On shutdown (lifespan event or signal):
    pid_path.unlink(missing_ok=True)
```

The stop slash command or `/claudetalk:stop` hook reads the PID file and calls `os.kill(pid, signal.SIGTERM)` or falls back to `psutil.Process(pid).terminate()` on Windows where SIGTERM semantics differ.

---

## Text Queue — TTS Backpressure

### Problem

Claude Code's `Stop` hook fires at end of each assistant turn. For long responses the hook delivers the entire `last_assistant_message` as one string (potentially thousands of words). TTS synthesis is real-time (or faster). Multiple `Stop` events can pile up if the user sends rapid-fire prompts.

### Recommended Approach: Bounded Queue with Discard-on-Full

```python
TTS_QUEUE_MAXSIZE = 3  # allow queuing up to 3 full responses

tts_queue = queue.Queue(maxsize=TTS_QUEUE_MAXSIZE)

@app.post("/speak")
async def speak(req: SpeakRequest):
    try:
        tts_queue.put_nowait(req.text)
    except queue.Full:
        # Drop oldest, enqueue new (optional: discard new instead)
        try:
            tts_queue.get_nowait()
        except queue.Empty:
            pass
        tts_queue.put_nowait(req.text)
    return {"queued": True}
```

### TTS Worker: Sentence-Chunked Synthesis

```python
import re

SENTENCE_SPLITTER = re.compile(r'(?<=[.!?])\s+')

def tts_worker_loop(q: queue.Queue, kokoro: Kokoro):
    while True:
        text = q.get()
        if text is None:  # shutdown sentinel
            break
        sentences = SENTENCE_SPLITTER.split(text.strip())
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            try:
                samples, sample_rate = kokoro.create(
                    sentence, voice=config.voice, speed=config.speed, lang="en-us"
                )
                sd.play(samples, sample_rate)
                sd.wait()  # blocks until audio finishes — natural pacing
            except Exception:
                pass  # never crash the worker on synthesis error
        q.task_done()
```

**Why sentence-chunked:** kokoro-onnx `create()` returns a numpy array for a full input string. Splitting by sentence gives natural pauses at sentence boundaries and allows the worker to start playing the first sentence while the rest are synthesized sequentially. Per the PROJECT.md, streaming TTS mid-sentence is out of scope for v1.

**Why `sd.wait()` (blocking):** Audio playback is inherently sequential — each sentence must finish before the next begins. The TTS worker thread is the only consumer, so blocking is correct here. The FastAPI thread continues accepting new `/speak` POSTs during playback.

### Interrupt-on-New-Response (Optional Enhancement)

If a new message arrives while TTS is playing, stop current playback:

```python
@app.post("/speak")
async def speak(req: SpeakRequest):
    # Clear queue and stop current playback before enqueuing new text
    with tts_queue.mutex:
        tts_queue.queue.clear()
    sd.stop()  # stops sounddevice playback immediately
    tts_queue.put_nowait(req.text)
    return {"queued": True}
```

This is a v1.1 enhancement — implement only if users report frustration with audio piling up.

---

## Claude Code Hook Architecture

### Which Hooks Fire

| Hook | When | Use for ClaudeTalk |
|------|------|--------------------|
| `Stop` | When main Claude agent finishes responding | PRIMARY: speak the assistant's complete response |
| `SessionStart` | When Claude Code starts a session | Start the ClaudeTalk service if not running |
| `SessionEnd` | When session ends | Optional: stop ClaudeTalk service |

**Do NOT use `PostToolUse`** for speaking: PostToolUse fires after every tool call (file reads, web searches, bash commands) — not after the final assistant text response. That produces excessive, unwanted speech.

### Stop Hook — Payload Structure (HIGH confidence, verified from official docs)

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "I've completed the refactoring. Here's a summary..."
}
```

**`last_assistant_message`** is the field to POST to the service. It is the final text response without tool outputs or metadata. This is exactly what ClaudeTalk needs — no transcript parsing required.

**`stop_hook_active`**: When `true`, Claude is already continuing due to a previous Stop hook's `decision: "block"`. ClaudeTalk should check this and still speak even when it's `true`, but should NEVER return `decision: "block"` (that would create infinite continuation loops).

### Hook Script Design

```python
#!/usr/bin/env python3
# .claude/hooks/speak.py
import json
import sys
import urllib.request

def main():
    payload = json.load(sys.stdin)
    text = payload.get("last_assistant_message", "").strip()
    if not text:
        sys.exit(0)

    try:
        data = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:5050/speak",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # Service not running — fail silently, never block Claude
    sys.exit(0)  # always exit 0; never block or delay Claude Code

if __name__ == "__main__":
    main()
```

**Critical: `async: true` in hook configuration.** The hook must run asynchronously so it does not block Claude Code's UI while the HTTP POST fires. TTS playback happens independently in the service.

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR\\.claude\\hooks\\speak.py\"",
            "async": true,
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR\\.claude\\hooks\\ensure_running.py\"",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

---

## Config Persistence

### Recommendation: JSON in APPDATA

Use `%APPDATA%\ClaudeTalk\config.json` — always writable by the current user, no admin rights required, survives Python environment changes.

```python
from pathlib import Path
import json
import os

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ClaudeTalk"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "model": "kokoro",
    "voice": "af_sarah",
    "speed": 1.0,
    "enabled": True,
    "port": 5050,
}

def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        return {**DEFAULTS, **json.loads(CONFIG_FILE.read_text())}
    return DEFAULTS.copy()

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
```

**Why not registry:** Registry requires `winreg` and is harder to inspect/edit manually. APPDATA JSON is transparent — users can edit it directly if needed.

**Why not `.env` / environment variables:** Environment variables don't persist across process restarts without a shell session. Not appropriate for user preferences.

**Why not TOML:** `tomllib` (Python 3.11+ stdlib) is read-only. Writing TOML requires `tomli-w` as an extra dependency. JSON is read/write with the stdlib.

---

## Service Lifecycle — Start/Stop

### Startup Sequence

```
1. Hook (ensure_running.py) or slash command fires
2. Check PID file exists AND process is alive (psutil.pid_exists)
3. If alive: skip (already running)
4. If not alive or no PID file: launch service with pythonw.exe
5. Service starts:
   a. Load config from APPDATA
   b. Initialize Kokoro model (slow — 1-3s on first load)
   c. Start pystray icon (main thread, blocking)
   d. pystray.setup= callback: start uvicorn thread + TTS worker thread
   e. Write PID file
   f. POST /status returns 200 once uvicorn is accepting
```

### Shutdown Sequence

**Via "Quit" tray menu:**
```
1. pystray MenuItem callback fires (on tray icon thread)
2. Stop TTS worker: tts_queue.put(None) sentinel + sd.stop()
3. Stop uvicorn: server.should_exit = True
4. Delete PID file
5. icon.stop() — exits pystray main loop → process exits
```

**Via `/claudetalk:stop` slash command (HTTP):**
```
1. Claude Code slash command script runs
2. HTTP POST http://127.0.0.1:5050/stop
3. FastAPI /stop handler:
   a. tts_queue.put(None)
   b. sd.stop()
   c. Schedule server.should_exit = True (asyncio.get_event_loop().call_soon)
   d. icon.stop()
4. Service exits
```

**Via PID file (fallback if HTTP unreachable):**
```python
import psutil, signal
pid = int(Path(pid_file).read_text())
p = psutil.Process(pid)
p.terminate()  # SIGTERM on Unix, TerminateProcess on Windows
```

### Health Check

`GET /status` returns:
```json
{
  "status": "running",
  "model": "kokoro",
  "voice": "af_sarah",
  "queue_depth": 0,
  "pid": 12345
}
```

Used by `ensure_running.py` hook and `/claudetalk:status` slash command.

---

## Recommended Project Structure

```
claudetalk/
├── service/
│   ├── __main__.py          # Entry point: init pystray, threads, config
│   ├── api.py               # FastAPI app, /speak /stop /status /voice endpoints
│   ├── tts_worker.py        # TTS queue worker loop
│   ├── tray.py              # pystray icon setup, menu definitions
│   ├── config.py            # load_config / save_config / APPDATA paths
│   └── models/
│       ├── kokoro.py        # Kokoro wrapper (returns numpy array, sample_rate)
│       └── piper.py         # Piper wrapper (if Windows support confirmed)
├── hooks/
│   ├── speak.py             # Stop hook: POST last_assistant_message
│   ├── ensure_running.py    # SessionStart hook: start service if not running
│   └── slash/
│       ├── start.py         # /claudetalk:start
│       ├── stop.py          # /claudetalk:stop
│       ├── voice.py         # /claudetalk:voice
│       └── model.py         # /claudetalk:model
├── assets/
│   └── icon.png             # System tray icon (32x32 or 64x64 PNG)
├── install.py               # One-command installer: copies hooks, creates shortcut
├── pyproject.toml           # Dependencies
└── .claude/
    └── settings.json        # Hook registration (Stop, SessionStart)
```

### Structure Rationale

- **`service/`:** All service code in one package. `__main__.py` allows `python -m claudetalk.service` invocation.
- **`hooks/`:** Hook scripts are thin relay scripts — minimal dependencies, fast startup. They must not import heavy libraries (kokoro, sounddevice).
- **`models/`:** Isolates TTS engine differences behind a common interface: `synthesize(text, voice, speed) -> (np.ndarray, int)`.
- **`install.py`:** Handles the "copy hooks + register in .claude/settings.json + create .lnk shortcut" flow without user path-wrangling.

---

## Data Flow: Claude Output → Audio

```
Claude Code generates response
        |
        v
Stop hook fires → speak.py reads stdin JSON
        |
        | extracts: payload["last_assistant_message"]
        v
HTTP POST http://127.0.0.1:5050/speak
        { "text": "I've completed the refactoring. Here's a summary..." }
        |
        v
FastAPI /speak handler
        |
        | tts_queue.put_nowait(text)
        v
TTS Worker dequeues text
        |
        | sentence = split on [.!?]
        v
kokoro.create(sentence, voice="af_sarah", speed=1.0, lang="en-us")
        |
        | returns (numpy_array, sample_rate=24000)
        v
sounddevice.play(numpy_array, sample_rate)
sounddevice.wait()   ← blocks until sentence audio completes
        |
        | next sentence...
        v
Audio heard through system speakers
```

**End-to-end latency (estimated):**
- Hook fires → HTTP POST: ~50ms (subprocess startup + network on loopback)
- Queue to first sentence synthesis (Kokoro on CPU): ~300-800ms
- Audio begins playing: ~1-1.5 seconds after Claude finishes responding

---

## Architectural Patterns

### Pattern 1: Daemon Thread for Background Work

**What:** Mark uvicorn and TTS worker threads as `daemon=True`. Daemon threads are killed automatically when the main thread (pystray) exits.

**When to use:** Any thread that should not prevent process exit.

**Trade-offs:** Daemon threads cannot do cleanup on process kill. For ClaudeTalk this is fine — the PID file is the only cleanup needed, and it is deleted in pystray's shutdown sequence before `icon.stop()` is called.

```python
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
```

### Pattern 2: Queue Sentinel for Clean Worker Shutdown

**What:** Send a `None` sentinel value into the queue to signal the worker to exit gracefully.

**When to use:** Any producer-consumer queue pattern where workers must drain cleanly.

```python
# Producer (shutdown)
tts_queue.put(None)

# Worker
while True:
    item = tts_queue.get()
    if item is None:
        break
    # process item
```

### Pattern 3: FastAPI Lifespan Context Manager

**What:** Use FastAPI's `lifespan` context manager (not deprecated `@app.on_event`) for startup and shutdown lifecycle hooks within the ASGI server.

**When to use:** Loading TTS models on startup (slow — do it once, not per-request).

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.state.kokoro = Kokoro(model_path, voices_path)
    app.state.config = load_config()
    yield
    # shutdown — clean up if needed
    pass

app = FastAPI(lifespan=lifespan)
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Running TTS in the FastAPI Async Handler

**What people do:** Call `kokoro.create()` directly inside the `async def speak()` route handler.

**Why it's wrong:** `kokoro.create()` is CPU-bound and takes 300-800ms. Called inside an async handler it blocks the uvicorn event loop, preventing any other HTTP requests from being processed during synthesis. Under rapid-fire hook calls this creates a response pileup.

**Do this instead:** Route handler enqueues text into `queue.Queue`. TTS worker thread dequeues and synthesizes. The handler returns immediately with `{"queued": True}`.

### Anti-Pattern 2: Using `PostToolUse` as the Speech Trigger

**What people do:** Hook on `PostToolUse` to capture assistant output as it streams.

**Why it's wrong:** `PostToolUse` fires after every individual tool call (file reads, web searches, bash, etc.) — not after the assistant composes its final text response. This triggers speech for every intermediate tool step, producing unwanted and chaotic output.

**Do this instead:** Use `Stop` hook with `last_assistant_message` field, which is the complete final assistant response text.

### Anti-Pattern 3: Blocking the Hook Script

**What people do:** Have the hook script wait for TTS to finish before exiting.

**Why it's wrong:** Claude Code waits for hook scripts to exit before considering the turn complete. A blocking hook freezes the Claude Code UI until all audio finishes playing (potentially 30-60 seconds for long responses).

**Do this instead:** Set `"async": true` on the hook handler, or have the hook script fire-and-forget the HTTP POST with a short timeout and exit 0 immediately.

### Anti-Pattern 4: Calling `icon.run()` from a Thread

**What people do:** Start pystray in a background thread to avoid blocking main.

**Why it's wrong:** While technically safe on Windows (pystray docs confirm this), it breaks cross-platform compatibility and makes the pystray setup callback pattern (`setup=fn`) harder to reason about. More importantly, if the main thread exits for any reason, pystray and all daemon threads die immediately.

**Do this instead:** `icon.run(setup=start_services)` in the main thread. The `setup=` callback is the official integration point for starting other event loops alongside pystray.

### Anti-Pattern 5: Storing Model Files in the Repo

**What people do:** Commit the `kokoro-v1.0.onnx` (300MB) and `voices-v1.0.bin` files to the Git repository.

**Why it's wrong:** Repository becomes unusable; GitHub has a 100MB file size limit and cloning becomes slow for users.

**Do this instead:** `install.py` downloads model files from GitHub Releases on first run. `.gitignore` excludes `*.onnx` and `*.bin`.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| kokoro-onnx | Python library import; `Kokoro("model.onnx", "voices.bin").create(text, voice, speed, lang)` returns `(np.ndarray, int)` | Returns 24kHz float32 numpy array; no network calls |
| piper-tts | Python library import; Windows wheel available (win_amd64) as of v1.4.1 | Original repo archived Oct 2025 but PyPI package still updated; treat as secondary model |
| sounddevice | `sd.play(samples, sample_rate)` + `sd.wait()` | Requires PortAudio; bundled in sounddevice wheel on Windows |
| Claude Code | Hook system: shell commands receive JSON on stdin, communicate via exit codes + stdout | Official API — stable |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Hook script ↔ FastAPI | HTTP POST on loopback (127.0.0.1:5050) | Loopback only; no external exposure |
| FastAPI ↔ TTS Worker | `queue.Queue` (thread-safe) | Bounded queue prevents unbounded memory growth |
| TTS Worker ↔ sounddevice | Direct function call (blocking) | Synthesis and playback are sequential per sentence |
| pystray ↔ FastAPI | `setup=` callback starts uvicorn thread; menu callbacks set `server.should_exit = True` | One-way: tray controls service lifetime |
| Service ↔ Slash Commands | HTTP GET/POST on loopback | Slash command scripts are thin HTTP clients |

---

## Build Order Implications

The dependency graph drives phase ordering:

```
Phase 1: Core TTS synthesis
    kokoro-onnx + sounddevice working end-to-end
    (no HTTP, no hooks, no tray — just: text in, audio out)
    Validates: model works on Windows, audio output works

Phase 2: FastAPI + queue
    /speak endpoint + TTS worker queue
    Test with curl before any hook integration
    Validates: threading model, queue backpressure, sentence splitting

Phase 3: Hook integration
    Stop hook + ensure_running.py
    Test end-to-end: type in Claude Code → audio plays
    Validates: hook payload parsing, async hook behavior

Phase 4: pystray + process model
    System tray icon, pythonw.exe background launch, PID file
    Validates: no console window, tray appears, clean shutdown

Phase 5: Config + slash commands
    APPDATA config file, /voice /model /start /stop slash commands
    Validates: persistence across restarts

Phase 6: Install script + packaging
    install.py, model download, .lnk shortcut
    Validates: clean-machine installation
```

**Why this order:** Phase 1 is the highest-risk unknown (Windows TTS audio stack). Validate it in isolation before building the surrounding service infrastructure. Phases 2-3 build the HTTP + hook plumbing. Phase 4 adds the UX layer. Never do tray + hooks + TTS all at once.

---

## Scalability Considerations

This is a single-user, single-machine tool. Scalability in the traditional sense does not apply. The relevant "scale" axis is response length and request frequency.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Short responses (< 100 words) | Default queue size 3 is fine; single sentence plays fast |
| Long responses (500-1000 words) | Sentence chunking handles this naturally; 10-30 sentences queue up and play sequentially |
| Rapid-fire prompts (user sends 5 in quick succession) | Bounded queue drops old entries; interrupt-on-new optional enhancement |
| Multiple Claude Code sessions simultaneously | Single service instance handles all sessions via the same queue; ordering is FIFO across sessions |

---

## Sources

- pystray threading documentation: https://pystray.readthedocs.io/en/latest/usage.html (HIGH confidence — official docs)
- uvicorn thread signal handler fix (PR #871, v0.13.0): https://github.com/Kludex/uvicorn/pull/871 (HIGH confidence — official repo)
- uvicorn background thread pattern: https://bugfactory.io/articles/starting-and-stopping-uvicorn-in-the-background/ (MEDIUM confidence — verified against uvicorn docs)
- Claude Code hooks reference — Stop hook payload schema: https://code.claude.com/docs/en/hooks (HIGH confidence — official docs, accessed 2026-02-26)
- kokoro-onnx API (`Kokoro.create()` returns numpy array + sample_rate): https://github.com/thewh1teagle/kokoro-onnx (HIGH confidence — official repo README + examples/save.py)
- piper-tts Windows wheel availability (win_amd64): https://pypi.org/project/piper-tts/ (MEDIUM confidence — PyPI listing verified; original repo archived but package maintained)
- Windows no-console subprocess (`pythonw.exe`, `CREATE_NO_WINDOW`): Python official docs subprocess module (HIGH confidence)
- platformdirs for APPDATA config directory: https://github.com/tox-dev/platformdirs (HIGH confidence — official repo)

---

*Architecture research for: ClaudeTalk — Python FastAPI + pystray + local TTS background service*
*Researched: 2026-02-26*

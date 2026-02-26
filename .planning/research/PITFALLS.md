# Pitfalls Research

**Domain:** Windows Python TTS background service (FastAPI + Kokoro/Piper + pystray + Claude Code hooks)
**Researched:** 2026-02-26
**Confidence:** MEDIUM — Windows-specific behavior verified via official docs and GitHub issues; some edge cases LOW confidence from community reports only

---

## Critical Pitfalls

### Pitfall 1: pystray.Icon.run() Blocks the Main Thread

**What goes wrong:**
`pystray.Icon.run()` is a blocking call that must run on the main thread for cross-platform compatibility. When you also want to run `uvicorn` (which starts its own asyncio event loop), you have two blocking calls competing for the main thread. The naive approach — running both in threads — fails because pystray's Windows backend requires the Win32 message loop on the thread that created it.

**Why it happens:**
Developers assume that because Windows is more permissive than macOS (pystray docs note "if you only target Windows, calling run() from a thread other than the main thread is safe"), they can freely thread everything. The real trap is that `uvicorn.run()` also spawns its own event loop. When both run in background threads, shutdown becomes a deadlock: pystray waits for its message loop to drain while uvicorn's asyncio loop holds a reference that prevents clean exit.

**How to avoid:**
Use `pystray.Icon.run_detached()` — this is the purpose-built method for exactly this integration pattern. It starts the tray icon without blocking and returns control, allowing uvicorn's event loop to own the main thread. Alternatively, run uvicorn in a `threading.Thread(daemon=True)` and call `icon.run()` from the main thread; use a `threading.Event` to coordinate startup.

Recommended pattern:
```python
import threading
import uvicorn
import pystray

server_ready = threading.Event()

def start_uvicorn():
    uvicorn.run(app, host="127.0.0.1", port=8765)

thread = threading.Thread(target=start_uvicorn, daemon=True)
thread.start()
# pystray owns the main thread
icon.run(setup=lambda icon: server_ready.set())
```

**Warning signs:**
- Service starts but system tray icon never appears
- Service appears to hang on startup (process visible in Task Manager but no HTTP responses)
- `RuntimeError: Cannot close a running event loop` on shutdown
- `asyncio.exceptions.CancelledError` in uvicorn logs during shutdown

**Phase to address:** Phase 1 (Service skeleton / process architecture)

---

### Pitfall 2: Windows Asyncio Event Loop Policy Breaks Uvicorn

**What goes wrong:**
On Windows, Python 3.10+ defaults to `ProactorEventLoop`, but uvicorn 0.36.0+ has changed its own event loop policy handling in ways that break compatibility with code that manually sets `asyncio.WindowsSelectorEventLoopPolicy()`. The result is `NotImplementedError` when the service tries to start, or silent failures where the server never binds to a port.

**Why it happens:**
uvicorn internally sets the event loop policy at startup. If your code sets a policy first (e.g., to fix a different issue), uvicorn may override or conflict with it. On Windows, `ProactorEventLoop` does not support `add_signal_handler()`, which is used internally by uvicorn for graceful shutdown. This means `CTRL+C` handling can propagate to all child processes in the terminal session (known uvicorn Windows bug).

**How to avoid:**
- Do not manually set the event loop policy. Let uvicorn manage it.
- Use `uvicorn.Server` class directly with a config object for programmatic control, rather than `uvicorn.run()` (which is designed for CLI use).
- Avoid `reload=True` entirely — it uses subprocess spawning that breaks on Windows with ProactorEventLoop.
- Run uvicorn in a daemon thread with `loop="none"` or let it manage its own loop:

```python
config = uvicorn.Config(app, host="127.0.0.1", port=8765, loop="asyncio")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
```

**Warning signs:**
- `NotImplementedError` on startup mentioning event loop or subprocess transport
- `RuntimeError: This event loop is already running` when starting uvicorn
- Server appears to start (no errors) but HTTP requests time out immediately
- Port is not bound (confirmed via `netstat -an | findstr 8765`)

**Phase to address:** Phase 1 (Service skeleton), then verify in Phase 2 (HTTP endpoint integration)

---

### Pitfall 3: Kokoro ONNX Runtime Version Conflicts

**What goes wrong:**
`kokoro-onnx` requires `onnxruntime>=1.20.1`. If the user's Python environment already has an older `onnxruntime` installed (e.g., from another AI project requiring `onnxruntime==1.16.x`), pip will either fail with a dependency conflict or — worse — silently install kokoro-onnx against an incompatible runtime that crashes at inference time with a cryptic C++ error about operator version mismatches.

**Why it happens:**
`onnxruntime` has a strict model compatibility matrix between the runtime version and the `.onnx` file's opset version. Kokoro's ONNX models use opset 14+ features that older runtimes do not support. The error does not surface at import time; it surfaces when the model is first loaded or when inference runs.

**How to avoid:**
- Always install into a dedicated virtual environment. Non-negotiable for this project.
- Pin `onnxruntime` explicitly in `requirements.txt` to a version known to work: `onnxruntime>=1.20.1,<2.0`.
- Check for conflicts before first run: `pip check` will reveal version conflicts immediately.
- At startup, validate onnxruntime version programmatically: `import onnxruntime; assert tuple(int(x) for x in onnxruntime.__version__.split('.')[:2]) >= (1, 20)`.

**Warning signs:**
- `onnxruntime.capi.onnxruntime_pybind11_state.InvalidGraph` on model load
- `Invalid model: The model requires opset version X` errors
- `pip install kokoro-onnx` emits warnings about package conflicts but succeeds anyway
- `pip check` shows errors after installation

**Phase to address:** Phase 1 (Installation script), Phase 2 (Kokoro integration)

---

### Pitfall 4: Kokoro First-Load Latency Is Seconds, Not Milliseconds

**What goes wrong:**
The Kokoro ONNX model (FP32 variant: 310MB) takes 3–8 seconds to load from disk and initialize the ONNX runtime session on first use. If the service loads the model lazily (on the first HTTP request), the first speech synthesis call will appear to hang. Users will assume the service is broken and kill it.

There is also a per-inference warmup: the first inference call after model load takes 2–5x longer than subsequent calls due to ONNX Runtime's JIT kernel compilation.

**Why it happens:**
Developers test locally with the model already warm in filesystem cache. CI/CD or fresh installs see cold-start times. Additionally, ONNX Runtime's CPU execution provider compiles kernels on first use — this is expected behavior but undocumented in kokoro-onnx.

**How to avoid:**
- Load the model eagerly at service startup, not on first request.
- After loading, run one short synthesis ("hello") as a warmup before marking the service as ready.
- Expose a `/health` endpoint that returns 503 until warmup completes, so the Claude Code hook can wait before sending real text.
- Use INT8 quantized model (88MB) for 3–4x faster load and inference on CPU if quality is acceptable.
- Log startup timing: `INFO: Kokoro model loaded in X.Xs, warmup complete`.

**Warning signs:**
- First TTS request from Claude Code produces no audio and times out
- Service logs show a long pause between "loading model" and "ready" log lines
- HTTP requests during load return 200 with 0-byte audio

**Phase to address:** Phase 2 (Kokoro integration), Phase 3 (Health/readiness checks)

---

### Pitfall 5: Piper Is Archived and Has DLL/Binary Issues on Windows

**What goes wrong:**
The `rhasspy/piper` repository was archived by its owner on October 6, 2025 and is now read-only. The `piper-tts` PyPI package has conflicting dependencies between v1.1.0 and v1.2.0 (incompatible `piper-phonemize` versions). The Windows binary distribution requires the piper.exe to be in PATH or referenced by absolute path; when called via `subprocess`, it may silently produce no output if the binary cannot find its bundled DLLs.

**Why it happens:**
Piper's Windows binary bundles DLLs (onnxruntime, espeak-ng) that must reside in the same directory as `piper.exe`. If the exe is called from a different working directory or if the PATH is not set correctly, Windows cannot find the DLLs (DLL search order issue). The project being archived means these known issues will not be fixed.

**How to avoid:**
- Use Kokoro as the primary (and only v1) TTS engine. Piper support is explicitly higher-risk given its archived status.
- If Piper must be supported, call the binary using an absolute path with `cwd=` set to the directory containing `piper.exe`, not the project root.
- Never use `piper-tts` pip package for Windows — use the binary release from GitHub. The pip package's phonemize dependency conflicts make it unreliable.
- Always ship Piper with its DLLs in the same subdirectory. Never add just `piper.exe` to PATH without its dependencies alongside it.

**Warning signs:**
- `piper.exe` runs the `-h` flag fine but produces no audio output (DLL load failure is silent)
- `pip install piper-tts` warns about conflicting dependencies
- subprocess call to piper exits with code 0 but audio file is empty or missing

**Phase to address:** Phase 2 (TTS engine integration) — flag Piper as secondary priority

---

### Pitfall 6: Windows Audio Exclusive Mode Blocks TTS Playback

**What goes wrong:**
If the user has their audio device configured in WASAPI exclusive mode (common for audiophile setups, gaming headsets, or DACs), importing `sounddevice` momentarily interrupts any currently playing audio. More critically, if another application (e.g., a game, DAW, or Discord with exclusive mode) holds the audio device exclusively, `sounddevice` cannot open an output stream and raises `sounddevice.PortAudioError: Error opening OutputStream`.

Additionally, TTS models output audio at 24000 Hz (Kokoro) or 22050 Hz (Piper), while Windows default device sample rate is typically 44100 Hz or 48000 Hz. In WASAPI shared mode without `auto_convert=True`, this causes `PortAudioError: Invalid device` or distorted audio at wrong playback speed.

**Why it happens:**
Windows WASAPI shared mode requires the application to match the device's configured sample rate. WASAPI exclusive mode prevents any other application from accessing the device. The PortAudio/sounddevice layer does not handle this gracefully — it throws an exception rather than falling back.

**How to avoid:**
- Always use `sd.play(audio, samplerate=24000, extra_settings=sd.WasapiSettings(auto_convert=True))` to enable WASAPI's built-in sample rate conversion in shared mode.
- Wrap all audio playback in `try/except sounddevice.PortAudioError` with a clear error log: "Audio device busy or in exclusive mode — cannot play TTS".
- Do NOT use exclusive mode (`exclusive=True`) — this is the wrong direction for a background service.
- Test on a machine with a gaming headset configured as default device, as these commonly use exclusive mode.

**Warning signs:**
- TTS synthesis succeeds (audio data generated) but no sound plays
- `PortAudioError` in logs with "Invalid device" or "Unanticipated host error"
- Audio plays but at wrong pitch/speed (sample rate mismatch without auto_convert)
- Other applications lose audio briefly when the service starts

**Phase to address:** Phase 2 (Audio playback), Phase 3 (Error handling)

---

### Pitfall 7: Hook Payload Does NOT Contain Raw Assistant Text Directly — Use `last_assistant_message`

**What goes wrong:**
Developers assume the `Stop` hook payload contains the full conversation transcript or that they need to parse the `transcript_path` file to extract the assistant's last message. They build transcript parsing logic that is fragile against format changes. Or they use `PostToolUse` thinking it fires with assistant text — but `PostToolUse` fires with tool execution results, not the assistant's conversational response.

**Why it happens:**
The hook event naming is not obvious. `Stop` fires when Claude finishes responding, and it includes `last_assistant_message` directly in the payload — no transcript parsing needed. Many hook tutorial examples focus on `PreToolUse`/`PostToolUse` for code checks, leaving the `Stop` hook underdocumented for this use case.

**How to avoid:**
- Use the `Stop` hook with the `last_assistant_message` field — this is exactly the text of Claude's final response.
- Do not parse the transcript file for this purpose; it is a JSONL file that changes format between Claude Code versions.
- The `last_assistant_message` field already contains only the assistant's text, stripped of tool calls and metadata.
- Read stdin as UTF-8: `import sys; payload = json.loads(sys.stdin.buffer.read().decode('utf-8'))`.

Confirmed payload structure (HIGH confidence — from official docs):
```json
{
  "hook_event_name": "Stop",
  "last_assistant_message": "I've completed the refactoring. Here's a summary...",
  "stop_hook_active": false,
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../abc123.jsonl",
  "cwd": "/Users/..."
}
```

**Warning signs:**
- Hook script tries to read a file at `transcript_path` on every invocation (slow, fragile)
- Hook sends empty text to TTS service (field name typo or wrong event type)
- TTS speaks tool result JSON like `{"success": true, "filePath": "..."}` instead of assistant prose

**Phase to address:** Phase 2 (Hook integration)

---

### Pitfall 8: Python Hook Script stdin Encoding on Windows (CP1252 vs UTF-8)

**What goes wrong:**
On Windows, Python's `sys.stdin` defaults to the Windows console code page (CP1252 or the system ANSI code page), not UTF-8. When the hook payload JSON contains Unicode characters (non-ASCII in assistant messages), `json.loads(sys.stdin.read())` raises `UnicodeDecodeError` or silently corrupts the text. Claude Code itself has a documented UTF-8 BOM bug in config files that causes `SyntaxError: Unexpected token 'C', "Claude con..."`.

**Why it happens:**
Windows console code page defaults differ from Linux/macOS. Claude Code sends the hook payload as UTF-8 on stdin, but Python's stdin text wrapper uses the system locale encoding to decode bytes. Non-ASCII characters (em dash, smart quotes, code snippets with special chars) trigger the mismatch.

**How to avoid:**
- ALWAYS read stdin as raw bytes and decode explicitly:
  ```python
  import sys, json
  payload = json.loads(sys.stdin.buffer.read().decode('utf-8'))
  ```
- Set `PYTHONIOENCODING=utf-8` in the hook environment or at the top of the script:
  ```python
  import io, sys
  sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
  ```
- Add a shebang or explicit encoding declaration. Test with an assistant message containing em dashes, quotes, and Unicode.
- Do not save hook scripts with UTF-8 BOM. Use VS Code or any modern editor configured to save as "UTF-8 without BOM".

**Warning signs:**
- Hook crashes silently on messages with smart quotes or non-ASCII characters
- TTS service receives garbled text for inputs containing special characters
- `UnicodeDecodeError: 'charmap' codec can't decode byte` in hook stderr

**Phase to address:** Phase 2 (Hook integration)

---

### Pitfall 9: Service Leaves Zombie Processes on Crash or Restart

**What goes wrong:**
When the ClaudeTalk service is killed (Task Manager, power cycle, or crash), the `pythonw.exe` process may leave orphaned child processes — particularly if the service spawned subprocesses (e.g., for Piper binary invocation). On restart, the new service instance tries to bind port 8765, gets `[WinError 10048] Only one usage of each socket address is normally permitted`, and fails to start.

**Why it happens:**
Windows does not have the Unix process group / SIGKILL + reap behavior. Subprocesses started with `subprocess.Popen()` without explicit cleanup are not killed when the parent terminates abnormally. Port binding failures are the most common symptom — the old process holds the socket.

**How to avoid:**
- Write the service PID to a lock file on startup: `~/.claudetalk/service.pid`.
- On startup, read the lock file, check if the PID is still running, and kill it if so before rebinding.
- Use `subprocess.Popen(..., creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)` for any child processes so they can be targeted for kill independently.
- Register a `signal.signal(signal.SIGTERM, graceful_shutdown)` handler and an `atexit.register(cleanup)` function.
- In the pystray menu "Stop" action, use `os.kill(os.getpid(), signal.SIGTERM)` rather than `sys.exit()`.

**Warning signs:**
- Service fails to start with `[WinError 10048] address already in use`
- Multiple `python.exe` or `pythonw.exe` processes in Task Manager after a crash
- `/claudetalk:start` slash command appears to succeed but service is unreachable

**Phase to address:** Phase 1 (Service skeleton), Phase 3 (Error recovery)

---

### Pitfall 10: Text Sent to TTS Contains Unspoken Junk (Code, JSON, Markdown)

**What goes wrong:**
The `last_assistant_message` from Claude Code contains Markdown formatting: code blocks (` ```python ... ``` `), inline code (`code`), bold (`**text**`), bullet points, JSON blobs, file paths, URLs, and tool result summaries. If sent verbatim to TTS, the result is either:
- Robot reading out "backtick backtick backtick python backtick backtick backtick"
- Minutes of code being slowly dictated letter-by-letter
- JSON structure like `{"success": true, "filePath": "..."}` spoken aloud

**Why it happens:**
The `Stop` hook fires with the full assistant response text, which is written for visual consumption. Claude Code outputs rich Markdown. TTS models treat all input as speech-worthy text.

**How to avoid:**
Apply a text preprocessing pipeline before sending to TTS:

1. **Strip fenced code blocks entirely** — replace ` ```...``` ` with "[code block omitted]" or nothing. Code is never useful spoken.
2. **Strip inline code** — replace `\`code\`` with the plain text inside, or omit short snippets entirely.
3. **Strip Markdown formatting** — remove `**bold**`, `*italic*`, `### Headers`, `- bullets`, `> quotes`.
4. **Truncate extremely long messages** — if `last_assistant_message` exceeds ~500 words, speak only the first 2–3 sentences plus "and more."
5. **Skip pure JSON/XML responses** — if the message starts with `{` or `<`, it is likely a tool result that leaked through; skip it.
6. **Normalize punctuation** — replace `...` with a pause, strip URLs (speak "link" instead), strip file paths.

Example minimal filter:
```python
import re

def filter_for_tts(text: str) -> str:
    # Remove fenced code blocks
    text = re.sub(r'```[\s\S]*?```', '[code omitted]', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Remove markdown formatting
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r'\n{2,}', ' ', text)
    return text.strip()
```

**Warning signs:**
- TTS reads out "pound pound pound" for headers
- Long silence followed by code being spelled out
- Users complain that every response sounds like reading a manual

**Phase to address:** Phase 2 (Hook integration and text preprocessing)

---

### Pitfall 11: pythonw.exe vs python.exe: No Console = No Error Visibility

**What goes wrong:**
Running the service with `pythonw.exe` hides the console window (desired behavior), but it also discards all `print()` output and unhandled exception tracebacks. When the service silently crashes, there is no way to know why. The service PID disappears from Task Manager and the system tray icon vanishes, with no error message.

**Why it happens:**
`pythonw.exe` suppresses stdout and stderr by default. Any exception that propagates to the top level is silently swallowed. Developers test with `python.exe` (where they see errors), then switch to `pythonw.exe` for deployment without adding logging.

**How to avoid:**
- Add file-based logging from day one using Python's `logging` module:
  ```python
  import logging
  logging.basicConfig(
      filename=Path.home() / '.claudetalk' / 'service.log',
      level=logging.DEBUG,
      format='%(asctime)s %(levelname)s %(message)s'
  )
  ```
- Wrap the service entry point in a top-level `try/except Exception as e: logging.exception("Fatal crash")`.
- Log all startup steps: model load start/end, server bind, tray icon creation.
- Provide a "View log" option in the pystray menu.
- During development, use `python.exe` and only switch to `pythonw.exe` for testing the production startup path.

**Warning signs:**
- Service disappears silently with no error
- System tray icon never appears after `/claudetalk:start`
- Log file is empty or does not exist (logging not configured before the crash point)

**Phase to address:** Phase 1 (Service skeleton — logging must be the first thing initialized)

---

### Pitfall 12: PowerShell Execution Policy Blocks Hook Script on Windows

**What goes wrong:**
Claude Code hooks run as shell commands. On Windows, if the hook is a `.ps1` PowerShell script or the hook command is invoked through PowerShell and the execution policy is `Restricted` (Windows default), the hook fails silently or with a policy error. The service is never started because the `SessionStart` hook never executes.

**Why it happens:**
Windows PowerShell's default execution policy blocks unsigned scripts. Claude Code runs hooks through the shell, which on Windows uses cmd.exe or PowerShell depending on configuration. A Python script invoked as a hook with `python /path/to/hook.py` avoids this, but a `.ps1` hook does not.

**How to avoid:**
- Write the Claude Code hook as a Python script (`hook.py`), not a PowerShell script.
- Invoke it via: `"command": "python \"%USERPROFILE%\\.claude\\hooks\\claudetalk-hook.py\""`.
- Alternatively, use `pythonw.exe` to avoid any console flicker: `"command": "pythonw \"%USERPROFILE%\\.claude\\hooks\\claudetalk-hook.py\""`.
- Never require the user to change PowerShell execution policy. Use Python hooks universally.
- Test the hook command directly in cmd.exe before wiring into Claude Code settings.

**Warning signs:**
- `SessionStart` hook appears configured but service never starts with Claude Code
- Running the hook command manually in cmd.exe works, but Claude Code's invocation does not
- Claude Code shows no error about the hook (hooks fail silently by default unless exit 2)

**Phase to address:** Phase 2 (Claude Code hook integration)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Global Python install (no venv) | Simpler install step | ONNX version conflicts with user's other AI tools; pip install breaks other projects | Never — always use venv |
| Lazy model loading (on first request) | Faster service startup | First TTS call hangs for 3–8 seconds; users think service is broken | Never — eager load with warmup |
| Reading transcript file instead of `last_assistant_message` | Access to full history | Fragile against Claude Code internal format changes; slow file I/O per message | Never — use `last_assistant_message` |
| No PID lock file | Simpler startup code | Port conflicts on restart; zombie processes block the service | Never — implement from Phase 1 |
| Skipping text preprocessing | Less code | Users hear code blocks read aloud; extremely poor UX | Never — basic filter is 20 lines |
| `python.exe` instead of `pythonw.exe` | Console visible for debugging | Console window flashes on every Claude Code response | MVP only; switch before release |
| No startup logging | Simpler code | Impossible to debug silent crashes in pythonw.exe | Never — logging costs nothing |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Code `Stop` hook | Using `PostToolUse` to intercept assistant text | Use `Stop` hook — it fires when Claude finishes and provides `last_assistant_message` directly |
| Claude Code `SessionStart` hook | Starting service synchronously (blocks Claude Code startup) | Use `async: true` on the hook or start service as a detached subprocess |
| sounddevice on Windows | Using `sd.play(audio, 24000)` without `auto_convert` | Use `sd.play(audio, 24000, extra_settings=sd.WasapiSettings(auto_convert=True))` |
| kokoro-onnx model download | Downloading at runtime on every install | Bundle model download in install script; check `~/.claudetalk/models/` before downloading |
| piper binary | Adding only `piper.exe` to PATH | Bundle piper with ALL its DLLs in the same directory; call via absolute path |
| Hook JSON output | Mixing print() and JSON output | Hook stdout must contain ONLY the JSON object; any other print breaks parsing |
| uvicorn shutdown | `sys.exit()` inside tray menu callback | Set `server.should_exit = True` on the uvicorn Server object to trigger graceful shutdown |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synthesizing full long response as one chunk | 10–30 second delay before audio starts | Sentence-chunk the text; speak each sentence as it is synthesized | Any response over ~100 words |
| Audio playback blocking the HTTP handler | Next Claude Code message queued waiting for audio to finish | Run `sd.play()` with `blocking=False` or in a separate thread; queue requests | Second rapid Claude message |
| Model loaded on every request | Service unusably slow | Load model once at startup; keep session alive | Every request |
| Tight loop checking `sd.get_stream()` | 100% CPU during playback | Use `sd.wait()` or event-based checking | Any audio playback |
| Large `last_assistant_message` to TTS | Minutes of audio synthesized, never finishes | Hard-limit text to first N sentences before TTS | Claude responses >500 words |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Binding HTTP service to `0.0.0.0` instead of `127.0.0.1` | Any process or network host can trigger TTS playback | Bind exclusively to `127.0.0.1`; no auth needed if localhost-only |
| No validation on `/speak` endpoint payload | Any local process can send arbitrary text to be spoken; trivially abused by malicious scripts | Validate payload size (<10KB max); rate-limit endpoint; accept only plain text |
| Hook command runs arbitrary user input | If hook payload is malformed, injection possible | Parse JSON strictly; never interpolate hook payload fields into shell commands |
| Log file contains full assistant messages | Privacy: conversation content written to disk | Log only metadata (message length, duration, error types); not message content |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Speaking code blocks verbatim | Users hear "backtick backtick backtick python" for every code example | Strip all code blocks before TTS; replace with "[code omitted]" or nothing |
| No way to interrupt speech mid-sentence | User must wait for a 30-second response to finish before terminal is usable | Implement `/claudetalk:stop-speech` or kill current `sd.play()` on new request |
| Silent crash with no feedback | User doesn't know service is dead; keeps sending messages | Show Windows notification balloon on crash; write to log; tray icon changes to red |
| Slow startup blocks Claude Code session | Claude Code waits for `SessionStart` hook if not async | Make SessionStart hook fire-and-forget (`async: true`); service starts independently |
| Speaking every tool result/error | Noisy: every `git push` failure spoken aloud | Only `Stop` hook provides assistant prose; never speak PostToolUse content for TTS |

---

## "Looks Done But Isn't" Checklist

- [ ] **Model loading:** Service starts without error — but is the model actually loaded, or deferred to first request? Verify by checking logs for "warmup complete".
- [ ] **Audio playback:** TTS generates audio bytes — but does it actually play? Test on a machine with WASAPI shared mode, then exclusive mode.
- [ ] **Hook wiring:** Hook file exists and is configured — but does it actually fire? Test by running the hook command directly in cmd.exe, then verify via Claude Code's verbose mode (Ctrl+O).
- [ ] **Zombie prevention:** Service starts and stops cleanly in dev — but what happens on crash? Kill it with Task Manager, then try to restart. Does port 8765 rebind successfully?
- [ ] **Text filtering:** Filter passes unit tests — but test with a real multi-paragraph Claude response containing code blocks. Does the spoken output make sense?
- [ ] **Encoding:** Hook works with ASCII text — but test with a message containing em dash, smart quotes, or the word "café". Does it crash?
- [ ] **pythonw.exe mode:** Works with python.exe — but test the exact startup path used in production (pythonw.exe, via shortcut or hook). Does it still start?

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| pystray/uvicorn thread deadlock | MEDIUM | Rewrite service startup to use `run_detached()` pattern; 2–4 hours |
| ONNX version conflict in user env | LOW | Document venv requirement; add `pip check` to install script; 30 minutes |
| Kokoro first-load latency complaints | LOW | Add eager load + warmup + `/health` endpoint; 1–2 hours |
| Zombie process port conflict | LOW | Add PID lock file logic; 1 hour |
| Text filtering missing edge case | LOW | Extend regex filter; add test cases; 30 minutes per case |
| Encoding crash on Unicode | LOW | Fix stdin.buffer.read() pattern; 15 minutes |
| Piper DLL hell | HIGH | Deprioritize Piper; defer to post-v1 or drop entirely |
| Audio exclusive mode blocks playback | MEDIUM | Add WASAPI auto_convert + try/except + user-facing error message; 1–2 hours |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| pystray/uvicorn thread deadlock | Phase 1 (service skeleton) | Service starts, tray icon appears, HTTP responds — all simultaneously |
| Windows asyncio event loop conflict | Phase 1 (service skeleton) | `netstat` confirms port bound; no NotImplementedError in logs |
| ONNX version conflict | Phase 1 (install script) | `pip check` passes; `onnxruntime.__version__ >= "1.20.1"` |
| Kokoro first-load latency | Phase 2 (Kokoro integration) | `/health` returns 503 during load, 200 after warmup |
| Piper DLL/archived status | Phase 2 (TTS integration) | Consider Kokoro-only for v1; flag Piper as future work |
| Audio exclusive mode blocking | Phase 2 (audio playback) | Test with gaming headset in exclusive mode; graceful error logged |
| Wrong hook event type | Phase 2 (hook integration) | Stop hook fires and `last_assistant_message` is non-empty for assistant responses |
| Windows stdin encoding | Phase 2 (hook integration) | Hook handles message with em dash and Unicode; no UnicodeDecodeError |
| Zombie processes on crash | Phase 1 + Phase 3 (error recovery) | Kill process, restart; service binds port on second attempt |
| No logging in pythonw.exe | Phase 1 (service skeleton) | Log file created at `~/.claudetalk/service.log`; crash reason visible |
| PowerShell execution policy | Phase 2 (hook integration) | Hook is Python script, not .ps1; executes without policy change |
| Text junk in TTS | Phase 2 (text preprocessing) | Real Claude Code response with code block: only prose is spoken |

---

## Sources

- [Claude Code Hooks Reference — official docs](https://code.claude.com/docs/en/hooks) — HIGH confidence
- [Stop hook `last_assistant_message` field — official docs](https://code.claude.com/docs/en/hooks) — HIGH confidence
- [kokoro-onnx pyproject.toml — onnxruntime>=1.20.1, Python 3.10–3.13](https://github.com/thewh1teagle/kokoro-onnx/blob/main/pyproject.toml) — HIGH confidence
- [piper archived October 2025](https://github.com/rhasspy/piper/issues/821) — HIGH confidence
- [Piper Windows binary PATH/DLL issues](https://github.com/rhasspy/piper/issues/272) — MEDIUM confidence
- [piper-tts dependency conflicts](https://github.com/rhasspy/piper/issues/509) — HIGH confidence (multiple reports)
- [sounddevice exclusive mode interrupts audio on Windows](https://github.com/spatialaudio/python-sounddevice/issues/496) — HIGH confidence (official repo issue)
- [sounddevice WASAPI sample rate mismatch fix](https://github.com/spatialaudio/python-sounddevice/issues/52) — HIGH confidence
- [sounddevice WASAPI auto_convert docs](https://python-sounddevice.readthedocs.io/en/latest/api/platform-specific-settings.html) — HIGH confidence
- [pystray threading — Windows safe in thread; run_detached for event loop integration](https://pystray.readthedocs.io/en/latest/usage.html) — HIGH confidence
- [uvicorn Windows ProactorEventLoop issues](https://github.com/Kludex/uvicorn/issues/1220) — MEDIUM confidence
- [uvicorn 0.36.0+ WindowsSelectorEventLoopPolicy broken](https://github.com/Kludex/uvicorn/discussions/2749) — MEDIUM confidence
- [Claude Code UTF-8 BOM / JSON parse error on Windows](https://github.com/anthropics/claude-code/issues/14442) — HIGH confidence
- [Kokoro ONNX CPU benchmark — warmup behavior documented](https://gist.github.com/efemaer/23d9a3b949b751dde315192b4dcf0653) — MEDIUM confidence
- [Open-webui TTS markdown/code filtering discussion](https://github.com/open-webui/open-webui/discussions/6920) — MEDIUM confidence (community pattern)
- [Python subprocess CREATE_NO_WINDOW — pythonw.exe background process](https://medium.com/@maheshwar.ramkrushna/running-python-scripts-as-background-processes-using-subprocess-pythonw-exe-and-other-methods-ed5316dd5256) — MEDIUM confidence

---
*Pitfalls research for: Windows Python TTS background service (ClaudeTalk)*
*Researched: 2026-02-26*

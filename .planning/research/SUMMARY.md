# Project Research Summary

**Project:** AgentTalk
**Domain:** Windows local TTS background service — Claude Code voice output companion
**Researched:** 2026-02-26
**Confidence:** HIGH

## Executive Summary

AgentTalk is a Windows background service that speaks Claude Code's assistant responses aloud using local TTS. The product sits in a narrow but well-understood niche: it is an event-driven audio relay built around Claude Code's official hook system, not a general-purpose screen reader or voice assistant. The correct architecture is a single Python process with three concurrent components — a pystray icon owning the main thread, a uvicorn/FastAPI HTTP server in a daemon thread, and a TTS worker queue in a second daemon thread — communicating via a bounded `queue.Queue`. This architecture is dictated by platform constraints: the Win32 message loop that pystray needs, the asyncio event loop that uvicorn runs, and the blocking audio playback that sounddevice performs must each be isolated from the others. There are no architectural alternatives; everything else produces deadlocks or crashes.

The recommended TTS engine is kokoro-onnx (0.5.0) over Python 3.11. Kokoro produces high-quality neural speech without cloud dependencies and ships as a pure Python + ONNX package with no system-level espeak-ng install required. The Claude Code `Stop` hook provides `last_assistant_message` directly in its stdin payload — no transcript parsing is needed. Before the text reaches TTS, a preprocessing pipeline must strip code blocks, inline code, URLs, file paths, and markdown formatting; without this filter the tool is actively annoying and unusable as a daily driver. Installation should be `pip install agenttalk` followed by `agenttalk setup` to download model files and register hooks.

The primary risks are Windows-specific and well-understood: the pystray/uvicorn thread model must be implemented exactly once and correctly (the wrong threading layout produces silent deadlocks); Kokoro's ONNX model takes 3-8 seconds to load and must be eagerly loaded with a warmup call before the service accepts traffic; and the service must use a PID lock file to prevent port conflicts on crash restart. Piper TTS is explicitly lower priority because its upstream repository was archived in October 2025 and its Windows binary distribution has documented DLL search path issues. Kokoro should be the sole v1 TTS engine.

## Key Findings

### Recommended Stack

The stack is narrow and purpose-built. Python 3.11 is the required runtime — 3.12+ triggers a documented GIL crash in pystray 0.19.5, and there is no fix released as of the research date. The primary TTS engine is kokoro-onnx 0.5.0, which bundles espeak-ng data via the `espeakng-loader` dependency and returns float32 numpy arrays that sounddevice can play directly without format conversion. FastAPI 0.133.1 with uvicorn 0.41.0 provides the HTTP server layer with built-in `BackgroundTasks` for fire-and-forget audio dispatch. pystray 0.19.5 provides the system tray icon with Pillow handling icon image rendering.

All dependencies ship prebuilt Windows wheels for x86-64. The only manual download step is the Kokoro model files (~310MB ONNX + ~26MB voices binary from GitHub Releases), which cannot be bundled in the pip package due to size. Cloud-dependent TTS alternatives (gTTS, edge-tts, pyttsx3) are explicitly ruled out.

**Core technologies:**
- Python 3.11: Runtime — only version free of the pystray GIL crash bug
- kokoro-onnx 0.5.0: Primary TTS — pure Python/ONNX, no espeak-ng system install, high quality
- FastAPI 0.133.1 + uvicorn 0.41.0: HTTP server — async-native, BackgroundTasks built-in
- sounddevice 0.5.5: Audio playback — plays numpy arrays directly, PortAudio bundled in Windows wheel
- pystray 0.19.5 + Pillow: System tray — cross-platform, minimal dependencies
- httpx or urllib.request: Hook HTTP client — hook scripts must be lightweight, no heavy imports

### Expected Features

The feature set splits cleanly into two buckets. The P1 features are non-negotiable: without the Stop hook + text filter + TTS endpoint + mute toggle + tray icon + auto-launch, the product has no usable core. The P2 features (voice switching, model switching, sentence chunking, tray status indicator) add meaningful value but can wait for post-launch validation.

**Must have (table stakes):**
- Stop hook extraction + `/speak` endpoint — the entire value proposition; nothing else matters without this
- Text filtering pipeline — strips code blocks, inline code, URLs, file paths, markdown before TTS; without this every response sounds like a manual being read aloud
- System tray icon with Quit — Windows UX standard; background services must have a visible presence and an exit path
- Mute/unmute toggle — first thing users reach for when sound becomes inconvenient; needed at launch
- SessionStart auto-launch hook — users should never manually start the service
- `pip install agenttalk` + `agenttalk setup` — single-command install is the only acceptable pattern for the developer target audience

**Should have (competitive differentiators):**
- Voice switching via slash command — inline voice change without leaving the task
- Model switching (Kokoro vs Piper) — quality vs speed tradeoff at runtime (Piper deferred; see pitfalls)
- Tray speaking status indicator — visual feedback during TTS playback
- Sentence-chunked delivery — start speaking first sentence immediately instead of waiting for full synthesis

**Defer to v2+:**
- Piper TTS backend — archived upstream, DLL issues on Windows; not worth v1 risk
- Multi-language voice packs — no confirmed user need; adds model management complexity
- Transcript playback / "read that again" — only needed if TTS reliability proves poor
- GUI configuration panel — slash commands satisfy developer audience; GUI doubles scope
- Streaming TTS mid-response — impossible via Claude Code hooks; hooks only fire at Stop time

### Architecture Approach

The architecture is a single Python process with three layers coordinated through threading primitives. pystray owns the main thread via `Icon.run(setup=start_background_services)`, where the `setup` callback starts uvicorn in Thread 1 and the TTS worker in Thread 2 as daemon threads. The FastAPI `/speak` endpoint enqueues text into a bounded `queue.Queue(maxsize=3)` and returns immediately. The TTS worker dequeues, sentence-splits, synthesizes sentence-by-sentence with Kokoro, and plays with `sd.play()` + `sd.wait()`. Config is persisted as JSON in `%APPDATA%\AgentTalk\config.json`. A PID file at `%APPDATA%\AgentTalk\service.pid` enables crash detection and zombie cleanup on restart.

The hook scripts are thin relay scripts that must not import heavy libraries. The Stop hook reads `last_assistant_message` from stdin JSON and fires an HTTP POST to `127.0.0.1:5050/speak`. The SessionStart hook checks the PID file and launches the service with `subprocess.Popen(..., creationflags=subprocess.DETACHED_PROCESS)` if not running. Both hooks must be configured with `"async": true` so they do not block Claude Code's UI.

**Major components:**
1. Claude Code hooks (`speak.py`, `ensure_running.py`) — thin relay scripts; read stdin JSON, POST to service; exit 0 immediately
2. FastAPI HTTP server (uvicorn, Thread 1) — accepts `/speak /stop /status /voice` endpoints; enqueues text; returns immediately
3. TTS worker (Thread 2) — bounded queue consumer; sentence-splits; synthesizes with Kokoro; plays audio sequentially
4. pystray tray icon (Main Thread) — Win32 message loop; right-click menu for mute/voice/quit; visual service presence
5. Config store (`%APPDATA%\AgentTalk\`) — JSON config + PID file; writable without admin rights
6. TTS model adapters (`models/kokoro.py`) — common interface `synthesize(text, voice, speed) -> (np.ndarray, int)`

### Critical Pitfalls

1. **pystray/uvicorn thread deadlock** — Run pystray in main thread via `Icon.run(setup=fn)` and uvicorn in a daemon thread. Never run both `Icon.run()` and `uvicorn.run()` from competing threads. Use `pystray.Icon.run_detached()` or the `setup=` callback as the integration point.

2. **Kokoro first-load latency (3-8 seconds)** — Load the model eagerly at service startup, run a warmup synthesis call, and expose `/health` returning 503 until ready. Never defer model loading to first request or users will assume the service is broken.

3. **Windows asyncio event loop conflict** — Do not manually set the asyncio event loop policy. Use `uvicorn.Server(config)` directly in a daemon thread with `loop="asyncio"` in the Config. Never use `reload=True` (breaks ProactorEventLoop on Windows).

4. **Text junk in TTS** — Apply the full preprocessing pipeline before sending to TTS: strip fenced code blocks, inline code, URLs, file paths, markdown markers, and skip sentences that are mostly non-alphabetic. This is non-negotiable; it requires ~30 lines of regex and must be built in Phase 2.

5. **Zombie processes blocking port rebind** — Implement PID lock file from Phase 1. On startup, check if the existing PID is alive and kill it before binding. Use `atexit.register()` and a signal handler to delete the PID file on clean exit. Never skip this; port conflicts are the most common crash recovery failure.

6. **Windows stdin encoding (CP1252 vs UTF-8)** — Always read hook stdin as `sys.stdin.buffer.read().decode('utf-8')`. Python's default text stdin uses the system ANSI code page on Windows; Claude Code sends UTF-8. Non-ASCII in assistant messages will cause `UnicodeDecodeError` if this is not done from day one.

7. **pythonw.exe silences all errors** — Configure file-based logging as the absolute first action in `service.py`, before any imports that might fail. Log all startup steps. Wrap the entry point in `try/except Exception: logging.exception("Fatal crash")`. Without this, crashes are completely invisible.

## Implications for Roadmap

Based on the dependency graph in ARCHITECTURE.md and the pitfall-to-phase mapping in PITFALLS.md, six phases are suggested. The ordering is driven by risk: Phase 1 validates the hardest Windows-specific unknowns before any feature work begins. Phases proceed from core audio pipeline outward to integration, UX, then packaging.

### Phase 1: Service Skeleton and Core Audio

**Rationale:** The threading model (pystray + uvicorn + TTS worker), the Windows process launch pattern (`pythonw.exe` + `DETACHED_PROCESS`), and Kokoro model loading are all high-risk unknowns that must be validated before building anything on top. Every subsequent phase depends on these working correctly. Building tray + hooks + TTS simultaneously produces debugging nightmares when any one of them fails.

**Delivers:** A working service that loads Kokoro, synthesizes audio from hardcoded text, and plays it through speakers — no HTTP, no hooks, no tray yet. Also establishes the logging infrastructure and PID file pattern.

**Addresses:** Auto-start capability (foundation), basic TTS output (foundation for all features)

**Avoids:** Pitfall 1 (pystray/uvicorn deadlock), Pitfall 2 (asyncio event loop conflict), Pitfall 4 (first-load latency), Pitfall 7 (no logging in pythonw.exe), Pitfall 9 (zombie processes)

**Standard patterns:** Yes — all of these are documented threading patterns. No phase research needed.

### Phase 2: FastAPI HTTP Server and TTS Queue

**Rationale:** The HTTP layer decouples the hooks from TTS execution and enables fire-and-forget audio dispatch. The bounded queue handles backpressure from rapid-fire Claude Code turns. Sentence chunking reduces perceived latency. This phase validates the threading boundaries with real HTTP traffic before hook integration.

**Delivers:** `/speak`, `/stop`, `/status` endpoints; bounded queue consumer; sentence-chunked TTS playback; text preprocessing pipeline; WASAPI audio configuration.

**Addresses:** Stop hook + /speak endpoint (P1), text filtering pipeline (P1), sentence-chunked delivery (P2)

**Implements:** FastAPI HTTP server component, TTS worker component, text filter module

**Avoids:** Pitfall 3 (ONNX version conflicts), Pitfall 6 (WASAPI exclusive mode), Pitfall 10 (text junk in TTS)

**Standard patterns:** Yes — FastAPI + queue pattern is well-documented. No phase research needed.

### Phase 3: Claude Code Hook Integration

**Rationale:** Hooks are thin relay scripts but have several Windows-specific failure modes (encoding, PowerShell policy, async config) that should be isolated and validated in a dedicated phase. Once hooks work end-to-end, the core product is functional.

**Delivers:** `speak.py` Stop hook; `ensure_running.py` SessionStart hook; `.claude/settings.json` hook configuration; end-to-end smoke test (type in Claude Code, hear audio).

**Addresses:** Stop hook extraction (P1), SessionStart auto-launch (P1)

**Avoids:** Pitfall 7 (wrong hook event — use Stop not PostToolUse), Pitfall 8 (Windows stdin encoding), Pitfall 12 (PowerShell execution policy)

**Standard patterns:** Yes — hook payload schema is from official docs. No phase research needed.

### Phase 4: System Tray UX and Process Management

**Rationale:** pystray is the highest-friction UX component to get right on Windows 11. After confirming the core audio pipeline works, adding the tray icon, mute toggle, and clean process management (PID file, graceful shutdown sequences) completes the v1 user-facing experience.

**Delivers:** System tray icon with right-click menu; mute/unmute toggle; tray speaking status indicator; Quit action; clean startup/shutdown sequences; Windows notification balloon on crash.

**Addresses:** System tray icon (P1), mute toggle (P1), tray speaking status (P2)

**Implements:** pystray tray component, PID file management, graceful shutdown

**Avoids:** Pitfall 1 (pystray threading — `Icon.run(setup=fn)` pattern), Pitfall 9 (zombie processes on crash)

**Standard patterns:** Yes — pystray docs cover the `setup=` callback and menu patterns. No phase research needed.

### Phase 5: Configuration, Voice Selection, and Slash Commands

**Rationale:** With the service stable, adding persistent config (voice, speed, enabled state) and slash commands (`/agenttalk:voice`, `/agenttalk:mute`, `/agenttalk:start`, `/agenttalk:stop`) completes the operator interface. This phase is straightforward given the existing HTTP foundation.

**Delivers:** `%APPDATA%\AgentTalk\config.json` persistence; `/voice`, `/model`, `/start`, `/stop`, `/status` slash commands; voice switching via `/agenttalk:voice`; current voice shown in tray menu.

**Addresses:** Voice switching (P2), model switching foundation (P2), tray voice display (P2)

**Standard patterns:** Yes — config.json pattern and FastAPI endpoint addition are standard. No phase research needed.

### Phase 6: Installation Script and Packaging

**Rationale:** Developer-first installation must be single-command. This phase wires together `pyproject.toml` with console_scripts, the `agenttalk setup` post-install command that downloads model files and registers hooks, and `.gitignore` for ONNX model files. Packaging is deferred until the service is proven stable to avoid premature packaging complexity.

**Delivers:** `pip install agenttalk`; `agenttalk setup` command that downloads Kokoro model to `%APPDATA%\AgentTalk\models\`, registers hooks in `~/.claude/settings.json`, and creates a desktop shortcut; `pyproject.toml` with pinned dependencies; `.gitignore` for `*.onnx` and `*.bin`.

**Addresses:** Single-command install (P1)

**Avoids:** Anti-pattern: storing model files in the repo (GitHub 100MB limit); anti-pattern: installing deps globally (ONNX conflicts)

**Standard patterns:** Yes — Python packaging with pyproject.toml is well-documented. No phase research needed.

### Phase Ordering Rationale

- Phase 1 before Phase 2: The threading architecture and Windows audio stack must be validated in isolation. Adding HTTP before confirming TTS works creates multi-variable debugging.
- Phase 2 before Phase 3: The HTTP endpoint and queue must be testable with `curl` before wiring the hooks. Hook debugging is harder than HTTP debugging.
- Phase 3 before Phase 4: End-to-end audio verification (Claude Code response plays as audio) should happen before adding the tray UX layer. Tray icon bugs should not block validating the core feature.
- Phase 4 before Phase 5: Config and slash commands extend a stable service. Building slash commands before the service skeleton is stable wastes effort.
- Phase 5 before Phase 6: Package only what is proven to work. Early packaging locks in decisions before they are validated.

### Research Flags

Phases with standard patterns (skip `/gsd:research-phase` during planning):
- **Phase 1:** Threading patterns (pystray + uvicorn) are fully documented in official pystray and uvicorn docs. Kokoro ONNX model loading is documented in the repo README. No additional research needed.
- **Phase 2:** FastAPI + queue is a standard pattern with extensive official documentation. WASAPI settings documented in sounddevice official docs.
- **Phase 3:** Hook payload schema is from official Anthropic docs (HIGH confidence). Encoding fix is a known one-liner.
- **Phase 4:** pystray menu API is documented. Shutdown sequences follow from Phase 1 threading model.
- **Phase 5:** Config JSON and FastAPI endpoint extension require no research.
- **Phase 6:** Python packaging with pyproject.toml and console_scripts is standard and well-documented.

No phase requires `/gsd:research-phase`. All major unknowns were resolved during initial research. The only open question requiring live testing (not research) is whether `espeakng-loader` fully handles espeak-ng on a clean Windows machine without any system-level espeak-ng install — this should be validated empirically in Phase 1, not researched further.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All packages verified on PyPI with exact versions. Version constraints (Python 3.11 only, onnxruntime >=1.20.1) verified against official sources. |
| Features | HIGH | Claude Code hooks from official Anthropic docs. Feature set is narrow and well-bounded. Text filtering approach is domain-inferred (MEDIUM confidence) but the strategy is sound. |
| Architecture | HIGH | Threading model verified against official pystray and uvicorn docs. Hook payload schema from official Anthropic docs. Build order derived from explicit dependency analysis. |
| Pitfalls | HIGH | Most pitfalls from official GitHub issues or official docs. piper archived status HIGH confidence (GitHub announcement). ONNX warmup behavior MEDIUM (community gist). |

**Overall confidence:** HIGH

### Gaps to Address

- **espeakng-loader on clean Windows:** `kokoro-onnx` lists `espeakng-loader` as a dependency, but its behavior on a machine with no system espeak-ng install is not explicitly documented. Validate by running a synthesis test on a clean VM during Phase 1. If it fails, document the manual install step in `agenttalk setup`.
- **Piper deferred:** Piper TTS is excluded from v1 due to archived upstream and Windows DLL issues. If users request it post-launch, the implementation path is: use the official binary release, bundle DLLs alongside the exe, call via absolute path with `cwd=` set to the binary directory.
- **WASAPI auto_convert coverage:** The `sd.WasapiSettings(auto_convert=True)` fix addresses sample rate mismatches but does not resolve exclusive mode conflicts. Users with DACs or audiophile setups configured for WASAPI exclusive mode will see `PortAudioError`. The only resolution is a user-side audio setting change; document this prominently in the README.
- **Hook async behavior on resume:** The `SessionStart` hook with `matcher: "startup"` fires on new sessions. The research confirms it uses `source: "startup"` to distinguish from resume/clear/compact, but the exact matcher syntax in `settings.json` should be verified against the live Claude Code version during Phase 3.

## Sources

### Primary (HIGH confidence)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) — Stop hook payload schema, `last_assistant_message` field, SessionStart events, `async` hook flag, `$CLAUDE_PROJECT_DIR`
- [kokoro-onnx on PyPI](https://pypi.org/project/kokoro-onnx/) — version 0.5.0, Python support matrix, espeakng-loader dependency
- [kokoro-onnx GitHub](https://github.com/thewh1teagle/kokoro-onnx) — Kokoro.create() API, model file download instructions
- [piper-tts on PyPI](https://pypi.org/project/piper-tts/) — version 1.4.1, Windows win_amd64 wheel availability
- [FastAPI on PyPI](https://pypi.org/project/fastapi/) — version 0.133.1, Python >=3.10 requirement
- [uvicorn on PyPI](https://pypi.org/project/uvicorn/) — version 0.41.0, thread signal handler behavior
- [sounddevice on PyPI](https://pypi.org/project/sounddevice/) — version 0.5.5, Windows WASAPI settings
- [pystray usage docs](https://pystray.readthedocs.io/en/latest/usage.html) — `Icon.run(setup=fn)` pattern, Windows threading safety
- [FastAPI BackgroundTasks docs](https://fastapi.tiangolo.com/tutorial/background-tasks/) — fire-and-forget pattern
- [sounddevice WASAPI platform settings](https://python-sounddevice.readthedocs.io/en/latest/api/platform-specific-settings.html) — auto_convert flag
- [piper archived October 2025](https://github.com/rhasspy/piper/issues/821) — confirmed upstream archive status

### Secondary (MEDIUM confidence)
- [uvicorn background thread pattern](https://bugfactory.io/articles/starting-and-stopping-uvicorn-in-the-background/) — verified against uvicorn docs
- [uvicorn Windows ProactorEventLoop issues](https://github.com/Kludex/uvicorn/issues/1220) — event loop policy interaction
- [sounddevice GitHub issue #283](https://github.com/spatialaudio/python-sounddevice/issues/283) — Windows MME blocking play cutoff
- [pystray GIL crash on Windows 11](https://github.com/PySimpleGUI/PySimpleGUI/issues/6812) — Python 3.12+ GIL behavior
- [Piper Windows DLL issues](https://github.com/rhasspy/piper/issues/272) — binary search path behavior
- [Kokoro ONNX CPU warmup benchmark](https://gist.github.com/efemaer/23d9a3b949b751dde315192b4dcf0653) — first-inference warmup timing
- [Claude Code UTF-8 BOM / JSON parse error](https://github.com/anthropics/claude-code/issues/14442) — Windows stdin encoding behavior

### Tertiary (LOW confidence, needs validation)
- WebSearch: espeakng-loader bundled vs manual MSI install — needs clean-machine empirical test in Phase 1
- [Kokoro 82M install guide](https://aleksandarhaber.com/kokoro-82m-install-and-run-locally-fast-small-and-free-text-to-speech-tts-ai-model-kokoro-82m/) — voice names list only

---
*Research completed: 2026-02-26*
*Ready for roadmap: yes*

# Requirements: AgentTalk

**Defined:** 2026-02-26
**Core Value:** Claude Code's output is heard in real-time through a local TTS engine, hands-free, without leaving the terminal or touching a mouse.

## v1 Requirements

### TTS Engine

- [x] **TTS-01**: Service loads kokoro-onnx 0.5.0 as the primary TTS engine on startup (fully offline, no API key)
- [x] **TTS-02**: Service performs eager model load + warmup synthesis call before accepting requests (avoids 3-8s first-request latency)
- [x] **TTS-03**: Service exposes `/health` endpoint returning 503 until model is warm and ready
- [ ] **TTS-04**: Piper TTS is available as an alternate engine, switchable at runtime via `/agenttalk:model`
- [x] **TTS-05**: User can adjust TTS speech speed (rate) via configuration and slash command

### Audio Pipeline

- [x] **AUDIO-01**: Text is sentence-chunked before synthesis — first sentence begins playing while remaining sentences synthesize
- [x] **AUDIO-02**: Text preprocessing pipeline strips fenced code blocks, inline code, URLs, file paths, and markdown markers before TTS
- [x] **AUDIO-03**: Sentences with fewer than 40% alphabetic characters are silently skipped (avoids reading symbols, JSON, etc.)
- [x] **AUDIO-04**: Incoming TTS requests are queued (bounded, max 3 pending); overflow is dropped to prevent runaway audio
- [x] **AUDIO-05**: WASAPI `auto_convert=True` is set to handle sample rate mismatches on Windows audio devices
- [x] **AUDIO-06**: User can adjust TTS output volume via configuration and slash command
- [ ] **AUDIO-07**: When TTS begins speaking, other audio streams (e.g., Spotify, browser) are ducked to 50% of their current level via Windows Core Audio Session API; streams are restored to original level when TTS finishes

### Service Architecture

- [x] **SVC-01**: Service runs as a Windows background process with no console window (pythonw.exe + DETACHED_PROCESS)
- [x] **SVC-02**: FastAPI HTTP server runs on localhost:5050 in a daemon thread (uvicorn)
- [x] **SVC-03**: TTS worker runs in a separate daemon thread consuming from the audio queue
- [ ] **SVC-04**: pystray tray icon runs on the main thread (Win32 message loop requirement)
- [x] **SVC-05**: PID lock file at `%APPDATA%\AgentTalk\service.pid` prevents duplicate instances and enables clean process management
- [x] **SVC-06**: All service logs written to `%APPDATA%\AgentTalk\agenttalk.log` (pythonw.exe suppresses stdout; file logging is mandatory)
- [x] **SVC-07**: Service catches and logs all startup exceptions before crashing (no silent failures)

### Claude Code Integration

- [ ] **HOOK-01**: `Stop` hook reads `last_assistant_message` from stdin JSON and POSTs to `/speak` endpoint
- [ ] **HOOK-02**: `SessionStart` hook checks PID file and launches the service if not already running
- [ ] **HOOK-03**: Both hooks are configured with `"async": true` so they never block Claude Code's UI
- [ ] **HOOK-04**: Hook scripts read stdin as `sys.stdin.buffer.read().decode('utf-8')` to handle non-ASCII assistant output on Windows
- [ ] **HOOK-05**: Hook registration is automated by `agenttalk setup` — no manual JSON editing required

### System Tray UI

- [ ] **TRAY-01**: Service icon is visible in the Windows system tray while the service is running
- [ ] **TRAY-02**: Right-click tray menu includes Mute/Unmute toggle (with checkmark state)
- [ ] **TRAY-03**: Tray icon changes appearance (color or animation) when TTS is actively speaking
- [ ] **TRAY-04**: Right-click tray menu includes a voice submenu listing all available Kokoro voices
- [ ] **TRAY-05**: Right-click tray menu includes a Quit action that cleanly shuts down the service
- [ ] **TRAY-06**: Current active voice name is shown as a disabled (informational) item in the tray menu

### Slash Commands

- [ ] **CMD-01**: `/agenttalk:start` slash command launches the AgentTalk service if not running
- [ ] **CMD-02**: `/agenttalk:stop` slash command kills the AgentTalk service and silences any current audio
- [ ] **CMD-03**: `/agenttalk:voice [name]` slash command switches the active Kokoro voice by name
- [ ] **CMD-04**: `/agenttalk:model [kokoro|piper]` slash command switches the active TTS engine

### Audio Cues

- [ ] **CUE-01**: User can configure a pre-speech audio file (e.g., `bell.wav`) played before TTS begins speaking
- [ ] **CUE-02**: User can configure a post-speech audio file (e.g., `bell.wav`) played after TTS finishes speaking
- [ ] **CUE-03**: Pre/post audio files are optional — when not set, no sound plays (default behavior unchanged)
- [ ] **CUE-04**: Audio cue paths are configurable via `config.json` and settable via slash command or tray

### Configuration

- [ ] **CFG-01**: All settings persist in `%APPDATA%\AgentTalk\config.json` (no admin rights required)
- [ ] **CFG-02**: Persisted settings include: active voice, speech speed, output volume, TTS model, mute state, pre-speech cue path, post-speech cue path
- [ ] **CFG-03**: Config changes take effect immediately without service restart

### Installation & Packaging

- [x] **INST-01**: `pip install agenttalk` installs the package and CLI entry point
- [x] **INST-02**: `agenttalk setup` downloads the Kokoro ONNX model (~310MB) to `%APPDATA%\AgentTalk\models\` with a progress bar
- [x] **INST-03**: `agenttalk setup` registers the Stop and SessionStart hooks in `~/.claude/settings.json` without overwriting existing hooks
- [x] **INST-04**: `agenttalk setup` creates a desktop shortcut (.lnk) pointing to the AgentTalk service launcher
- [x] **INST-05**: `agenttalk setup` writes hook scripts using the absolute path to the venv's pythonw.exe (avoids PATH resolution failures)
- [x] **INST-06**: Install process works without administrator rights on Windows 11

### Documentation

- [x] **DOC-01**: README covers installation, quickstart (3 commands to working audio), available voices list, all slash commands, and tray menu usage
- [x] **DOC-02**: README includes a troubleshooting section covering: WASAPI exclusive mode conflicts, Kokoro model download issues, Python version requirements (3.11 only), hook registration verification
- [x] **DOC-03**: README is updated with every feature addition — no feature ships without doc coverage
- [x] **DOC-04**: Repository includes MIT LICENSE file
- [x] **DOC-05**: Repository is published publicly at github.com/omern/AgentTalk

## v2 Requirements

### Audio

- **V2-AUDIO-01**: Sentence-level streaming — begin speaking mid-response rather than waiting for Stop hook (requires different integration approach)
- **V2-AUDIO-02**: "Read that again" slash command — replays the last TTS segment

### TTS Engine

- **V2-TTS-01**: Multi-language voice packs (currently English only)
- **V2-TTS-02**: Voice blending (Kokoro supports `voice1:60,voice2:40` syntax — expose in UI)

### UX

- **V2-UX-01**: GUI configuration panel (web-based, served by FastAPI) — currently slash commands only
- **V2-UX-02**: Linux/macOS support — Windows-native focus for v1

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cloud TTS (gTTS, edge-tts, Azure TTS) | Requires internet, API keys — violates local-only constraint |
| pyttsx3 | System TTS voice quality is poor; not a real TTS engine |
| Screen reader functionality | Not the use case — AgentTalk only speaks Claude Code output |
| Multi-user / network TTS | Single-machine tool |
| Streaming mid-response TTS | Claude Code hooks only fire at Stop time — impossible without deeper integration |
| Windows SCM service registration | Adds admin rights requirement, unnecessary for single-user tool |
| Docker container deployment | Windows-native tool; containers add unnecessary overhead |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TTS-01 | Phase 1 | Complete |
| TTS-02 | Phase 1 | Complete |
| TTS-03 | Phase 1 | Complete |
| SVC-01 | Phase 1 | Complete |
| SVC-05 | Phase 1 | Complete |
| SVC-06 | Phase 1 | Complete |
| SVC-07 | Phase 1 | Complete |
| SVC-02 | Phase 2 | Complete |
| SVC-03 | Phase 2 | Complete |
| AUDIO-01 | Phase 2 | Complete |
| AUDIO-02 | Phase 2 | Complete |
| AUDIO-03 | Phase 2 | Complete |
| AUDIO-04 | Phase 2 | Complete |
| AUDIO-05 | Phase 2 | Complete |
| AUDIO-06 | Phase 2 | Complete |
| TTS-05 | Phase 2 | Complete |
| HOOK-01 | Phase 3 | Pending |
| HOOK-02 | Phase 3 | Pending |
| HOOK-03 | Phase 3 | Pending |
| HOOK-04 | Phase 3 | Pending |
| HOOK-05 | Phase 3 | Pending |
| SVC-04 | Phase 4 | Pending |
| TRAY-01 | Phase 4 | Pending |
| TRAY-02 | Phase 4 | Pending |
| TRAY-03 | Phase 4 | Pending |
| TRAY-04 | Phase 4 | Pending |
| TRAY-05 | Phase 4 | Pending |
| TRAY-06 | Phase 4 | Pending |
| AUDIO-07 | Phase 4 | Pending |
| CUE-01 | Phase 4 | Pending |
| CUE-02 | Phase 4 | Pending |
| CUE-03 | Phase 4 | Pending |
| CUE-04 | Phase 4 | Pending |
| CMD-01 | Phase 5 | Pending |
| CMD-02 | Phase 5 | Pending |
| CMD-03 | Phase 5 | Pending |
| CMD-04 | Phase 5 | Pending |
| CFG-01 | Phase 5 | Pending |
| CFG-02 | Phase 5 | Pending |
| CFG-03 | Phase 5 | Pending |
| TTS-04 | Phase 5 | Pending |
| INST-01 | Phase 6 | Complete |
| INST-02 | Phase 6 | Complete |
| INST-03 | Phase 6 | Complete |
| INST-04 | Phase 6 | Complete |
| INST-05 | Phase 6 | Complete |
| INST-06 | Phase 6 | Complete |
| DOC-01 | Phase 6 | Complete |
| DOC-02 | Phase 6 | Complete |
| DOC-03 | Phase 6 | Complete |
| DOC-04 | Phase 6 | Complete |
| DOC-05 | Phase 6 | Complete |

**Coverage:**
- v1 requirements: 52 total
- Mapped to phases: 52
- Unmapped: 0

---
*Requirements defined: 2026-02-26*
*Last updated: 2026-02-26 after roadmap creation — all 52 requirements mapped to 6 phases*

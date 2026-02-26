# Roadmap: AgentTalk

## Overview

AgentTalk ships in six phases ordered by risk: validate the Windows threading model and Kokoro audio stack first, wire up the HTTP layer and text pipeline second, integrate Claude Code hooks for end-to-end speech third, add the system tray UX and audio enhancements fourth, surface configuration and slash commands fifth, and package for single-command installation last. Each phase delivers a coherent, testable capability that the next phase builds on.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Service Skeleton and Core Audio** - Validate the Windows threading model, Kokoro TTS loading, and background process launch before building anything on top (completed 2026-02-26)
- [ ] **Phase 2: FastAPI HTTP Server and TTS Queue** - Expose the /speak endpoint, wire up the bounded audio queue, add sentence chunking and text preprocessing
- [ ] **Phase 3: Claude Code Hook Integration** - Connect Stop and SessionStart hooks for end-to-end speech from Claude Code output
- [ ] **Phase 4: System Tray UX, Audio Ducking, and Cues** - Add the pystray tray icon, mute toggle, speaking indicator, audio ducking, and pre/post audio cues
- [ ] **Phase 5: Configuration, Voice/Model Switching, and Slash Commands** - Persist settings in APPDATA, expose all slash commands, enable voice and model switching
- [ ] **Phase 6: Installation Script, Packaging, and Documentation** - Ship pip install agenttalk, agenttalk setup, desktop shortcut, and complete README

## Phase Details

### Phase 1: Service Skeleton and Core Audio
**Goal**: A Windows background process launches without a console window, loads Kokoro, synthesizes audio from hardcoded text, plays it through speakers, logs all activity to file, and prevents duplicate instances via PID lock
**Depends on**: Nothing (first phase)
**Requirements**: TTS-01, TTS-02, TTS-03, SVC-01, SVC-05, SVC-06, SVC-07
**Success Criteria** (what must be TRUE):
  1. Running `pythonw.exe service.py` produces no console window and audio plays through speakers within 10 seconds
  2. A second launch of the service detects the PID file and exits cleanly without port conflicts or zombie processes
  3. `%APPDATA%\AgentTalk\agenttalk.log` contains startup progress entries including model load and warmup completion
  4. The `/health` endpoint returns 503 before Kokoro warmup completes and 200 after
  5. Any startup exception is caught, logged to file, and does not produce a silent crash
**Plans**: TBD

### Phase 2: FastAPI HTTP Server and TTS Queue
**Goal**: A curl POST to /speak causes the service to preprocess text, sentence-chunk it, queue it, and play each sentence through speakers as it synthesizes — with backpressure capping at 3 pending items
**Depends on**: Phase 1
**Requirements**: SVC-02, SVC-03, AUDIO-01, AUDIO-02, AUDIO-03, AUDIO-04, AUDIO-05, AUDIO-06, TTS-05
**Success Criteria** (what must be TRUE):
  1. `curl -X POST localhost:5050/speak -d '{"text":"Hello world."}'` causes audio to play within 2 seconds
  2. Text containing fenced code blocks, inline code, URLs, and markdown markers is spoken as clean prose with those elements stripped
  3. A sentence consisting of fewer than 40% alphabetic characters (e.g., pure JSON) is silently skipped and no audio plays for it
  4. Sending 10 rapid POST requests causes at most 3 to queue; the rest are dropped without crashing the service
  5. Audio plays without sample rate errors on a standard Windows 11 audio device
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — TDD: text preprocessing module (strip_markdown, is_speakable, preprocess)
- [ ] 02-02-PLAN.md — TTS queue + /speak endpoint + WASAPI detection wired into service

### Phase 3: Claude Code Hook Integration
**Goal**: Typing a message in Claude Code and receiving an assistant response causes the response text to be spoken aloud automatically, and opening a new Claude Code session auto-launches the service if it is not running
**Depends on**: Phase 2
**Requirements**: HOOK-01, HOOK-02, HOOK-03, HOOK-04, HOOK-05
**Success Criteria** (what must be TRUE):
  1. After Claude Code receives an assistant response, the response text is spoken aloud within 3 seconds without any manual action
  2. Opening Claude Code when the service is not running causes the service to start automatically before the first response
  3. Hooks with non-ASCII characters in the assistant message (e.g., accented letters) are forwarded without UnicodeDecodeError
  4. Neither hook blocks Claude Code's UI — the terminal remains responsive during TTS playback
**Plans**: 2 plans

Plans:
- [ ] 03-01-PLAN.md — Hook scripts (stop_hook.py + session_start_hook.py) + unit tests
- [ ] 03-02-PLAN.md — Setup module (register_hooks into settings.json) + unit tests

### Phase 4: System Tray UX, Audio Ducking, and Cues
**Goal**: The service shows a visible tray icon while running; the icon changes when speaking; right-clicking reveals mute, voice selection, and quit; other audio streams duck during TTS; and optional pre/post audio cues play around each utterance
**Depends on**: Phase 3
**Requirements**: SVC-04, TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05, TRAY-06, AUDIO-07, CUE-01, CUE-02, CUE-03, CUE-04
**Success Criteria** (what must be TRUE):
  1. The AgentTalk icon appears in the Windows system tray when the service is running and disappears after Quit
  2. Right-clicking the tray icon shows Mute/Unmute (with checkmark), a voice submenu, the current active voice name, and Quit
  3. The tray icon changes appearance while TTS is actively speaking and returns to the default when playback finishes
  4. Music playing in Spotify or a browser drops to 50% volume when TTS speaks and restores to the original level when TTS finishes
  5. When a pre-speech cue path is configured, the cue file plays before each TTS utterance; when none is configured, no sound plays
**Plans**: TBD

### Phase 5: Configuration, Voice/Model Switching, and Slash Commands
**Goal**: All service settings persist across restarts in APPDATA, all four slash commands work from the Claude Code terminal, voice and model can be switched at runtime, and config changes take effect immediately without restarting the service
**Depends on**: Phase 4
**Requirements**: CMD-01, CMD-02, CMD-03, CMD-04, CFG-01, CFG-02, CFG-03, TTS-04
**Success Criteria** (what must be TRUE):
  1. Running `/agenttalk:stop` from Claude Code kills the service and silences any current audio
  2. Running `/agenttalk:voice af_bella` switches the active Kokoro voice and the next TTS utterance uses that voice
  3. Running `/agenttalk:model piper` switches the TTS engine and the next utterance is synthesized with Piper
  4. After changing the voice via slash command and restarting the service, the same voice is active (setting persisted in config.json)
  5. `%APPDATA%\AgentTalk\config.json` exists and contains all persisted settings: voice, speed, volume, model, mute state, cue paths
**Plans**: TBD

### Phase 6: Installation Script, Packaging, and Documentation
**Goal**: A developer on a clean Windows 11 machine runs two commands (pip install agenttalk, agenttalk setup) and AgentTalk is fully installed with hooks registered, model downloaded, desktop shortcut created, and no admin rights required
**Depends on**: Phase 5
**Requirements**: INST-01, INST-02, INST-03, INST-04, INST-05, INST-06, DOC-01, DOC-02, DOC-03, DOC-04, DOC-05
**Success Criteria** (what must be TRUE):
  1. `pip install agenttalk` succeeds on Python 3.11 on a clean Windows 11 machine without admin rights
  2. `agenttalk setup` downloads the Kokoro ONNX model to `%APPDATA%\AgentTalk\models\` with a visible progress bar and registers hooks in `~/.claude/settings.json` without overwriting existing hooks
  3. A desktop shortcut (.lnk) exists after setup and double-clicking it launches the service
  4. The README covers installation, quickstart, available voices, all slash commands, tray menu usage, and a troubleshooting section covering WASAPI exclusive mode, Kokoro download issues, Python version requirements, and hook verification
  5. The repository is publicly accessible at github.com/omern/AgentTalk under the MIT license
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Service Skeleton and Core Audio | 2/2 | Complete | 2026-02-26 |
| 2. FastAPI HTTP Server and TTS Queue | 0/TBD | Not started | - |
| 3. Claude Code Hook Integration | 0/TBD | Not started | - |
| 4. System Tray UX, Audio Ducking, and Cues | 0/TBD | Not started | - |
| 5. Configuration, Voice/Model Switching, and Slash Commands | 0/TBD | Not started | - |
| 6. Installation Script, Packaging, and Documentation | 0/TBD | Not started | - |

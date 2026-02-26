# AgentTalk

## What This Is

AgentTalk is a lightweight Windows background service that intercepts Claude Code's text output and speaks it aloud using a local TTS model (Kokoro or Piper). It runs silently in the system tray, starts automatically with Claude Code, and is controlled entirely via Claude Code slash commands. No cloud services, no API keys — fully local.

## Core Value

Claude Code's output is heard in real-time through a local TTS engine, hands-free, without leaving the terminal or touching a mouse.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] FastAPI service wraps a local TTS model (Kokoro or Piper) and exposes an HTTP endpoint to synthesize and play audio
- [ ] Claude Code hooks intercept assistant output and POST text to the FastAPI service in real-time
- [ ] Service runs as a background Windows process (not a console window)
- [ ] Service appears as an icon in the Windows system tray while running
- [ ] Desktop shortcut (.lnk) installed for manual start/restart outside Claude Code
- [ ] Service starts automatically when Claude Code starts (via SessionStart hook)
- [ ] `/agenttalk:start` slash command launches the service
- [ ] `/agenttalk:stop` slash command kills the service
- [ ] `/agenttalk:voice` slash command switches the active voice/speaker
- [ ] `/agenttalk:model` slash command switches the TTS model (Kokoro ↔ Piper)
- [ ] Only the assistant's main text output is spoken — no metadata, tool results, or system messages
- [ ] Documentation is comprehensive, user-friendly, and always current
- [ ] Installation is a single command or guided script (no manual path-wrangling)
- [ ] Project is published as a public MIT-licensed GitHub repo (omern/AgentTalk)

### Out of Scope

- Cloud TTS or any external API calls — local-only by design
- Linux / macOS support in v1 — Windows-native focus
- Web or GUI configuration panel — slash commands are the interface
- Multi-user or networked TTS — single-machine only
- Streaming TTS mid-sentence — sentence-complete chunking is sufficient for v1

## Context

- **Platform**: Windows 11, native (no WSL)
- **Language**: Python — chosen for best TTS ecosystem (Kokoro, Piper), FastAPI native, and `pystray` for system tray
- **TTS models**: Kokoro (higher quality, ONNX-based) and Piper (fast, lightweight) — both run fully offline
- **Hook integration**: Claude Code's `PostToolUse` and `Stop` hooks deliver assistant output; only the final assistant text content is forwarded
- **Service architecture**: Single Python process — FastAPI HTTP server + pystray system tray icon running in threads
- **Installation target**: Developer machines; assumes Python 3.10+ available or bundled
- **Documentation standard**: README stays current with every feature change; install guide is tested on clean Windows machine

## Constraints

- **Platform**: Windows 11 — must work without WSL, Docker, or admin rights for normal use
- **Footprint**: Service RAM target < 200MB at rest; startup < 5 seconds
- **Local-only**: Zero network calls for TTS synthesis
- **Python**: 3.10+ (matches Claude Code's typical dev environment)
- **No admin required**: Installation and service start must work as a normal user

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over Go/Rust | Best TTS library support (kokoro-onnx, piper-tts), FastAPI native, pystray works | — Pending |
| FastAPI as TTS wrapper | Lightweight, async-friendly, easy Claude Code hook integration via HTTP POST | — Pending |
| pystray for system tray | Pure Python, Windows-native, minimal dependencies | — Pending |
| Sentence-chunked TTS | Avoids latency of streaming; natural speech boundaries | — Pending |
| Claude Code hooks for interception | Official mechanism — no screen scraping or process injection needed | — Pending |
| Kokoro as default model | Higher quality output vs Piper; ONNX runtime available on Windows | — Pending |

---
*Last updated: 2026-02-26 after initialization*

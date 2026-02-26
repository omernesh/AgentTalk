# Feature Research

**Domain:** Developer TTS companion app (Claude Code / AI assistant voice output)
**Researched:** 2026-02-26
**Confidence:** HIGH (Claude Code hooks from official docs; pystray from official docs; TTS from multiple verified sources)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Speak assistant text output | Core value proposition — nothing works without this | MEDIUM | Uses `Stop` hook: `last_assistant_message` field delivers full assistant text without transcript parsing |
| Silence non-assistant content | Speaking tool results, file paths, metadata = noise; users expect only the narrative text | MEDIUM | Text filtering logic: strip markdown, code blocks, file paths, JSON blobs before sending to TTS |
| Mute / unmute toggle | First thing users reach for when sound becomes inconvenient | LOW | Pystray menu checkmark item; also via slash command |
| System tray icon visible while running | Windows UX standard — background service must show presence | LOW | pystray on Windows shows tray on right-click automatically |
| Start / stop via Claude Code commands | The interface is Claude Code, not a separate window | LOW | `/claudetalk:start` and `/claudetalk:stop` slash commands trigger HTTP calls to FastAPI |
| Auto-start with Claude Code session | Users should not need to manually start the service | LOW | `SessionStart` hook with `startup` matcher starts the service process |
| Graceful exit from tray | "Quit" is required — you can't leave a process with no exit path | LOW | Tray right-click "Quit" item calls `icon.stop()` |
| Single-command install | Developers expect `pip install claudetalk` or equivalent; multi-step installs are abandoned | MEDIUM | `pip install claudetalk` with post-install setup script for hook registration |

### Differentiators (Competitive Advantage)

Features that set the product apart — not expected of a basic TTS tool, but they add meaningful value for this specific use case.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Smart text filtering for AI output | Screen readers read everything — ClaudeTalk reads only the assistant's narrative, skipping code blocks, file paths, JSON, tool output | HIGH | Core differentiator; filter pipeline strips: markdown fences, inline code, file paths (heuristic: strings with `/` or `\`), JSON structures, ANSI escape codes |
| Voice switching via slash command | Switching voices in a screen reader requires leaving the task; `/claudetalk:voice af_sarah` does it inline | LOW | Kokoro voices: af_alloy, af_bella, af_heart, af_jessica, af_kore, af_nicole, af_nova, af_river, af_sarah, af_sky (American English female); am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael, am_onyx (American English male) |
| Model switching via slash command | Kokoro vs Piper trade-off (quality vs speed) selectable at runtime | MEDIUM | `/claudetalk:model kokoro` or `piper`; FastAPI swaps backend without restart |
| Tray icon shows speaking status | Visual feedback when TTS is active vs idle — reduces anxiety about whether it's working | LOW | pystray supports dynamic icon; swap icon image on TTS start/stop |
| Sentence-chunked delivery | TTS starts speaking sentence by sentence rather than waiting for full response — lower perceived latency | MEDIUM | Split on `.`, `!`, `?` before sending to TTS; queue chunks; Kokoro handles sentence-length inputs well |
| SessionStart auto-launch hook | Starts ClaudeTalk when Claude Code opens, not just when user remembers | LOW | `SessionStart` hook with `matcher: "startup"` checks if service is running, starts it if not |
| Local-only (no cloud dependency) | Privacy-conscious developers prefer zero telemetry; all other AI voice tools make network calls | LOW | Architecture decision already made; differentiator in positioning |
| Tray shows current voice name | Glanceable status — which voice is active right now | LOW | Dynamic pystray menu item updated via `icon.update_menu()` |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem like a good idea but create disproportionate complexity or scope creep for v1.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Streaming TTS mid-sentence | Lower latency; start speaking while Claude is still writing | Claude Code hooks only deliver output at `Stop` time — there is no streaming hook for mid-response text; would require screen scraping or process injection | Sentence-chunked delivery from `last_assistant_message` achieves similar perceived latency with no scraping |
| GUI configuration panel | "Nice to have" settings UI instead of slash commands | Scope doubles: need a window framework (tkinter/wx), state management, and maintained UI alongside CLI — for a background service used by developers who prefer CLI | Slash commands cover 100% of configuration needs for the target user |
| Cloud TTS option (ElevenLabs, Azure) | Higher voice quality ceiling | Adds API key management, network dependency, latency, cost, and privacy concerns; contradicts the core value ("zero cloud") | Kokoro quality is excellent for offline use |
| Wake word detection ("Hey Claude") | Hands-free control feels like a natural extension | Requires always-on microphone, ML inference pipeline, significant RAM — completely different product surface | Out of scope; a different product |
| Multi-language voice selection | Piper and Kokoro support multiple languages | Adds voice discovery complexity, model download management, and language detection logic with no immediate user need | English-only for v1; add languages when requested by real users |
| Transcript playback / re-read | "Read that again" for missed responses | Requires transcript storage, playback controls, and a history model; significantly more complex than the core streaming use case | Not needed if TTS works reliably; defer until requested |
| Windows service (SCM) registration | True background service behavior, auto-start on login | Requires admin rights for service registration and significantly more complex install/uninstall; contradicts the "no admin required" constraint | Desktop shortcut + SessionStart hook covers the real need without admin rights |
| Voice activity detection (pause when user speaks) | Natural conversation feel | Requires microphone access; wrong interaction model for a dev tool where Claude Code is the primary interface | Not needed; TTS stopping when Claude stops is the correct behavior |

---

## Feature Dependencies

```
[SessionStart hook]
    └──requires──> [FastAPI service running]
                       └──requires──> [Kokoro or Piper model loaded]

[Stop hook: last_assistant_message]
    └──requires──> [Text filtering pipeline]
                       └──requires──> [FastAPI /speak endpoint]
                                          └──requires──> [TTS model loaded]

[/claudetalk:voice command]
    └──requires──> [FastAPI /voice endpoint]
                       └──requires──> [Service running]

[/claudetalk:model command]
    └──requires──> [FastAPI /model endpoint]
                       └──requires──> [Both Kokoro and Piper available]

[Tray status icon]
    └──enhances──> [Service running check]

[Sentence chunking]
    └──enhances──> [Stop hook delivery]

[pip install claudetalk]
    └──requires──> [Model files bundled or downloaded on first run]
```

### Dependency Notes

- **Stop hook requires service running:** The hook fires when Claude finishes responding. If the service is not up, the HTTP POST fails silently (timeout) — must handle gracefully.
- **Sentence chunking enhances Stop hook:** Splitting `last_assistant_message` into sentences before posting to the `/speak` endpoint makes responses feel more responsive without requiring streaming infrastructure.
- **Model switching conflicts with in-flight TTS:** If user switches model while a sentence is being spoken, the current audio must complete before the model swap takes effect.

---

## Claude Code Hook Mechanism (Authoritative — from official docs)

**Source:** https://code.claude.com/docs/en/hooks (HIGH confidence)

### Relevant Hook Events for ClaudeTalk

| Event | When It Fires | What ClaudeTalk Uses It For |
|-------|---------------|-----------------------------|
| `SessionStart` | When session begins or resumes | Auto-start the FastAPI service if not running |
| `Stop` | When Claude finishes responding | Extract `last_assistant_message`, filter, POST to TTS |
| `SessionEnd` | When session terminates | Optional: stop service or leave running |

### Stop Hook — Input Schema

The `Stop` hook is the primary integration point. It receives via stdin:

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": true,
  "last_assistant_message": "I've completed the refactoring. Here's a summary..."
}
```

Key fields:
- `last_assistant_message` — the full text of Claude's final response. **This is the primary field to extract and send to TTS.** No transcript parsing needed.
- `stop_hook_active` — `true` if Claude is already continuing due to a previous Stop hook. Must check this to avoid infinite loops.

The hook configuration in `~/.claude/settings.json` or `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/path/to/claudetalk/hook.py"
          }
        ]
      }
    ]
  }
}
```

### SessionStart Hook — Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "SessionStart",
  "source": "startup",
  "model": "claude-sonnet-4-6"
}
```

Use `matcher: "startup"` to fire only on new sessions, not on resume or compact.

### Hook Execution Notes

- Hooks run as shell commands receiving JSON on stdin
- Command hooks have a default 600-second timeout
- All matching hooks run in parallel
- `Stop` hook does NOT support matchers (always fires)
- Hook scripts must handle non-interactive shell (no interactive profile output or JSON parsing breaks)
- On Windows: hook commands run via the shell; use `python` with absolute path or ensure PATH is set

---

## Text Filtering Strategy (What to Speak vs Skip)

**Research basis:** Screen reader behavior analysis + domain knowledge (MEDIUM confidence — no direct prior art for Claude Code TTS filtering)

### Speak

- Plain prose sentences from Claude's response
- Lists expressed as natural language ("First... Second... Third...")
- Questions Claude asks the user
- Summary statements
- Error explanations in plain English

### Skip

| Content Type | Detection Pattern | Rationale |
|---|---|---|
| Code blocks | Between triple backticks or 4-space indented blocks | Code read aloud is unintelligible |
| Inline code | Between single backticks | Short but disruptive |
| File paths | Strings matching `/path/to/file` or `C:\path\to\file` patterns | Meaningless when spoken |
| JSON / structured data | Starts with `{` or `[`, contains structured nesting | Unreadable aloud |
| URLs | Starts with `http://` or `https://` | Spoken URLs are noise |
| ANSI escape codes | `\x1b[...m` sequences | Terminal formatting artifacts |
| Markdown headers | Lines starting with `#` | Read the text beneath instead |
| Table rows | Lines containing multiple `|` characters | Tables cannot be conveyed by linear TTS |
| Repeated emphasis markers | `**bold**` / `*italic*` markers | Strip markers, keep text |

### Filtering Implementation Approach

Strip → then speak. Order:
1. Remove ANSI codes (regex)
2. Remove triple-backtick code blocks (regex, multiline)
3. Remove inline code (regex)
4. Remove URLs (regex)
5. Remove file paths (heuristic: path-like tokens)
6. Strip markdown markers (`**`, `*`, `#`, `|`)
7. Sentence-split remaining text
8. Skip sentences that are still mostly non-alphabetic (< 40% alpha chars)

---

## Windows Installation Patterns

**Source:** PyPI docs, pyinstaller docs, Python packaging guide (HIGH confidence)

### Recommended: pip install with post-install model download

```bash
pip install claudetalk
claudetalk setup   # downloads model files, registers hooks
```

**Why this pattern:**
- Developers expect `pip install` — lowest friction for the target audience
- `pyproject.toml` with a `console_scripts` entry point creates a `claudetalk` command automatically
- Post-install `setup` command handles: model file download (Kokoro ONNX), hook registration in `~/.claude/settings.json`, desktop shortcut creation

**Why NOT PyInstaller exe:**
- Adds ~50-100MB to distribution
- Loses pip upgrade path (`pip install --upgrade claudetalk`)
- ONNX models are already large downloads; bundling them into the exe is impractical
- Developer audience already has Python

**Why NOT installer script (.bat / PowerShell):**
- No standard uninstall path
- Can't express dependencies cleanly
- pip install is idiomatic for Python tools

### Windows-specific notes

- `pip install claudetalk` installs the `claudetalk` command to `%PYTHON%\Scripts\claudetalk.exe` (auto-shim)
- If Python Scripts folder not in PATH: `python -m claudetalk` fallback in documentation
- Virtual environment support: service should work inside a venv; hook must use the same Python as the service
- No admin rights needed for pip install to user site-packages (`pip install --user`)
- Model files stored in `%APPDATA%\claudetalk\models\` (user-writable, no admin)

---

## Windows System Tray UX Patterns

**Source:** pystray docs + Microsoft UX guidelines (MEDIUM confidence — pystray docs HIGH, MS guidelines for right-click items MEDIUM)

### Recommended Right-Click Menu Structure (pystray)

```
[speaking indicator - checkmark when active]
ClaudeTalk  (disabled header item, shows app name)
---separator---
Mute / Unmute        [checkmark]
Current voice: af_sarah  (disabled, informational)
---separator---
Voice >              [submenu]
  af_sarah (current, radio button)
  af_bella
  am_adam
  [more voices...]
---separator---
Start Service
Stop Service
---separator---
Quit
```

**pystray menu implementation notes:**
- `pystray.MenuItem` with `checked=True/False` for mute state
- `pystray.MenuItem` with `enabled=False` for informational labels
- `pystray.Menu.SEPARATOR` for visual grouping
- Dynamic items: use callable for `checked` property so state updates on open
- Call `icon.update_menu()` after state changes to refresh tray menu
- On Windows, pystray right-click fires on right mouse button on the tray icon (default behavior, no extra code needed)
- Left-click on tray icon: can bind `icon.run(setup=on_left_click)` to toggle mute on left-click as shortcut

### Icon Design

- Idle state: microphone icon (gray or dimmed)
- Speaking state: microphone icon (bright, animated if possible — pystray supports icon swapping)
- Muted state: microphone with slash
- Service stopped: no icon (service not running = no tray presence)

---

## MVP Definition

### Launch With (v1)

- [x] **Stop hook extraction** — capture `last_assistant_message`, POST to `/speak` — core value
- [x] **Text filtering pipeline** — strip code blocks, paths, URLs before TTS — without this, the tool is annoying
- [x] **FastAPI `/speak` endpoint** — accepts text, synthesizes with Kokoro, plays audio
- [x] **System tray icon** — shows service is running; right-click "Quit" is minimum viable tray UX
- [x] **Mute toggle** — in tray menu and via slash command — critical for real-world use
- [x] **SessionStart auto-launch** — so users don't have to think about starting the service
- [x] **`pip install claudetalk` + `claudetalk setup`** — single-command installation

### Add After Validation (v1.x)

- [ ] **Voice switching** (`/claudetalk:voice`) — validate that users want multiple voices before building the selector UI
- [ ] **Model switching** (`/claudetalk:model`) — Piper backend needs separate integration work
- [ ] **Tray icon speaking indicator** — animate icon during TTS; confirm users notice and value it
- [ ] **Sentence-chunked delivery** — if users report TTS starting "too late" after long responses

### Future Consideration (v2+)

- [ ] **Piper backend** — lighter weight alternative; defer until Kokoro quality complaints arise
- [ ] **Language/voice packs** — only if international users request; complicates model management
- [ ] **Transcript playback** — "read that again" — only if users report missing responses due to distraction

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Stop hook + `/speak` endpoint | HIGH | MEDIUM | P1 |
| Text filtering pipeline | HIGH | MEDIUM | P1 |
| System tray icon (basic) | HIGH | LOW | P1 |
| Mute toggle (tray + command) | HIGH | LOW | P1 |
| SessionStart auto-launch | HIGH | LOW | P1 |
| pip install + claudetalk setup | HIGH | MEDIUM | P1 |
| Voice switching | MEDIUM | LOW | P2 |
| Model switching (Kokoro/Piper) | MEDIUM | MEDIUM | P2 |
| Tray speaking status indicator | MEDIUM | LOW | P2 |
| Sentence-chunked delivery | MEDIUM | MEDIUM | P2 |
| Piper TTS backend | LOW | MEDIUM | P3 |
| Multi-language voices | LOW | HIGH | P3 |
| Transcript playback | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | Generic Screen Readers (NVDA, Narrator) | VoiceMode (MCP server) | ClaudeTalk (our approach) |
|---------|----------------------------------------|------------------------|--------------------------|
| Text filtering | Read everything including metadata | Relies on conversation context | Targeted: strip code/paths/JSON, speak prose only |
| Voice switching | System-level, not context-aware | OpenAI voices or Kokoro via config | Slash command inline, no context switch |
| Claude Code integration | None (screen captures terminal) | MCP server (different integration) | Official hooks: `Stop` + `SessionStart` |
| Local-only | Yes (screen reader is local) | Optional (cloud or local) | Enforced local-only by design |
| Installation | Windows built-in or exe installer | npm/node MCP setup | pip install (Python native) |
| System tray | No | No | Yes — visual service presence |
| Model quality | Platform TTS (lower quality) | GPT-4o or Kokoro | Kokoro (high quality, 82M params) |

---

## Sources

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) — HIGH confidence (official Anthropic docs, accessed 2026-02-26)
- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide) — HIGH confidence (official Anthropic docs, accessed 2026-02-26)
- [pystray Usage Documentation](https://pystray.readthedocs.io/en/latest/usage.html) — HIGH confidence (official library docs)
- [kokoro-tts CLI](https://github.com/nazdridoy/kokoro-tts) — MEDIUM confidence (GitHub, community implementation)
- [Kokoro TTS - Voice Mode integration](https://voice-mode.readthedocs.io/en/stable/kokoro/) — MEDIUM confidence (third-party integration docs showing voice names)
- [PyInstaller documentation](https://pyinstaller.org/en/stable/) — HIGH confidence (official docs)
- [Python Packaging Guide](https://packaging.python.org/tutorials/installing-packages/) — HIGH confidence (official Python docs)
- [Microsoft TTS vs Screen Reader differences](https://www.microsoft.com/en-us/windows/learning-center/tts-screen-reader-difference) — MEDIUM confidence (Microsoft official)
- [Kokoro 82M install guide](https://aleksandarhaber.com/kokoro-82m-install-and-run-locally-fast-small-and-free-text-to-speech-tts-ai-model-kokoro-82m/) — LOW confidence (blog, used for voice names only)

---
*Feature research for: Developer TTS companion app (ClaudeTalk)*
*Researched: 2026-02-26*

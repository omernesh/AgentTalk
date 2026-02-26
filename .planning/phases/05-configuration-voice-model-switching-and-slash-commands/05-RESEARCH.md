# Phase 5: Configuration, Voice/Model Switching, and Slash Commands - Research

**Researched:** 2026-02-26
**Domain:** Claude Code slash command registration, JSON config persistence, Piper TTS integration, FastAPI runtime config endpoints
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CMD-01 | `/agenttalk:start` slash command launches the AgentTalk service if not running | Slash command = `~/.claude/commands/agenttalk/start.md`; executes session_start_hook pattern (pythonw + subprocess.Popen DETACHED) |
| CMD-02 | `/agenttalk:stop` slash command kills the service and silences any current audio | Slash command = `~/.claude/commands/agenttalk/stop.md`; POSTs to new `POST /stop` FastAPI endpoint; stop endpoint calls `sd.stop()` then `os._exit(0)` |
| CMD-03 | `/agenttalk:voice [name]` slash command switches the active Kokoro voice by name | Slash command = `~/.claude/commands/agenttalk/voice.md` with `$ARGUMENTS`; POSTs to new `POST /config` endpoint; service sets `STATE["voice"]` immediately and writes config.json |
| CMD-04 | `/agenttalk:model [kokoro\|piper]` slash command switches the active TTS engine | Slash command = `~/.claude/commands/agenttalk/model.md` with `$ARGUMENTS`; POSTs to `POST /config`; service swaps active engine and writes config.json |
| CFG-01 | All settings persist in `%APPDATA%\AgentTalk\config.json` (no admin rights required) | `save_config()` added to `config_loader.py`; atomic write via `tmp.replace(config.json)`; no admin rights for APPDATA |
| CFG-02 | Persisted settings include: active voice, speech speed, output volume, TTS model, mute state, pre-speech cue path, post-speech cue path | All 7 keys already live in `STATE` dict; `save_config()` reads STATE and serialises to config.json |
| CFG-03 | Config changes take effect immediately without service restart | `STATE` dict is read at synthesis time (existing tts_worker design); writing STATE keys from a new FastAPI `/config` endpoint achieves immediate effect |
| TTS-04 | Piper TTS available as alternate engine, switchable at runtime via `/agenttalk:model` | `piper-tts` package (piper1-gpl, v1.4.1 Feb 2026, pip-installable); `PiperVoice.load()` + `synthesize()` API; lazy-load at first switch to avoid startup cost |
</phase_requirements>

---

## Summary

Phase 5 has three distinct work streams that must be composed together: (1) registering Claude Code slash commands with the correct namespace, (2) adding FastAPI control endpoints to the running service so those commands have something to call, and (3) adding `save_config()` to the existing config_loader module so changes persist across restarts. A fourth stream adds Piper TTS as a second engine behind a runtime switch.

The slash command system in Claude Code uses a subdirectory-based namespace convention: a Markdown file at `~/.claude/commands/agenttalk/stop.md` creates the command `/agenttalk:stop`. Commands can execute shell commands using the `!`cmd`` syntax in SKILL.md frontmatter, or — for simple service interactions — they can simply instruct Claude to use the `Bash` tool to POST to the localhost FastAPI endpoint. The service already runs on `localhost:5050`, which is the cleanest integration point.

The `STATE` dict in `tts_worker.py` is already the single source of truth for all runtime settings; `tts_worker._tts_worker()` reads it at synthesis time, so any change to it takes effect on the next sentence. The only missing pieces are: a `POST /config` endpoint that updates `STATE` keys, a `POST /stop` endpoint that silences audio and exits, a `save_config()` function in `config_loader.py` that writes STATE to disk, and the Piper engine wrapper that can substitute for Kokoro. The `agenttalk setup` module (Phase 6) will handle distributing the slash command files — Phase 5 only needs to create them.

**Primary recommendation:** Create four Markdown slash command files in `~/.claude/commands/agenttalk/`, add `POST /config` and `POST /stop` to the FastAPI service, add `save_config()` to `config_loader.py`, and wrap Piper TTS behind a thin engine interface with lazy loading.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| piper-tts (piper1-gpl) | >=1.4.1 (Feb 2026 latest) | Alternate offline TTS engine | Official successor to archived rhasspy/piper; pip-installable on Windows; ONNX-based |
| json (stdlib) | stdlib | Read/write config.json | No dependencies; existing load_config() already uses it |
| pathlib (stdlib) | stdlib | APPDATA path construction | Already used throughout the codebase |
| fastapi (existing) | current | New `/config` and `/stop` endpoints | Already running; zero new infra |
| urllib.request (stdlib) | stdlib | Slash command calls to service | Already used in stop_hook.py; no extra deps |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| threading.Lock | stdlib | Guard concurrent config writes | When multiple FastAPI requests could call save_config() simultaneously |
| sounddevice | existing | `sd.stop()` to silence current audio on /stop | Already imported in service.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `~/.claude/commands/` (personal) | `.claude/commands/` (project) | Personal = works in all projects (correct for AgentTalk); project = only in this repo |
| SKILL.md with `allowed-tools: Bash` | Plain .md without Bash | Bash variant lets command POST directly; plain variant requires Claude to decide; Bash is more reliable |
| Lazy Piper load on first use | Eager load at startup | Eager adds 2-5s startup cost every time; lazy only pays cost when user explicitly switches to Piper |

**Installation:**
```bash
pip install piper-tts
```

Model download (run once during setup):
```bash
python -m piper.download_voices en_US-lessac-medium
```

---

## Architecture Patterns

### Recommended Project Structure
```
~/.claude/commands/
└── agenttalk/
    ├── start.md       # /agenttalk:start — launch service
    ├── stop.md        # /agenttalk:stop  — kill service + silence audio
    ├── voice.md       # /agenttalk:voice [name] — switch voice
    └── model.md       # /agenttalk:model [kokoro|piper] — switch engine

agenttalk/
├── config_loader.py   # add save_config() alongside existing load_config()
├── tts_worker.py      # add ENGINE key to STATE; add engine-switching logic
├── service.py         # add POST /config, POST /stop, POST /start endpoints
└── piper_engine.py    # NEW: thin wrapper around PiperVoice for engine interface
```

### Pattern 1: Claude Code Slash Command Namespace via Subdirectory

**What:** Placing a Markdown file at `~/.claude/commands/agenttalk/voice.md` registers the command `/agenttalk:voice` in Claude Code. The subdirectory name becomes the namespace prefix.

**When to use:** Whenever you need namespaced commands that avoid collisions with user's own commands.

**Example (`~/.claude/commands/agenttalk/voice.md`):**
```markdown
---
name: voice
description: Switch the active AgentTalk TTS voice
argument-hint: [voice-name]
disable-model-invocation: true
allowed-tools: Bash
---

Switch the AgentTalk voice to $ARGUMENTS.

Run this bash command to update the voice:
```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"voice\": \"$ARGUMENTS\"}"
```

If the service is not running, say so and suggest running `/agenttalk:start`.
```

Source: [Claude Code Skills docs](https://code.claude.com/docs/en/skills), [danielcorin.com namespace article](https://www.danielcorin.com/til/anthropic/custom-slash-commands-hierarchy/)

### Pattern 2: FastAPI Config Endpoint — Partial Updates

**What:** `POST /config` accepts a partial JSON body and updates only the provided keys in `STATE`. Immediately calls `save_config()` to persist. Any missing key leaves the current value unchanged.

**When to use:** Slash commands that change one setting at a time (voice, model, speed, volume, mute).

**Example:**
```python
# Source: project pattern based on existing FastAPI service
from pydantic import BaseModel
from typing import Optional

class ConfigRequest(BaseModel):
    voice: Optional[str] = None
    speed: Optional[float] = None
    volume: Optional[float] = None
    model: Optional[str] = None       # "kokoro" or "piper"
    muted: Optional[bool] = None
    pre_cue_path: Optional[str] = None
    post_cue_path: Optional[str] = None

@app.post("/config", status_code=200)
async def update_config(req: ConfigRequest):
    """Update one or more runtime settings. Changes take effect immediately."""
    updates = req.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key in STATE:
            STATE[key] = value
    # Persist all settings to disk
    save_config(STATE)
    return JSONResponse({"status": "ok", "updated": list(updates.keys())})
```

### Pattern 3: Atomic Config Write

**What:** Write config.json via a temp file then `Path.replace()` to ensure no partial writes. Protected by a module-level `threading.Lock` for concurrent FastAPI requests.

**When to use:** Any time STATE is persisted to disk.

**Example:**
```python
# Source: atomic write pattern, verified with Python docs and setup.py precedent in codebase
import json
import threading
import pathlib

_CONFIG_LOCK = threading.Lock()

def save_config(state: dict) -> None:
    """
    Persist the current STATE to config.json atomically.

    Uses write-to-tmp + Path.replace() so a crash never leaves a half-written file.
    Protected by _CONFIG_LOCK against concurrent FastAPI requests.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Extract persisted keys only (CFG-02)
    persisted = {
        "voice": state.get("voice", "af_heart"),
        "speed": state.get("speed", 1.0),
        "volume": state.get("volume", 1.0),
        "model": state.get("model", "kokoro"),
        "muted": state.get("muted", False),
        "pre_cue_path": state.get("pre_cue_path"),
        "post_cue_path": state.get("post_cue_path"),
    }

    tmp = path.with_suffix(".json.tmp")
    with _CONFIG_LOCK:
        tmp.write_text(json.dumps(persisted, indent=2), encoding="utf-8")
        tmp.replace(path)  # os.replace() — atomic on Windows (Python 3.3+)
```

### Pattern 4: Piper Engine Wrapper

**What:** A thin `PiperEngine` class implementing the same interface as Kokoro: `create(text, voice, speed, lang) -> (samples, rate)`. Lazy-loaded on first model switch.

**When to use:** When `STATE["model"]` is switched to `"piper"` via `/config` or slash command.

**Example:**
```python
# Source: piper1-gpl Python API docs — https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
import io
import wave
import numpy as np
from piper_tts import PiperVoice, SynthesisConfig

class PiperEngine:
    """
    Thin wrapper around PiperVoice that exposes the same interface as Kokoro:
        create(text, voice, speed, lang) -> (np.ndarray[float32], int sample_rate)
    """
    def __init__(self, model_path: str):
        self._voice = PiperVoice.load(model_path)
        self._sample_rate = 22050  # Piper default

    def create(self, text: str, voice: str = None, speed: float = 1.0, lang: str = "en-us"):
        """
        Synthesize text. Returns (float32 samples, sample_rate).
        'voice' param is ignored — Piper uses the model's built-in voice.
        'speed' maps to SynthesisConfig(length_scale=1.0/speed).
        """
        cfg = SynthesisConfig(length_scale=1.0 / max(speed, 0.1))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self._voice.synthesize_wav(text, wf, syn_config=cfg)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            self._sample_rate = wf.getframerate()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return samples, self._sample_rate
```

### Pattern 5: Stop Endpoint — Silence + Exit

**What:** `POST /stop` calls `sd.stop()` to cut current audio, then `os._exit(0)` which terminates the process including the tray (same pattern as the existing `_on_quit()` callback).

**Example:**
```python
@app.post("/stop", status_code=200)
async def stop_service():
    """Kill the service. Silences current TTS immediately."""
    import sounddevice as sd
    sd.stop()          # Interrupt any currently playing audio
    os._exit(0)        # Terminate process tree (same as tray Quit)
```

### Pattern 6: Startup Config Loading — Full State Hydration

**What:** On startup, `load_config()` is called and ALL persisted keys are applied to `STATE` (not just cue paths as in Phase 4). This ensures voice, model, speed, volume, and mute are restored from disk.

**Example:**
```python
# In service.py main(), extend the existing _cfg section:
_cfg = load_config()
for key in ("voice", "speed", "volume", "model", "muted", "pre_cue_path", "post_cue_path"):
    if key in _cfg and _cfg[key] is not None:
        STATE[key] = _cfg[key]
        logging.info("Config restored: %s = %s", key, STATE[key])
```

### Anti-Patterns to Avoid

- **Registering slash commands in `.claude/commands/` (project-level):** Commands would only work inside the AgentTalk repo directory. AgentTalk commands must be personal (`~/.claude/commands/agenttalk/`) so they work in any Claude Code session.
- **Blocking FastAPI with Piper init on startup:** Piper load takes 2-5 seconds. Loading it at startup adds latency even when the user never uses Piper. Use lazy init — load PiperEngine only when model switches to "piper".
- **Writing config.json from tts_worker thread without a lock:** FastAPI runs in a thread; tts_worker runs in a thread; both could call save_config() concurrently. The `threading.Lock` in save_config() prevents interleaved writes.
- **Using `sys.exit()` in the /stop endpoint:** `sys.exit()` raises SystemExit, which daemon threads can swallow. Use `os._exit(0)` (same as existing `_on_quit()`).
- **Storing model-specific state (Piper model path) in STATE without a defined key:** STATE must gain a `"model"` key ("kokoro" or "piper") and a `"piper_model_path"` key so the engine can be re-initialized after restart.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slash command registration | Custom hook or registry script | Markdown files in `~/.claude/commands/agenttalk/` | Claude Code discovers them automatically; zero code required |
| Atomic file writes | Open file + try/write/except | `tmp.write_text() + tmp.replace()` | `.replace()` is atomic on Windows (Python 3.3+); exact pattern already used in `setup.py` |
| Piper audio synthesis | Custom ONNX inference loop | `PiperVoice.synthesize_wav()` or `PiperVoice.synthesize()` | Piper handles phonemization (espeak-ng), ONNX inference, and WAV formatting |
| Service process discovery for /start | Custom PID scanning | Read existing `PID_FILE`; spawn via same `PYTHONW_PATH_FILE` pattern as `session_start_hook.py` | Pattern already implemented and tested |

**Key insight:** The FastAPI service is already the integration point. Slash commands only need to POST JSON to localhost:5050. No custom IPC, no pipes, no shared memory.

---

## Common Pitfalls

### Pitfall 1: Personal vs. Project Slash Command Location

**What goes wrong:** Commands placed in `.claude/commands/` (project-level) only work when Claude Code's cwd is the AgentTalk project directory. `/agenttalk:stop` would fail in any other project.
**Why it happens:** Claude Code has two levels — project (`.claude/`) and personal (`~/.claude/`). AgentTalk commands need to be personal since they control a system-wide service.
**How to avoid:** Always place AgentTalk slash commands in `~/.claude/commands/agenttalk/`. Note: `agenttalk setup` (Phase 6) must write these files to the user's home directory, not the project.
**Warning signs:** Commands appear in the `/` menu only when cwd is the AgentTalk repo.

### Pitfall 2: Colon Namespace Requires Subdirectory, Not Filename

**What goes wrong:** Creating `~/.claude/commands/agenttalk:stop.md` (colon in filename) instead of `~/.claude/commands/agenttalk/stop.md` (subdirectory). Windows filesystems forbid colons in filenames.
**Why it happens:** Reading `/namespace:command` as a filename convention rather than a directory convention.
**How to avoid:** The namespace is the directory name. The command name is the filename. Subdirectory = `agenttalk/`, file = `stop.md` → command = `/agenttalk:stop`.
**Warning signs:** `FileNotFoundError` or file creation fails on Windows.

### Pitfall 3: Piper Voice Models Not Bundled

**What goes wrong:** User switches to Piper model via `/agenttalk:model piper` and PiperEngine fails with "model file not found" because no voice model has been downloaded.
**Why it happens:** `piper-tts` package installs the API but not any voice models. Models must be downloaded separately.
**How to avoid:** Store the Piper model path in `STATE["piper_model_path"]` and in `config.json`. If no path is configured when the user switches to Piper, return a clear error from `/config`: `{"status": "error", "reason": "No Piper model configured. Run agenttalk setup --piper to download a model."}`.
**Warning signs:** PiperVoice.load() raises FileNotFoundError.

### Pitfall 4: Partial config.json Writes on Windows

**What goes wrong:** A second process (or concurrent request) reads `config.json` while the first write is in progress, getting truncated JSON that fails to parse.
**Why it happens:** Writing directly to the final path is not atomic on Windows when the file exists.
**How to avoid:** Always write to `config.json.tmp` then call `tmp.replace(config.json)`. `Path.replace()` calls `os.replace()` which is atomic on Windows for files in the same filesystem. Pattern already established in `setup.py`.
**Warning signs:** `load_config()` logging "Failed to load config from ... — using defaults" on startup after a crash.

### Pitfall 5: STATE Does Not Have "model" Key Yet

**What goes wrong:** Phase 4's `STATE` dict in `tts_worker.py` does not include `"model"` or `"piper_model_path"` keys. Adding engine switching requires adding these keys and updating the tts_worker loop to select the engine at synthesis time.
**Why it happens:** TTS-04 (Piper) was deferred from earlier phases.
**How to avoid:** Add `"model": "kokoro"` and `"piper_model_path": None` to STATE in Phase 5. Modify `_tts_worker()` to call `_get_active_engine()` which returns either `_kokoro_engine` or a lazy-loaded `_piper_engine`.
**Warning signs:** `KeyError: "model"` in tts_worker when /config sets `model`.

### Pitfall 6: `/agenttalk:stop` Slash Command Timing

**What goes wrong:** The slash command POST to `/stop` succeeds but the service process exits before returning the HTTP response, causing `urllib.error.URLError` (connection reset). The command should treat this as success, not failure.
**Why it happens:** `os._exit(0)` terminates the process immediately, dropping the HTTP connection.
**How to avoid:** The slash command's Bash invocation should use `curl` with `--max-time 2` and treat both exit codes 0 and 52/56 (connection reset) as success. Or use a sentinel: send a 200 before the thread that calls os._exit.
**Warning signs:** Slash command reports error even though service stopped correctly.

### Pitfall 7: Piper Sample Rate Mismatch

**What goes wrong:** Piper outputs 22050 Hz audio; the service's WASAPI detection was configured for Kokoro's 24000 Hz. `sd.play()` may produce distorted audio at incorrect pitch.
**Why it happens:** `sounddevice` uses the sample rate passed to `sd.play(samplerate=rate)`. As long as `rate` is read from `PiperEngine.create()` return value, sounddevice resamples correctly. The bug is reading a hardcoded rate instead of the returned value.
**How to avoid:** Always use the `rate` returned by `engine.create()` — never hardcode 24000 in the TTS worker loop. This is already the pattern in the existing worker.
**Warning signs:** Piper speech sounds low-pitched (too slow) — would indicate wrong sample rate was passed.

---

## Code Examples

Verified patterns from official sources:

### Slash Command File: `/agenttalk:stop`
```markdown
---
name: stop
description: Stop the AgentTalk TTS service and silence any current audio
disable-model-invocation: true
allowed-tools: Bash
---

Stop the AgentTalk service by sending a stop request.

Run:
```bash
curl -s -X POST http://localhost:5050/stop --max-time 3 || true
```

If the command fails because the service is already stopped, say "AgentTalk service was not running."
If it succeeds or the connection was reset (service stopped), say "AgentTalk service stopped."
```

### Slash Command File: `/agenttalk:voice`
```markdown
---
name: voice
description: Switch the AgentTalk TTS voice. Available voices: af_heart, af_bella, af_nicole, af_sarah, af_sky, am_adam, am_michael, bf_emma, bf_isabella, bm_george, bm_lewis
argument-hint: [voice-name]
disable-model-invocation: true
allowed-tools: Bash
---

Switch the AgentTalk TTS voice to $ARGUMENTS.

Run:
```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"voice\": \"$ARGUMENTS\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, say "Voice switched to $ARGUMENTS. The next utterance will use this voice."
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."
```

### Slash Command File: `/agenttalk:model`
```markdown
---
name: model
description: Switch the AgentTalk TTS engine. Options: kokoro, piper
argument-hint: [kokoro|piper]
disable-model-invocation: true
allowed-tools: Bash
---

Switch the AgentTalk TTS engine to $ARGUMENTS.

Run:
```bash
curl -s -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"$ARGUMENTS\"}" \
  --max-time 5
```

If the response contains `"status": "ok"`, say "TTS engine switched to $ARGUMENTS."
If the response contains `"status": "error"`, display the error reason.
If the connection is refused, say "AgentTalk service is not running. Start it with /agenttalk:start."
```

### Slash Command File: `/agenttalk:start`
```markdown
---
name: start
description: Start the AgentTalk TTS service if it is not already running
disable-model-invocation: true
allowed-tools: Bash
---

Start the AgentTalk service.

First, check if it's already running:
```bash
curl -s http://localhost:5050/health --max-time 2
```

If the health check returns `"status": "ok"`, say "AgentTalk is already running."

If the health check fails (connection refused), launch the service:
```bash
python -c "
import subprocess, os, sys
from pathlib import Path
appdata = Path(os.environ['APPDATA']) / 'AgentTalk'
pythonw = (appdata / 'pythonw_path.txt').read_text().strip()
service = (appdata / 'service_path.txt').read_text().strip()
subprocess.Popen([pythonw, service], creationflags=0x00000008|0x00000200, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print('Service launched')
"
```

Say "AgentTalk service is starting. It will be ready in about 10 seconds."
```

### save_config() Implementation
```python
# Source: established in setup.py (same atomic write pattern) + Python docs os.replace()
import json
import threading
import pathlib
import os
import logging

_CONFIG_LOCK = threading.Lock()

def save_config(state: dict) -> None:
    """
    Persist runtime state to config.json atomically.

    Writes to .json.tmp then calls Path.replace() — atomic on Windows
    (os.replace() is guaranteed atomic within the same filesystem).

    Thread-safe via _CONFIG_LOCK — both FastAPI handler thread and
    potentially the tts_worker thread could call this concurrently.

    CFG-01: Writes to %APPDATA%/AgentTalk/config.json (no admin rights).
    CFG-02: Persists all 7 settings fields.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    persisted = {
        "voice":         state.get("voice", "af_heart"),
        "speed":         state.get("speed", 1.0),
        "volume":        state.get("volume", 1.0),
        "model":         state.get("model", "kokoro"),
        "muted":         state.get("muted", False),
        "pre_cue_path":  state.get("pre_cue_path"),
        "post_cue_path": state.get("post_cue_path"),
    }
    tmp = path.with_suffix(".json.tmp")
    with _CONFIG_LOCK:
        tmp.write_text(json.dumps(persisted, indent=2), encoding="utf-8")
        tmp.replace(path)
    logging.debug("Config saved to %s", path)
```

### Engine Switching in tts_worker
```python
# Engine registry — module-level
_kokoro_engine = None   # Set by start_tts_worker()
_piper_engine = None    # Lazy-loaded on first Piper synthesis

def _get_active_engine(kokoro):
    """Return the active TTS engine based on STATE['model']."""
    global _piper_engine
    model = STATE.get("model", "kokoro")
    if model == "piper":
        if _piper_engine is None:
            piper_path = STATE.get("piper_model_path")
            if not piper_path:
                raise RuntimeError("Piper model path not configured")
            from agenttalk.piper_engine import PiperEngine
            _piper_engine = PiperEngine(piper_path)
        return _piper_engine
    return kokoro  # default: Kokoro

# In _tts_worker(), replace direct kokoro_engine.create() call:
engine = _get_active_engine(kokoro_engine)
samples, rate = engine.create(sentence, voice=STATE["voice"], speed=STATE["speed"], lang="en-us")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| rhasspy/piper | OHF-Voice/piper1-gpl (`pip install piper-tts`) | Archived Oct 2025; piper1-gpl active as of Feb 2026 | Same pip install name; Python API changed from subprocess to `PiperVoice` class |
| `.claude/commands/mycommand.md` (flat) | `.claude/commands/namespace/command.md` (subdirectory) | Claude Code update (2025) | Subdirectory creates `/namespace:command` — cleaner organization |
| Custom slash commands | Skills (SKILL.md) | 2025 | `.claude/commands/` still works; Skills are the new canonical path |

**Deprecated/outdated:**
- `rhasspy/piper` (github.com/rhasspy/piper): archived Oct 2025. Do not reference this repo. Use `pip install piper-tts` which installs from OHF-Voice/piper1-gpl.
- Flat command files like `~/.claude/commands/agenttalk-stop.md`: creates `/agenttalk-stop`, not `/agenttalk:stop`. Use subdirectory instead.

---

## Open Questions

1. **Piper model default path location**
   - What we know: Piper models are downloaded via `python -m piper.download_voices <voice>` and stored in a system/user path. The exact default varies by OS.
   - What's unclear: Where does `piper-tts` store models on Windows by default? Is it `%APPDATA%\piper-tts\` or a site-packages location?
   - Recommendation: Store the Piper model explicitly in `%APPDATA%\AgentTalk\models\piper\` (same as Kokoro model directory) and require `piper_model_path` in config.json. Phase 6 (`agenttalk setup --piper`) handles the download.

2. **`/agenttalk:stop` HTTP connection reset**
   - What we know: `os._exit(0)` terminates before the HTTP response fully delivers. `curl` may exit with code 52 or 56 (connection reset by peer).
   - What's unclear: Does the slash command's Claude invocation treat non-zero curl exit codes as errors?
   - Recommendation: Use `|| true` after the curl call in the stop command markdown so the Bash tool always exits 0. Instruct Claude to check for "stopped" wording or connection reset as success.

3. **`agenttalk setup` slash command distribution (Phase 6 boundary)**
   - What we know: Phase 5 creates the `.md` files; Phase 6's `agenttalk setup` copies them to `~/.claude/commands/agenttalk/`.
   - What's unclear: Should Phase 5 also write a dev-mode helper to install them manually, or leave that entirely to Phase 6?
   - Recommendation: Phase 5 creates the files in the project at `agenttalk/commands/` and documents how to manually symlink or copy them. Phase 6 automates the copy via `agenttalk setup`.

---

## Sources

### Primary (HIGH confidence)
- [Claude Code Skills docs](https://code.claude.com/docs/en/skills) — slash command namespace convention, SKILL.md frontmatter, `$ARGUMENTS` substitution, `allowed-tools`, `disable-model-invocation`
- [danielcorin.com — Custom Slash Commands Hierarchy](https://www.danielcorin.com/til/anthropic/custom-slash-commands-hierarchy/) — confirmed subdirectory → namespace:command mapping
- [OHF-Voice/piper1-gpl Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md) — `PiperVoice.load()`, `synthesize_wav()`, `synthesize()`, `SynthesisConfig(length_scale=)`, output format (16-bit WAV)
- [rhasspy/piper archived notice](https://github.com/rhasspy/piper) — confirmed archived Oct 2025; development moved to OHF-Voice/piper1-gpl
- Project codebase — `config_loader.py`, `tts_worker.py`, `service.py`, `setup.py` — existing patterns confirmed by direct read

### Secondary (MEDIUM confidence)
- [OHF-Voice/piper1-gpl README](https://github.com/OHF-Voice/piper1-gpl) — v1.4.1 released Feb 2026; `pip install piper-tts`; Python API confirmed available
- [Python docs — os.replace()](https://docs.python.org/3/library/os.html) — atomic on Windows within same filesystem (Python 3.3+); used in `setup.py` already
- Multiple community sources on namespace:command pattern corroborating subdirectory convention

### Tertiary (LOW confidence)
- Piper default model storage path on Windows: not confirmed from official docs — treat as open question

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — piper-tts verified from official repo; config patterns verified from codebase; slash command system verified from official docs
- Architecture: HIGH — all patterns derive from existing project code or official Claude Code docs
- Pitfalls: HIGH — most pitfalls are verified from existing codebase decisions (e.g., os._exit pattern from `_on_quit`, atomic write from `setup.py`, namespace from docs)
- Piper engine integration: MEDIUM — Python API verified, but Windows-specific behavior (DLL deps, model paths) not validated on real device

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days — both Claude Code slash commands and piper-tts are actively maintained)

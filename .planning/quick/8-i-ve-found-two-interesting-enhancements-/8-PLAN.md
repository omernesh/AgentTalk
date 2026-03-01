---
phase: quick-8
plan: 8
type: execute
wave: 1
depends_on: []
files_modified:
  - agenttalk/lightblue_engine.py
  - agenttalk/hebrewpiper_engine.py
  - agenttalk/tts_worker.py
  - agenttalk/service.py
  - agenttalk/config_loader.py
  - agenttalk/commands/model.md
  - docs/hebrew-tts-setup.md
autonomous: true
requirements: [QUICK-8]

must_haves:
  truths:
    - "User can set model='lightblue' via POST /config and AgentTalk speaks Hebrew text using Light-BlueTTS"
    - "User can set model='hebrewpiper' via POST /config and AgentTalk speaks Hebrew text via PiperStream Docker service"
    - "Hebrew engine selection persists in config.json and survives service restart"
    - "Non-Hebrew engines (kokoro, piper) are unaffected by this change"
    - "/voices returns Hebrew voice options when model is lightblue or hebrewpiper"
  artifacts:
    - path: "agenttalk/lightblue_engine.py"
      provides: "LightBlueTTSEngine — Kokoro-compatible wrapper around Light-BlueTTS HebrewTTS class"
      exports: ["LightBlueTTSEngine"]
    - path: "agenttalk/hebrewpiper_engine.py"
      provides: "HebrewPiperEngine — Kokoro-compatible wrapper around PiperStream REST API"
      exports: ["HebrewPiperEngine"]
    - path: "agenttalk/tts_worker.py"
      provides: "Updated _get_active_engine() routing lightblue and hebrewpiper model names to new engines"
    - path: "agenttalk/service.py"
      provides: "Updated /config model literal type, /voices endpoint for Hebrew voices, /hebrew-voices endpoint"
    - path: "agenttalk/config_loader.py"
      provides: "Extended save_config() persisting all 5 Hebrew config keys so settings survive restart"
    - path: "docs/hebrew-tts-setup.md"
      provides: "User-facing setup guide for both Hebrew TTS options"
  key_links:
    - from: "agenttalk/tts_worker.py"
      to: "agenttalk/lightblue_engine.py"
      via: "_get_active_engine() dispatches model=='lightblue'"
      pattern: "LightBlueTTSEngine"
    - from: "agenttalk/tts_worker.py"
      to: "agenttalk/hebrewpiper_engine.py"
      via: "_get_active_engine() dispatches model=='hebrewpiper'"
      pattern: "HebrewPiperEngine"
    - from: "agenttalk/lightblue_engine.py"
      to: "HebrewTTS.infer()"
      via: "create() calls tts.infer(text, style_json_path=voice)"
      pattern: "tts.infer"
    - from: "agenttalk/hebrewpiper_engine.py"
      to: "http://localhost:8000/synthesize/stream"
      via: "requests.post() in create()"
      pattern: "requests.post.*synthesize"
    - from: "agenttalk/config_loader.py"
      to: "config.json"
      via: "save_config() persists hebrewpiper_host/voice and lightblue_onnx_dir/phonikud_path/voice_path"
      pattern: "hebrewpiper_host.*lightblue_onnx_dir"
---

<objective>
Research and integration plan for PiperStream and Light-BlueTTS: adding Hebrew TTS support to AgentTalk.

Purpose: AgentTalk currently supports Kokoro (English/multilingual, 11 voices) and Piper ONNX (English
voices via local .onnx files). Both repositories by maxmelichov address Hebrew TTS — a language gap.
This plan adds two Hebrew engine backends behind the existing engine-switching architecture so users
can speak Hebrew by switching model at runtime with no service restart.

Output:
- agenttalk/lightblue_engine.py — Light-BlueTTS wrapper (local Python library, recommended)
- agenttalk/hebrewpiper_engine.py — PiperStream wrapper (Docker REST service, simpler setup)
- Updated tts_worker.py and service.py to route the new model names
- Updated config_loader.py so all 5 Hebrew config keys are persisted and restored on restart
- docs/hebrew-tts-setup.md — setup guide for both approaches
</objective>

<execution_context>
@D:/docker/claudetalk/.planning/quick/8-i-ve-found-two-interesting-enhancements-/8-PLAN.md
</execution_context>

<context>
@D:/docker/claudetalk/.planning/STATE.md
@D:/docker/claudetalk/agenttalk/tts_worker.py
@D:/docker/claudetalk/agenttalk/piper_engine.py
@D:/docker/claudetalk/agenttalk/service.py
@D:/docker/claudetalk/agenttalk/config_loader.py
@D:/docker/claudetalk/pyproject.toml

<research>
## PiperStream (https://github.com/maxmelichov/PiperStream)

Type: Docker-based REST API service (NOT a Python library)
Port: 8000 (localhost)
Hebrew pipeline: raw Hebrew text -> phonikud (auto diacritization) -> Piper ONNX inference -> WAV
Two voices: male (`piper_medium_male.onnx`), female (`piper_medium_female.onnx`)
Sample rate: 22050 Hz, 16-bit mono WAV output

Key endpoint for integration:
  POST http://localhost:8000/synthesize/stream
  Content-Type: application/json
  Body: { "text": "...", "model": "male"|"female", "length_scale": 1.0 }
  Response: StreamingResponse (audio/wav) — WAV header + chunked PCM

Simpler /synthesize/audio returns complete WAV file (better for our use: parse with wave module).

Integration approach:
- HebrewPiperEngine wraps requests.post() calls — NO new Python deps beyond existing `requests`
- User must run `docker compose up` from cloned PiperStream repo + download onnx.zip
- Engine streams complete WAV -> parse with wave module -> return (np.ndarray float32, 22050)
- `hebrewpiper_host` config key for non-default host:port (default: http://localhost:8000)

Setup complexity: Medium (requires Docker + model download)

## Light-BlueTTS (https://github.com/maxmelichov/Light-BlueTTS)

Type: Local Python library (direct import, no network service)
License: MIT
Python version: >= 3.10 (compatible with project's 3.11 requirement)
Sample rate: 44100 Hz (output from infer())
Voices: Style JSON files in voices/ directory (e.g., female1.json — user clones repo)

Core API:
  from hebrew_inference_helper import HebrewTTS, TTSConfig
  tts = HebrewTTS(TTSConfig(
      onnx_dir="path/to/onnx_models",    # 9 ONNX files required
      phonikud_path="phonikud-1.0.onnx",
      speed=1.0,
      use_gpu=False,
  ))
  wav = tts.infer(text, style_json_path="path/to/voices/female1.json")
  # wav = np.ndarray[float32], sample_rate=44100

Returns np.ndarray float32 — IDENTICAL to existing engine interface:
  create(text, voice, speed, lang) -> (np.ndarray[float32], int sample_rate)

Integration approach:
- LightBlueTTSEngine.__init__(onnx_dir, phonikud_path) -> lazy loads HebrewTTS
- create(text, voice, speed, lang) -> (wav, 44100)
  - voice param = absolute path to a voices/*.json style file
  - speed -> TTSConfig(speed=speed) (recreate config on speed change OR store speed in create())
- `lightblue_onnx_dir` and `lightblue_phonikud_path` config keys
- New deps: numpy (already present), onnxruntime, phonikud, phonikud-onnx, soundfile, torch>=2.10

CRITICAL DEPS NOTE: Light-BlueTTS requires torch>=2.10.0. This is a ~2GB dependency not currently
in AgentTalk. This makes Light-BlueTTS an OPTIONAL extra in pyproject.toml, not a core dep.
Installation: pip install light-blue-tts (if published) OR pip install -e path/to/Light-BlueTTS

Setup complexity: High (9 ONNX model files + phonikud model + torch + clone repo)

## Architecture Fit

Both repos fit the existing pluggable engine pattern in tts_worker._get_active_engine():
  - model == "kokoro"      -> Kokoro engine (existing)
  - model == "piper"       -> PiperEngine (existing)
  - model == "lightblue"   -> LightBlueTTSEngine (new)
  - model == "hebrewpiper" -> HebrewPiperEngine (new)

STATE dict needs two new config keys:
  - "lightblue_onnx_dir": str|None  — path to onnx_models dir
  - "lightblue_phonikud_path": str|None — path to phonikud-1.0.onnx
  - "lightblue_voice_path": str|None — path to current voices/*.json file
  - "hebrewpiper_host": str  — default "http://localhost:8000"
  - "hebrewpiper_voice": "male"|"female"  — default "female"

## Recommendation

HebrewPiperEngine is the simpler integration (Docker + existing `requests` dep, no new Python deps).
LightBlueTTSEngine is the better long-term choice (local, no Docker, same return type, GPU option).

Plan implements BOTH so user can choose based on their setup.
</research>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement HebrewPiperEngine and LightBlueTTSEngine wrappers</name>
  <files>
    agenttalk/hebrewpiper_engine.py
    agenttalk/lightblue_engine.py
  </files>
  <action>
Create two new engine modules following the exact same interface as PiperEngine
(see agenttalk/piper_engine.py for the pattern to follow).

--- agenttalk/hebrewpiper_engine.py ---

Module docstring explaining:
- Wraps the PiperStream REST API (github.com/maxmelichov/PiperStream)
- Speaks Hebrew text by POSTing to http://localhost:8000/synthesize/audio
- Returns (np.ndarray[float32], 22050) matching Kokoro/PiperEngine interface
- Requires: Docker running `docker compose up` in a clone of the PiperStream repo
- No new Python deps beyond existing `requests`

Class HebrewPiperEngine:

  def __init__(self, host: str = "http://localhost:8000", voice: str = "female"):
    - self._host = host.rstrip("/")
    - self._voice = voice  # "male" or "female"
    - Log: "HebrewPiperEngine initialized, host=%s voice=%s"
    - Do NOT call requests here — lazy health check on first create()

  def create(self, text: str, voice: str | None = None, speed: float = 1.0, lang: str = "he") -> tuple[np.ndarray, int]:
    - effective_voice = voice or self._voice  # allow per-call override
    - length_scale = 1.0 / max(float(speed), 0.1)  # same mapping as PiperEngine
    - payload = {"text": text, "model": effective_voice, "length_scale": length_scale}
    - Use requests.post(f"{self._host}/synthesize/audio", json=payload, timeout=30)
    - On ConnectionError: raise RuntimeError("PiperStream not reachable at {host}. Start Docker: docker compose up")
    - On non-200: raise RuntimeError(f"PiperStream /synthesize/audio returned {r.status_code}: {r.text[:200]}")
    - Parse WAV bytes from response.content using wave + io.BytesIO (same pattern as piper_engine.py)
    - Convert int16 PCM to float32 via: samples = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
    - Return (samples, sample_rate_from_wav_header)

--- agenttalk/lightblue_engine.py ---

Module docstring explaining:
- Wraps Light-BlueTTS (github.com/maxmelichov/Light-BlueTTS)
- Local Python inference, no Docker needed
- Returns (np.ndarray[float32], 44100) matching engine interface
- Requires: pip install onnxruntime phonikud phonikud-onnx soundfile torch torchaudio
  AND cloning the repo to get onnx_models/ dir and voices/ dir
- Heavy deps: torch (~2GB) — optional, not in core requirements

Class LightBlueTTSEngine:

  def __init__(self, onnx_dir: str, phonikud_path: str = "phonikud-1.0.onnx", speed: float = 1.0, use_gpu: bool = False):
    - All imports deferred inside __init__ (same lazy pattern as piper_engine.py):
        from hebrew_inference_helper import HebrewTTS, TTSConfig
    - TTSConfig fields: onnx_dir=onnx_dir, phonikud_path=phonikud_path, speed=speed, use_gpu=use_gpu
    - self._tts = HebrewTTS(config)
    - self._speed = speed
    - Log: "LightBlueTTSEngine loaded from %s", onnx_dir

  def create(self, text: str, voice: str | None = None, speed: float = 1.0, lang: str = "he") -> tuple[np.ndarray, int]:
    - voice = voice or "voices/female1.json"  (relative path — user should pass absolute)
    - wav = self._tts.infer(text, style_json_path=voice)
      NOTE: infer() does NOT accept a speed arg directly — speed is baked into TTSConfig.
      If speed != self._speed: reload with new TTSConfig (log a warning: "speed change requires engine reload")
      This is acceptable — speed changes are rare.
    - Return (wav, 44100)  # Light-BlueTTS always outputs 44100 Hz
    - On ImportError: raise ImportError(
        "Light-BlueTTS not installed. Install deps: pip install onnxruntime phonikud phonikud-onnx soundfile torch torchaudio\n"
        "Then clone https://github.com/maxmelichov/Light-BlueTTS and add it to PYTHONPATH."
      )
  </action>
  <verify>
    <automated>cd /d/docker/claudetalk && python -c "from agenttalk.hebrewpiper_engine import HebrewPiperEngine; e = HebrewPiperEngine(); print('HebrewPiperEngine OK')" && python -c "import inspect, agenttalk.lightblue_engine as m; src=inspect.getsource(m); assert 'LightBlueTTSEngine' in src and 'infer' in src; print('LightBlueTTSEngine OK')"</automated>
  </verify>
  <done>
    Both engine files exist and are importable. HebrewPiperEngine() instantiates without network call.
    LightBlueTTSEngine deferred import means it imports cleanly even without torch installed.
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire new engines into tts_worker, service, and config_loader</name>
  <files>
    agenttalk/tts_worker.py
    agenttalk/service.py
    agenttalk/config_loader.py
    agenttalk/commands/model.md
  </files>
  <action>
Update tts_worker.py, service.py, config_loader.py, and commands/model.md to recognize the two new
model names and persist their config keys across service restarts.

--- agenttalk/tts_worker.py ---

1. Add new keys to STATE dict (after existing piper_model_path line):
   "hebrewpiper_host": "http://localhost:8000",  # PiperStream Docker service URL
   "hebrewpiper_voice": "female",                # "male" or "female"
   "lightblue_onnx_dir": None,                   # Absolute path to onnx_models/ dir
   "lightblue_phonikud_path": None,              # Absolute path to phonikud-1.0.onnx
   "lightblue_voice_path": None,                 # Absolute path to a voices/*.json style file

2. Add module-level engine cache variables (after existing _piper_engine/_piper_loaded_path):
   _hebrewpiper_engine = None
   _hebrewpiper_loaded_key: str | None = None  # tracks host+voice combo
   _lightblue_engine = None
   _lightblue_loaded_key: str | None = None  # tracks onnx_dir+phonikud_path combo

3. Update _get_active_engine() to handle the two new model names. After the existing
   `if model == "piper":` block, add:

   elif model == "hebrewpiper":
       global _hebrewpiper_engine, _hebrewpiper_loaded_key
       host = STATE.get("hebrewpiper_host", "http://localhost:8000")
       voice = STATE.get("hebrewpiper_voice", "female")
       key = f"{host}|{voice}"
       if _hebrewpiper_engine is None or _hebrewpiper_loaded_key != key:
           from agenttalk.hebrewpiper_engine import HebrewPiperEngine
           logging.info("Initialising HebrewPiperEngine host=%s voice=%s", host, voice)
           _hebrewpiper_engine = HebrewPiperEngine(host=host, voice=voice)
           _hebrewpiper_loaded_key = key
       return _hebrewpiper_engine

   elif model == "lightblue":
       global _lightblue_engine, _lightblue_loaded_key
       onnx_dir = STATE.get("lightblue_onnx_dir")
       phonikud_path = STATE.get("lightblue_phonikud_path", "phonikud-1.0.onnx")
       if not onnx_dir:
           raise RuntimeError(
               "Light-BlueTTS onnx_dir not configured. "
               "Clone https://github.com/maxmelichov/Light-BlueTTS, download models, "
               "then POST /config with lightblue_onnx_dir set to absolute path of onnx_models/."
           )
       key = f"{onnx_dir}|{phonikud_path}"
       if _lightblue_engine is None or _lightblue_loaded_key != key:
           from agenttalk.lightblue_engine import LightBlueTTSEngine
           logging.info("Initialising LightBlueTTSEngine from %s", onnx_dir)
           _lightblue_engine = LightBlueTTSEngine(onnx_dir=onnx_dir, phonikud_path=phonikud_path)
           _lightblue_loaded_key = key
       return _lightblue_engine

--- agenttalk/service.py ---

1. Update the ConfigRequest model:
   - Extend model Literal type: Literal["kokoro", "piper", "lightblue", "hebrewpiper"] | None
   - Add new optional fields after piper_model_path:
     hebrewpiper_host: str | None = Field(None,
         description="Base URL for PiperStream Docker service. Default: 'http://localhost:8000'.",
         examples=["http://localhost:8000"])
     hebrewpiper_voice: Literal["male", "female"] | None = Field(None,
         description="PiperStream voice. 'male' or 'female'. Default: 'female'.")
     lightblue_onnx_dir: str | None = Field(None,
         description="Absolute path to Light-BlueTTS onnx_models/ directory.",
         examples=["C:/Users/user/Light-BlueTTS/onnx_models"])
     lightblue_phonikud_path: str | None = Field(None,
         description="Absolute path to phonikud-1.0.onnx. Default: 'phonikud-1.0.onnx' (cwd).",
         examples=["C:/Users/user/Light-BlueTTS/phonikud-1.0.onnx"])
     lightblue_voice_path: str | None = Field(None,
         description="Absolute path to a Light-BlueTTS voices/*.json style file.",
         examples=["C:/Users/user/Light-BlueTTS/voices/female1.json"])

2. Update POST /config handler to apply new fields (same pattern as existing piper_model_path):
   for field in ("hebrewpiper_host", "hebrewpiper_voice", "lightblue_onnx_dir",
                 "lightblue_phonikud_path", "lightblue_voice_path"):
       val = getattr(body, field, None)
       if val is not None:
           STATE[field] = val

3. Update GET /config response to include new fields:
   "hebrewpiper_host":       STATE.get("hebrewpiper_host"),
   "hebrewpiper_voice":      STATE.get("hebrewpiper_voice"),
   "lightblue_onnx_dir":     STATE.get("lightblue_onnx_dir"),
   "lightblue_phonikud_path": STATE.get("lightblue_phonikud_path"),
   "lightblue_voice_path":   STATE.get("lightblue_voice_path"),

4. Add GET /hebrew-voices endpoint (after /piper-voices):
   @app.get("/hebrew-voices", summary="List available Hebrew TTS voices")
   def list_hebrew_voices():
       """Returns available voices for Hebrew TTS engines.
       For model='hebrewpiper': static list ['male', 'female'].
       For model='lightblue': scans lightblue_voice_path's parent dir for *.json files.
       """
       result = {
           "hebrewpiper": ["male", "female"],
           "lightblue": [],
       }
       onnx_dir = STATE.get("lightblue_onnx_dir")
       voice_path = STATE.get("lightblue_voice_path")
       if voice_path:
           voices_dir = Path(voice_path).parent
           if voices_dir.exists():
               result["lightblue"] = [p.stem for p in sorted(voices_dir.glob("*.json"))]
       return JSONResponse(result)

5. Update the startup restoration loop in main() at line 665.
   The existing tuple restores only the original 9 keys. Extend it to also restore the 5 Hebrew keys:

   for _key in (
       "voice", "speed", "volume", "model", "muted",
       "pre_cue_path", "post_cue_path", "piper_model_path", "speech_mode",
       "hebrewpiper_host", "hebrewpiper_voice",
       "lightblue_onnx_dir", "lightblue_phonikud_path", "lightblue_voice_path",
   ):

--- agenttalk/config_loader.py ---

Extend the `persisted` dict inside save_config() to include the 5 new Hebrew config keys.
The current dict ends with "speech_mode". Add these entries after it:

   "hebrewpiper_host":        state.get("hebrewpiper_host", "http://localhost:8000"),
   "hebrewpiper_voice":       state.get("hebrewpiper_voice", "female"),
   "lightblue_onnx_dir":      state.get("lightblue_onnx_dir"),
   "lightblue_phonikud_path": state.get("lightblue_phonikud_path"),
   "lightblue_voice_path":    state.get("lightblue_voice_path"),

Also update the docstring comment from "Persists all 7 settings fields" (or "9 keys") to
"Persists all 14 settings fields" to reflect the expanded set.

--- agenttalk/commands/model.md ---

Update the /agenttalk:model command documentation to list the two new model options AND fix the
binary resolution clause so the command works correctly for all four models.

1. Find and replace the binary resolution clause. The current text says something like:
     "resolve it to kokoro or piper"
   Replace it with:
     "resolve it to one of: kokoro, piper, lightblue, hebrewpiper"

2. Update the pick list from 2 options to 4 options — ensure all four appear:
   - kokoro
   - piper
   - lightblue
   - hebrewpiper

3. Append to the existing model list:
  - `lightblue` — Hebrew TTS via Light-BlueTTS (local, requires onnx_models setup)
  - `hebrewpiper` — Hebrew TTS via PiperStream Docker service (requires `docker compose up`)

4. Add examples:
  # Switch to Hebrew (PiperStream — easier setup):
  /agenttalk:model hebrewpiper

  # Switch to Hebrew (Light-BlueTTS — better quality, local):
  /agenttalk:model lightblue
  </action>
  <verify>
    <automated>cd /d/docker/claudetalk && python -c "
from agenttalk.tts_worker import STATE
assert 'hebrewpiper_host' in STATE, 'missing hebrewpiper_host'
assert 'lightblue_onnx_dir' in STATE, 'missing lightblue_onnx_dir'
assert 'lightblue_voice_path' in STATE, 'missing lightblue_voice_path'
print('STATE keys OK:', list(k for k in STATE if 'hebrew' in k or 'lightblue' in k))
" && python -c "
import inspect, agenttalk.tts_worker as tw
src = inspect.getsource(tw._get_active_engine)
assert 'hebrewpiper' in src, 'missing hebrewpiper dispatch'
assert 'lightblue' in src, 'missing lightblue dispatch'
print('_get_active_engine dispatch OK')
" && python -c "
import inspect, agenttalk.config_loader as cl
src = inspect.getsource(cl.save_config)
assert 'hebrewpiper_host' in src, 'save_config missing hebrewpiper_host'
assert 'lightblue_onnx_dir' in src, 'save_config missing lightblue_onnx_dir'
print('save_config persistence OK')
" && python -c "
import inspect, agenttalk.service as svc
src = inspect.getsource(svc)
assert 'hebrewpiper_host' in src and 'hebrewpiper_voice' in src, 'service missing hebrew keys'
assert 'lightblue' in src and 'hebrewpiper' in src
assert 'hebrew-voices' in src
print('service.py OK')
" && python -c "
content = open('agenttalk/commands/model.md').read()
assert 'lightblue' in content, 'model.md missing lightblue'
assert 'hebrewpiper' in content, 'model.md missing hebrewpiper'
assert 'kokoro, piper, lightblue, hebrewpiper' in content or 'lightblue.*hebrewpiper' in content, 'resolution clause not updated'
print('model.md OK')
"</automated>
  </verify>
  <done>
    tts_worker.STATE has all 5 new keys with defaults. _get_active_engine() routes
    'hebrewpiper' and 'lightblue' to their respective engine classes. ConfigRequest accepts
    all new fields. GET /config and GET /hebrew-voices return Hebrew engine state.
    save_config() persists all 5 Hebrew keys so selection survives restart. The service.py
    startup loop restores all 5 Hebrew keys from config.json on boot.
    /agenttalk:model command docs list all four models with the corrected resolution clause.
  </done>
</task>

<task type="auto">
  <name>Task 3: Write Hebrew TTS setup guide</name>
  <files>
    docs/hebrew-tts-setup.md
  </files>
  <action>
Create docs/hebrew-tts-setup.md — a practical setup guide comparing both options.

Structure:
1. Overview section: Two approaches — PiperStream (Docker, simpler) vs Light-BlueTTS (local, heavier)
   Include comparison table: setup effort, quality, GPU support, network required, voices.

2. Option A — HebrewPiper (PiperStream):
   Prerequisites: Docker Desktop installed
   Steps:
     a. git clone https://github.com/maxmelichov/PiperStream
     b. Download onnx.zip from the repo releases/instructions and place in project root
     c. docker compose up --build -d (first build ~3 min)
     d. curl http://localhost:8000/health  (verify)
     e. Switch AgentTalk: curl -X POST http://localhost:5050/config \
          -H "Content-Type: application/json" \
          -d '{"model": "hebrewpiper", "hebrewpiper_voice": "female"}'
     f. Test: curl -X POST http://localhost:5050/speak \
          -H "Content-Type: application/json" \
          -d '{"text": "שלום עולם, זה מבחן"}'
   Voice options: male, female (via hebrewpiper_voice config key)

3. Option B — Light-BlueTTS:
   Prerequisites: Python 3.10+, ~3GB disk (torch + models)
   Steps:
     a. git clone https://github.com/maxmelichov/Light-BlueTTS /path/to/Light-BlueTTS
     b. pip install onnxruntime phonikud phonikud-onnx soundfile torch torchaudio
        (or follow repo's `uv sync` instructions)
     c. Download model files — follow repo README to get onnx_models/ directory
        (includes backbone.onnx, text_encoder.onnx, vocoder.onnx, and 6 others)
     d. Download phonikud-1.0.onnx (listed in repo requirements)
     e. Add Light-BlueTTS to Python path:
        set PYTHONPATH=C:\path\to\Light-BlueTTS  (Windows)
        export PYTHONPATH=/path/to/Light-BlueTTS  (macOS/Linux)
     f. Configure AgentTalk:
        curl -X POST http://localhost:5050/config \
          -H "Content-Type: application/json" \
          -d '{
            "model": "lightblue",
            "lightblue_onnx_dir": "C:/path/to/Light-BlueTTS/onnx_models",
            "lightblue_phonikud_path": "C:/path/to/Light-BlueTTS/phonikud-1.0.onnx",
            "lightblue_voice_path": "C:/path/to/Light-BlueTTS/voices/female1.json"
          }'
     g. Test: curl -X POST http://localhost:5050/speak \
          -H "Content-Type: application/json" \
          -d '{"text": "שלום עולם, זה מבחן"}'
   Voice options: List voices via GET http://localhost:5050/hebrew-voices

4. Switching back to English:
   curl -X POST http://localhost:5050/config -H "Content-Type: application/json" -d '{"model": "kokoro"}'

5. Troubleshooting section:
   - PiperStream ConnectionError: check Docker is running, port 8000 not occupied
   - Light-BlueTTS ImportError: PYTHONPATH not set or deps not installed
   - Light-BlueTTS RuntimeError about onnx_dir: lightblue_onnx_dir not set in config
   - Garbled Hebrew audio: text may need to be UTF-8 encoded; check terminal encoding

Write clean markdown. No emojis. Headers use ##/###. Code blocks use bash/json fences.
  </action>
  <verify>
    <automated>cd /d/docker/claudetalk && test -f docs/hebrew-tts-setup.md && python -c "
content = open('docs/hebrew-tts-setup.md').read()
assert 'hebrewpiper' in content
assert 'lightblue' in content
assert 'docker compose' in content
assert 'lightblue_onnx_dir' in content
print('Setup guide OK, length:', len(content), 'chars')
"</automated>
  </verify>
  <done>
    docs/hebrew-tts-setup.md exists with both setup paths documented, including
    exact curl commands to configure and test each engine.
  </done>
</task>

</tasks>

<verification>
After all tasks complete, run end-to-end import check:

  python -c "
  from agenttalk.tts_worker import STATE, _get_active_engine
  from agenttalk.hebrewpiper_engine import HebrewPiperEngine
  import agenttalk.lightblue_engine  # verify importable without torch
  assert STATE['hebrewpiper_host'] == 'http://localhost:8000'
  assert STATE['hebrewpiper_voice'] == 'female'
  print('All imports OK')
  "

Verify service.py Literal type includes new models:
  python -c "
  import inspect, agenttalk.service as svc
  src = inspect.getsource(svc)
  assert 'lightblue' in src and 'hebrewpiper' in src
  assert 'hebrew-voices' in src
  print('service.py OK')
  "

Verify config_loader persists Hebrew keys:
  python -c "
  import inspect, agenttalk.config_loader as cl
  src = inspect.getsource(cl.save_config)
  assert 'hebrewpiper_host' in src and 'lightblue_onnx_dir' in src
  print('config_loader.py persistence OK')
  "
</verification>

<success_criteria>
1. `python -c "from agenttalk.hebrewpiper_engine import HebrewPiperEngine"` succeeds (no Docker needed for import)
2. `python -c "import agenttalk.lightblue_engine"` succeeds (no torch needed for import — deferred)
3. `python -c "from agenttalk.tts_worker import STATE; assert 'hebrewpiper_host' in STATE"` passes
4. GET http://localhost:5050/config shows new Hebrew config keys when service is running
5. GET http://localhost:5050/hebrew-voices returns `{"hebrewpiper": ["male", "female"], "lightblue": [...]}`
6. docs/hebrew-tts-setup.md exists with step-by-step instructions for both Hebrew TTS options
7. Existing English TTS (kokoro, piper) behavior is unchanged
8. Hebrew model selection (hebrewpiper_host, hebrewpiper_voice, lightblue_onnx_dir, lightblue_phonikud_path, lightblue_voice_path) persists in config.json and is restored after service restart
9. /agenttalk:model command correctly resolves lightblue and hebrewpiper (resolution clause updated)
</success_criteria>

<output>
After completion, create `.planning/quick/8-i-ve-found-two-interesting-enhancements-/8-SUMMARY.md`
with: engines added, config keys, API changes, files modified, and link to docs/hebrew-tts-setup.md.
</output>

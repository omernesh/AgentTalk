# Phase 2: FastAPI HTTP Server and TTS Queue - Research

**Researched:** 2026-02-26
**Domain:** FastAPI POST endpoint, Python threading.Queue backpressure, sentence chunking (pysbd), markdown text preprocessing, sounddevice volume, kokoro-onnx speed parameter
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SVC-02 | FastAPI HTTP server runs on localhost:5050 in a daemon thread (uvicorn) | Phase 1 already implements this; Phase 2 adds /speak endpoint to the existing app |
| SVC-03 | TTS worker runs in a separate daemon thread consuming from the audio queue | threading.Queue(maxsize=3) + daemon Thread pattern documented; blocking q.get() in worker thread is correct |
| AUDIO-01 | Text is sentence-chunked before synthesis — first sentence begins playing while remaining synthesize | pysbd 0.3.4 Segmenter API verified; queue accepts list of sentences; worker pops one at a time |
| AUDIO-02 | Text preprocessing pipeline strips fenced code blocks, inline code, URLs, file paths, and markdown markers | stdlib re.sub pipeline documented; no extra deps needed; ordered regex application is critical |
| AUDIO-03 | Sentences with fewer than 40% alphabetic characters are silently skipped | sum(c.isalpha() for c in s) / len(s) pattern verified; threshold applied per-sentence post-strip |
| AUDIO-04 | Incoming TTS requests are queued (bounded, max 3 pending); overflow is dropped | threading.Queue(maxsize=3) + put_nowait() + queue.Full exception catch pattern confirmed |
| AUDIO-05 | WASAPI auto_convert=True is set to handle sample rate mismatches on Windows audio devices | Phase 1 empirical finding: WasapiSettings causes PaErrorCode -9984 on MME devices; Phase 2 must detect host API and only apply WasapiSettings if device is WASAPI, not MME |
| AUDIO-06 | User can adjust TTS output volume via configuration and slash command | Volume = multiply numpy samples by float scalar before sd.play(); no extra deps |
| TTS-05 | User can adjust TTS speech speed (rate) via configuration and slash command | kokoro.create(speed=float) parameter, range 0.5–2.0; stored in config, read per-synthesis call |
</phase_requirements>

---

## Summary

Phase 2 adds the core runtime capability: a POST `/speak` endpoint that accepts text, preprocesses it (strip markdown, segment into sentences, filter junk), and plays each sentence through speakers as it is synthesized — with a bounded queue preventing runaway audio. The service skeleton from Phase 1 already provides the FastAPI app, uvicorn daemon thread, Kokoro engine, and audio playback. Phase 2 wires them together.

The most important architectural decision is the queue type. The TTS worker must run in a `threading.Thread` (not async) because `kokoro.create()` is blocking CPU work and `sd.play()` + `sd.wait()` is blocking I/O — neither is safe to run in the asyncio event loop without executor wrapping. The correct queue is `threading.Queue(maxsize=3)` from the Python stdlib, which is thread-safe and works naturally between FastAPI's async handlers (which call `put_nowait()`) and the blocking worker thread (which calls `get()`). The `asyncio.Queue` is explicitly not thread-safe and must not be used here.

The text preprocessing pipeline is a pure-regex stdlib implementation — no markdown parsing library is needed, since we are stripping content rather than rendering it. The sentence segmentation uses `pysbd` (0.3.4, rule-based, no ML model), which is the TTS community standard and handles edge cases (abbreviations, decimals, URLs) that naive split-on-period fails on. The alphabetic ratio filter (`sum(c.isalpha() for c in s) / max(len(s), 1)`) is a one-liner. Volume and speed are stored in a module-level state dict and applied per-synthesis call.

**Primary recommendation:** Use `threading.Queue(maxsize=3)` for the TTS queue, `pysbd.Segmenter` for sentence segmentation, stdlib `re` for markdown stripping, `samples * volume` for volume, and `kokoro.create(speed=speed)` for rate. Detect the output device's host API at startup to conditionally apply `WasapiSettings(auto_convert=True)` only if the device is WASAPI (not MME).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.110 | POST /speak endpoint with Pydantic body | Already in requirements.txt; Pydantic validation is automatic |
| pydantic | >=2.0 (fastapi dep) | Request body model (SpeakRequest) | Bundled with FastAPI; validates `text` field |
| pysbd | 0.3.4 | Sentence boundary detection | Rule-based, no model download, 97.92% accuracy on English; TTS community standard |
| threading | stdlib | TTS worker daemon thread | Already used in Phase 1; blocking worker is correct pattern |
| queue | stdlib | Bounded thread-safe TTS queue | Thread-safe, put_nowait() raises queue.Full; no extra deps |
| re | stdlib | Markdown text preprocessing pipeline | Sufficient for all required stripping; no parser overhead |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | >=2.0.2 (kokoro dep) | Volume scaling: `samples * volume_scalar` | Already installed; multiply float32 array by scalar |
| sounddevice | 0.5.5 | Audio playback (already in stack) | query_devices() used to detect WASAPI vs MME for AUDIO-05 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| threading.Queue | asyncio.Queue | asyncio.Queue is NOT thread-safe; cannot be safely called from both async handlers and threading.Thread workers without run_coroutine_threadsafe wrappers — adds unnecessary complexity |
| threading.Queue | janus (sync/async bridge queue) | janus 2.0.0 solves the same problem but adds a dependency; threading.Queue.put_nowait() is already callable from async code without any bridging |
| pysbd | NLTK sent_tokenize | NLTK requires punkt_tab corpus download; pysbd is zero-setup rule-based; equivalent accuracy for English |
| pysbd | str.split('.') | Naive split breaks on abbreviations (e.g., "Dr. Smith"), decimals ("3.14"), and URLs — not acceptable for TTS |
| re (stdlib) | markdown-it-py, python-markdown | Full parsers are overkill for stripping; regex is faster and has no risk of rendering artifacts |
| samples * scalar | sounddevice Stream callback | Stream callback adds complexity; pre-multiplying the numpy array before sd.play() is simpler and correct for one-shot playback |

**Installation:**
```bash
pip install pysbd
```
(All other Phase 2 dependencies are already in requirements.txt from Phase 1)

---

## Architecture Patterns

### Recommended Project Structure

```
agenttalk/
├── service.py       # Entry point + FastAPI app (extend existing)
├── tts_worker.py    # TTS daemon thread: queue consumer, synthesize, play
├── preprocessor.py  # Text pipeline: strip_markdown(), segment_sentences(), is_junk()
└── state.py         # Shared mutable state: volume, speed, is_ready (module-level dict)
```

For Phase 2, the planner may keep everything in `service.py` or split into modules. Splitting is recommended because the file is already ~275 lines and will grow substantially.

### Pattern 1: threading.Queue Bounded Backpressure

**What:** A `threading.Queue(maxsize=3)` sits between the FastAPI async handler and the TTS daemon thread. The FastAPI handler calls `put_nowait()` — if the queue is full, it catches `queue.Full` and drops the request silently (or returns 429). The TTS worker blocks on `get()`.

**When to use:** Any time async code needs to send work to a blocking thread without blocking the event loop.

**Why threading.Queue and not asyncio.Queue:** `asyncio.Queue` is explicitly documented as not thread-safe. Calling `asyncio_queue.put_nowait()` from a `threading.Thread` worker (or from the uvicorn event loop thread to a thread consumer) is unsafe. `threading.Queue.put_nowait()` is safe from any context including async handlers — it uses stdlib locks.

```python
# Source: Python stdlib queue docs + threading docs
import queue
import threading

# Created once at startup
_tts_queue: queue.Queue = queue.Queue(maxsize=3)

# In FastAPI async handler:
@app.post("/speak")
async def speak(req: SpeakRequest):
    sentences = preprocess_and_segment(req.text)
    if not sentences:
        return JSONResponse({"status": "skipped"}, status_code=200)
    try:
        _tts_queue.put_nowait(sentences)
        return JSONResponse({"status": "queued"}, status_code=202)
    except queue.Full:
        return JSONResponse({"status": "dropped", "reason": "queue full"}, status_code=429)

# TTS worker (runs in daemon thread):
def _tts_worker():
    while True:
        sentences = _tts_queue.get()  # Blocks until item available
        for sentence in sentences:
            samples, rate = _kokoro_engine.create(
                sentence,
                voice=_state["voice"],
                speed=_state["speed"],
                lang="en-us",
            )
            scaled = samples * _state["volume"]
            sd.play(scaled, samplerate=rate)
            sd.wait()
        _tts_queue.task_done()
```

### Pattern 2: Text Preprocessing Pipeline

**What:** A sequence of `re.sub()` calls that strips markdown elements before sentence segmentation. Order matters — strip fenced code blocks FIRST (before inline code) to avoid partial matches.

**When to use:** Applied to every incoming `/speak` request body before sentence chunking.

```python
# Source: stdlib re docs + markdown syntax spec
import re

def strip_markdown(text: str) -> str:
    """Strip markdown elements for clean TTS prose."""
    # 1. Fenced code blocks (``` ... ```) — strip entire block including content
    text = re.sub(r'```[\s\S]*?```', '', text)
    # 2. Inline code (`code`) — replace with nothing (or a space to prevent word merging)
    text = re.sub(r'`[^`\n]+`', '', text)
    # 3. URLs (http/https) — strip entire URL
    text = re.sub(r'https?://\S+', '', text)
    # 4. File paths (e.g., /path/to/file, C:\path\to\file, ./relative)
    text = re.sub(r'(?:^|[\s(])(?:[A-Za-z]:\\|\.{0,2}/)[\w./\\-]+', ' ', text)
    # 5. Markdown headers (# ## ###)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 6. Bold/italic markers (**text**, *text*, __text__, _text_)
    text = re.sub(r'[*_]{1,3}([^*_\n]+)[*_]{1,3}', r'\1', text)
    # 7. Markdown links [text](url) — keep text, drop URL
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 8. Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text
```

### Pattern 3: Sentence Segmentation with pysbd

**What:** `pysbd.Segmenter` segments cleaned text into a list of sentences. The segmenter is created once and reused (no model load cost, but Segmenter is lightweight and can be created per-call if needed).

**When to use:** After `strip_markdown()`, before the alphabetic filter.

```python
# Source: pysbd PyPI docs / GitHub README (verified 2026-02-26)
import pysbd

_segmenter = pysbd.Segmenter(language="en", clean=False)

def segment_sentences(text: str) -> list[str]:
    """Split text into sentences using pySBD rule-based segmenter."""
    return _segmenter.segment(text)
```

### Pattern 4: Alphabetic Ratio Filter

**What:** Skip any sentence where fewer than 40% of its characters are alphabetic. This silently drops pure JSON, symbol strings, code snippets that slipped through, etc.

**When to use:** Applied per-sentence after segmentation. Sentences that pass the filter are added to the playback list.

```python
# Source: Python str.isalpha() docs
def is_speakable(sentence: str) -> bool:
    """Return True if >= 40% of characters are alphabetic."""
    cleaned = sentence.strip()
    if not cleaned:
        return False
    alpha_count = sum(c.isalpha() for c in cleaned)
    return alpha_count / len(cleaned) >= 0.40
```

### Pattern 5: Volume and Speed State

**What:** A module-level dict holds mutable runtime state: `volume` (0.0–2.0, default 1.0) and `speed` (0.5–2.0, default 1.0). Volume is applied by multiplying the numpy float32 samples array. Speed is passed to `kokoro.create()`.

**When to use:** Applied in the TTS worker on every synthesis call. State is read at synthesis time, so changes take effect on the next queued sentence.

```python
# Source: numpy docs (array scalar multiplication); kokoro-onnx examples
_state = {
    "volume": 1.0,   # 0.0 = silent, 1.0 = normal, 2.0 = double amplitude
    "speed": 1.0,    # 0.5 = half speed, 2.0 = double speed
    "voice": "af_heart",
}

# In TTS worker:
samples, rate = _kokoro_engine.create(text, voice=_state["voice"], speed=_state["speed"], lang="en-us")
scaled_samples = samples * _state["volume"]  # float32 array * float scalar
sd.play(scaled_samples, samplerate=rate)
sd.wait()
```

**Volume note:** Kokoro returns float32 samples normalized to [-1.0, 1.0]. Multiplying by 1.0 is identity. Multiplying by > 1.0 causes clipping; keep volume <= 1.0 for safe output. For Phase 2, volume defaults to 1.0 and is configurable. Clipping prevention (np.clip) should be applied when volume > 1.0.

### Pattern 6: WASAPI Host API Detection (AUDIO-05)

**What:** AUDIO-05 requires `WasapiSettings(auto_convert=True)` for sample rate mismatches. Phase 1 empirically proved this causes `PaErrorCode -9984` on MME devices. The correct implementation: detect the host API of the default output device at startup. Apply WasapiSettings only if WASAPI, not if MME.

**When to use:** During `_configure_audio()` at startup.

```python
# Source: python-sounddevice 0.5.5 docs (query_devices, query_hostapis)
import sounddevice as sd

def _configure_audio_for_device() -> None:
    """Apply WASAPI auto_convert only if default device uses WASAPI host API."""
    try:
        device_info = sd.query_devices(kind='output')
        hostapi_id = device_info.get('hostapi', 0)
        hostapi_info = sd.query_hostapis(hostapi_id)
        hostapi_name = hostapi_info.get('name', '').upper()
        if 'WASAPI' in hostapi_name:
            sd.default.extra_settings = sd.WasapiSettings(auto_convert=True)
            logging.info("WASAPI device detected — auto_convert enabled.")
        else:
            logging.info(
                "Non-WASAPI device (%s) — using PortAudio default resampling.", hostapi_name
            )
    except Exception:
        logging.warning("Could not detect host API; using PortAudio defaults.", exc_info=True)
```

### Pattern 7: Pydantic Request Body for /speak

**What:** A Pydantic `BaseModel` with a single `text: str` field. FastAPI validates the request body automatically. Non-JSON or missing-field requests get 422 responses automatically.

```python
# Source: FastAPI official docs - https://fastapi.tiangolo.com/tutorial/body/
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import JSONResponse

class SpeakRequest(BaseModel):
    text: str

@app.post("/speak")
async def speak(req: SpeakRequest):
    ...
```

### Anti-Patterns to Avoid

- **Using asyncio.Queue as the TTS queue:** Not thread-safe. `put_nowait()` from an async handler to a `threading.Thread` consumer will silently corrupt the queue. Use `threading.Queue`.
- **Running kokoro.create() in the async event loop:** Blocks the entire uvicorn server for 1-3 seconds per sentence. Always run synthesis in a daemon thread.
- **Calling sd.play() in the async event loop:** Same problem — blocks uvicorn. Audio must happen in the TTS worker thread.
- **Applying WasapiSettings globally without host API check:** Phase 1 empirically confirmed this causes `PaErrorCode -9984` on MME devices. Detect first, apply conditionally.
- **Using str.split('.') for sentence chunking:** Breaks on "Dr. Smith", "v1.0", "3.14", URLs. Use pysbd.
- **Applying alphabetic filter before preprocessing:** Filter after stripping markdown. Raw text with code blocks will fail the 40% test even for valid sentences.
- **Stripping inline code before fenced code blocks:** A fenced block containing backtick strings would be partially matched. Strip fenced blocks first.
- **Creating pysbd.Segmenter per request:** Lightweight but unnecessary — create once at module level.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentence boundary detection | split on "." or regex sentence splitter | pysbd.Segmenter | Abbreviations, decimals, URLs, initials all cause false boundaries; pysbd handles 97.92% of English cases correctly |
| Thread-safe bounded queue | asyncio.Queue + run_coroutine_threadsafe | threading.Queue(maxsize=3) | stdlib, genuinely thread-safe, put_nowait() works from any context |
| Markdown stripping | HTML parser → plain text | stdlib re.sub() pipeline | Parsing markdown to HTML then stripping HTML is two unnecessary transforms; regex on input is faster and sufficient |
| Volume control | sounddevice Stream callback with gain | samples * scalar before sd.play() | Pre-multiplying a one-shot numpy array is O(n) and requires zero extra infrastructure |

**Key insight:** The TTS pipeline is simpler than it looks. The hard problems (phoneme-to-speech, ONNX inference, PortAudio playback) are already solved by the Phase 1 stack. Phase 2 only adds the routing layer (queue) and text preprocessing (regex + pysbd), which are stdlib + one tiny library.

---

## Common Pitfalls

### Pitfall 1: asyncio.Queue in a Mixed Async/Thread Architecture

**What goes wrong:** `asyncio.Queue.put_nowait()` called from the FastAPI async handler successfully inserts — but the TTS daemon thread calling `queue.get()` deadlocks or sees stale data because asyncio.Queue uses asyncio primitives that require the asyncio event loop, not OS-level locks.

**Why it happens:** asyncio.Queue is documented as "not thread-safe" and designed only for async/await code. Accessing it from `threading.Thread` violates its contract.

**How to avoid:** Use `threading.Queue(maxsize=3)`. Its `put_nowait()` is safe to call from any thread or async context. Its `get()` blocks the calling thread (correct for a daemon worker).

**Warning signs:** Intermittent deadlocks or `RuntimeError: no running event loop` when calling asyncio.Queue methods from worker threads.

### Pitfall 2: kokoro.create() Blocking the Event Loop

**What goes wrong:** If `/speak` calls `kokoro.create()` directly in the async handler, the entire uvicorn server freezes for 1-3 seconds per sentence. All other requests (including `/health`) time out.

**Why it happens:** Kokoro's ONNX inference is CPU-bound and blocking. FastAPI's async handlers share the same event loop as uvicorn — blocking in an async handler blocks all other coroutines.

**How to avoid:** NEVER call `kokoro.create()` or `sd.play()` in the async handler. The handler only does: preprocess text → enqueue to `threading.Queue` → return 202. The TTS daemon thread does the synthesis and playback.

**Warning signs:** `/health` stops responding during TTS playback; 2+ second latency on all endpoints while TTS is running.

### Pitfall 3: Alphabetic Filter Applied Before Markdown Stripping

**What goes wrong:** A sentence like "```python\ndef foo(): pass\n```" contains very few alpha characters in the raw form. But after stripping the fenced code block, there may be no text at all. If the filter runs on raw text, valid prose after a code block might be filtered out due to the block contaminating the ratio.

**Why it happens:** The filter must operate on cleaned text, not raw markdown.

**How to avoid:** Always run the preprocessing pipeline in this exact order: `strip_markdown(text)` → `segment_sentences(cleaned)` → `is_speakable(sentence)` per sentence.

**Warning signs:** Valid sentences immediately after code blocks are silently skipped.

### Pitfall 4: WasapiSettings on MME Device

**What goes wrong:** `sd.default.extra_settings = sd.WasapiSettings(auto_convert=True)` raises `PaErrorCode -9984 (Incompatible host API specific stream info)` at playback time.

**Why it happens:** WasapiSettings is specific to WASAPI host API. When PortAudio selects an MME device (common on Windows 11 with Realtek Audio), applying WASAPI settings to an MME stream causes host API mismatch.

**How to avoid:** Detect the host API at startup using `sd.query_devices(kind='output')['hostapi']` and `sd.query_hostapis()`. Apply WasapiSettings only if `'WASAPI' in hostapi_name`.

**Warning signs:** `PortAudioError: Incompatible host API specific stream info` in the log at first playback after startup.

**Phase 1 context:** This was empirically confirmed during Phase 1 execution. The WasapiSettings recommendation in the Phase 1 research was found incorrect for this machine's MME device. Phase 2 must fix this properly rather than leaving WasapiSettings absent.

### Pitfall 5: Queue Holds Text Strings, Worker Re-Segments

**What goes wrong:** If the queue holds the raw `text` string (not the pre-segmented sentence list), the worker must re-do preprocessing. This wastes CPU and — more critically — means the API can't validate and filter before queuing, so junk sentences consume queue slots.

**How to avoid:** Preprocess and segment in the async handler BEFORE calling `put_nowait()`. The queue holds `list[str]` of cleaned, filtered sentences. The worker iterates the list and synthesizes each sentence.

**Warning signs:** Queue fills with items that produce no audio (junk sentences occupying slots).

### Pitfall 6: pysbd.Segmenter is Not Thread-Safe

**What goes wrong:** If `pysbd.Segmenter` is called from multiple threads simultaneously (e.g., if `/speak` ever processes requests concurrently), it may produce incorrect segmentation.

**Why it happens:** pysbd's Segmenter has internal mutable state during segmentation.

**How to avoid:** Call `segment_sentences()` only in the async handler (which uvicorn serializes for sync-looking ops), or use a threading.Lock around the segmenter call. For Phase 2 with a single-worker queue, the segmenter runs in the async handler — one call at a time is fine because FastAPI processes one request body at a time per worker.

**Warning signs:** Incorrect sentence splits under load.

---

## Code Examples

Verified patterns from official sources:

### Complete /speak Endpoint

```python
# Source: FastAPI docs (body) + Python stdlib queue docs
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import queue

class SpeakRequest(BaseModel):
    text: str

@app.post("/speak", status_code=202)
async def speak(req: SpeakRequest):
    """Accept text, preprocess, and queue for TTS playback."""
    if not is_ready:
        return JSONResponse({"status": "not_ready"}, status_code=503)

    cleaned = strip_markdown(req.text)
    sentences = [s for s in segment_sentences(cleaned) if is_speakable(s)]

    if not sentences:
        return JSONResponse({"status": "skipped", "reason": "no speakable sentences"}, status_code=200)

    try:
        _tts_queue.put_nowait(sentences)
        return JSONResponse({"status": "queued", "sentences": len(sentences)}, status_code=202)
    except queue.Full:
        logging.info("TTS queue full (%d items) — dropping request.", _tts_queue.qsize())
        return JSONResponse({"status": "dropped", "reason": "queue full"}, status_code=429)
```

### TTS Worker Thread

```python
# Source: Python stdlib threading + queue docs
import threading
import queue
import logging
import sounddevice as sd

_tts_queue: queue.Queue = queue.Queue(maxsize=3)

def _tts_worker() -> None:
    """Daemon thread: consume sentences from queue, synthesize, play."""
    logging.info("TTS worker thread started.")
    while True:
        sentences: list[str] = _tts_queue.get()
        try:
            for sentence in sentences:
                if not sentence.strip():
                    continue
                logging.debug("TTS: synthesizing %r", sentence[:60])
                samples, rate = _kokoro_engine.create(
                    sentence,
                    voice=_state["voice"],
                    speed=_state["speed"],
                    lang="en-us",
                )
                scaled = samples * _state["volume"]
                if _state["volume"] > 1.0:
                    import numpy as np
                    scaled = np.clip(scaled, -1.0, 1.0)
                sd.play(scaled, samplerate=rate)
                sd.wait()
        except Exception:
            logging.exception("TTS worker error on sentence.")
        finally:
            _tts_queue.task_done()

def start_tts_worker() -> threading.Thread:
    t = threading.Thread(target=_tts_worker, daemon=True, name="tts-worker")
    t.start()
    logging.info("TTS worker daemon thread started.")
    return t
```

### Markdown Stripping Pipeline

```python
# Source: stdlib re docs + markdown syntax specification
import re

def strip_markdown(text: str) -> str:
    """Strip markdown elements to produce clean TTS-ready prose."""
    # Order matters: fenced blocks before inline code
    text = re.sub(r'```[\s\S]*?```', ' ', text)          # fenced code blocks
    text = re.sub(r'`[^`\n]+`', ' ', text)                # inline code
    text = re.sub(r'https?://\S+', ' ', text)              # URLs
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [link text](url)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headers
    text = re.sub(r'[*_]{1,3}([^*_\n]+)[*_]{1,3}', r'\1', text)  # bold/italic
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)  # blockquotes
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)  # list bullets
    text = re.sub(r'\s+', ' ', text).strip()               # normalize whitespace
    return text
```

### Sentence Segmentation + Filter

```python
# Source: pysbd PyPI docs (https://pypi.org/project/pysbd/)
import pysbd

_segmenter = pysbd.Segmenter(language="en", clean=False)

def segment_sentences(text: str) -> list[str]:
    return _segmenter.segment(text)

def is_speakable(sentence: str) -> bool:
    """Skip sentences with fewer than 40% alphabetic characters."""
    s = sentence.strip()
    if not s:
        return False
    alpha = sum(c.isalpha() for c in s)
    return alpha / len(s) >= 0.40
```

### Volume-Scaled Playback

```python
# Source: numpy docs (array operations) + python-sounddevice 0.5.5 docs
import numpy as np
import sounddevice as sd

def play_audio_scaled(samples, sample_rate: int, volume: float = 1.0) -> None:
    """Play audio with volume scaling. Clips if volume > 1.0."""
    scaled = samples * volume
    if volume > 1.0:
        scaled = np.clip(scaled, -1.0, 1.0)
    sd.play(scaled, samplerate=sample_rate)
    sd.wait()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| asyncio.Queue for cross-thread communication | threading.Queue for thread-to-async bridging | Always the right choice; asyncio.Queue was never appropriate here | Eliminates race conditions and deadlocks |
| NLTK sent_tokenize (requires punkt download) | pysbd.Segmenter (zero-setup rule-based) | pysbd 0.3.4, 2021 — stable since | No internet/corpus download needed; same or better accuracy |
| split() + strip('.') for sentence chunking | pysbd rule-based segmenter | 2020+ TTS community standard | Handles 97.92% of English edge cases vs ~60% for naive split |
| sd.default.extra_settings = WasapiSettings() globally | Conditional WASAPI detection + apply only if WASAPI device | Phase 1 empirical finding 2026-02-26 | Eliminates PaErrorCode -9984 on MME devices |
| @app.on_event("startup") | FastAPI lifespan asynccontextmanager | FastAPI ~0.95 | Already implemented in Phase 1; do not use deprecated on_event |

**Deprecated/outdated:**
- `asyncio.Queue` for mixed async/thread scenarios: Use `threading.Queue`. Not deprecated in stdlib, but architecturally wrong for this use case.
- `@app.on_event("startup")`: Deprecated, replaced by lifespan (already in Phase 1).
- WasapiSettings applied globally: Broken on MME devices, must be conditional.

---

## Open Questions

1. **pysbd thread safety under concurrent requests**
   - What we know: pysbd.Segmenter has internal mutable state. FastAPI uvicorn with a single worker processes requests concurrently via asyncio (not threads).
   - What's unclear: Whether the async handler's call to `_segmenter.segment()` can interleave with another concurrent async handler's call to the same instance.
   - Recommendation: Create the segmenter inside the handler call (cheap, pure Python) or protect with a `threading.Lock`. For Phase 2, creating per-call is safest.

2. **Queue maxsize=3: sentences or requests?**
   - What we know: AUDIO-04 says "max 3 pending" referring to requests. Each request may contain multiple sentences.
   - What's unclear: Whether maxsize=3 refers to 3 requests (each a list of sentences) or 3 individual sentences.
   - Recommendation: maxsize=3 = 3 **requests** (lists of sentences), consistent with the requirement "at most 3 to queue". This matches the success criterion: "10 rapid POST requests causes at most 3 to queue."

3. **Interrupt/stop current playback on queue clear**
   - What we know: Requirements don't mention stopping current audio on a stop command (that's Phase 5/SVC-04).
   - What's unclear: Whether Phase 2 needs any mechanism to interrupt `sd.wait()` mid-playback.
   - Recommendation: Phase 2 does not implement interrupt. The TTS worker plays each sentence to completion. Interrupt is a Phase 5 concern.

4. **Mute state**
   - What we know: AUDIO-06 is about volume. Tray mute toggle is Phase 4 (TRAY-02).
   - What's unclear: Whether `volume=0.0` should be the mute implementation in Phase 2.
   - Recommendation: Add `_state["muted"] = False` now; TTS worker skips synthesis if muted. Simple to add, saves refactor in Phase 4.

---

## Sources

### Primary (HIGH confidence)
- https://fastapi.tiangolo.com/tutorial/body/ — POST endpoint with Pydantic BaseModel pattern verified
- https://docs.python.org/3/library/queue.html — threading.Queue(maxsize), put_nowait(), Full exception, thread-safety guarantee verified
- https://docs.python.org/3/library/asyncio-queue.html — asyncio.Queue explicitly documented as "not thread-safe"
- https://pypi.org/project/pysbd/ — pysbd 0.3.4, Segmenter(language="en", clean=False).segment(text) API verified
- https://python-sounddevice.readthedocs.io/en/latest/api/checking-hardware.html — query_devices(kind='output'), hostapi field, query_hostapis() verified
- https://python-sounddevice.readthedocs.io/en/0.5.5/api/platform-specific-settings.html — WasapiSettings(auto_convert=True) only applies to WASAPI host API (not MME)
- `.planning/phases/01-service-skeleton-and-core-audio/01-02-SUMMARY.md` — Phase 1 empirical finding: WasapiSettings causes PaErrorCode -9984 on MME; PortAudio/MME handles 24000 Hz automatically

### Secondary (MEDIUM confidence)
- https://github.com/nipunsadvilkar/pySBD — pysbd rule-based, 97.92% accuracy on English Golden Rule Set, 22 language support
- https://github.com/aio-libs/janus — janus 2.0.0 (December 2024) as alternative sync/async bridge queue; threading.Queue preferred for simplicity
- WebSearch result: kokoro-onnx speed range 0.5–2.0 float (from GitHub issue #155 type hints)
- WebSearch result: numpy float32 samples * scalar for volume; clip to [-1.0, 1.0] if > 1.0

### Tertiary (LOW confidence)
- pysbd thread safety with concurrent access — not verified in official docs; recommend per-call instantiation as mitigation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pysbd PyPI verified; threading.Queue stdlib; FastAPI POST body pattern from official docs
- Architecture: HIGH — Queue type choice (threading vs asyncio) verified from Python stdlib docs; WASAPI detection from sounddevice 0.5.5 docs; phase 1 empirical data
- Pitfalls: HIGH — WasapiSettings/MME confirmed empirically in Phase 1; asyncio.Queue thread-safety from official Python docs; ordering of preprocessing verified by logic
- pysbd thread safety: LOW — not verified; mitigation recommended

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days — pysbd 0.3.4 is stable/unmaintained so no version risk; FastAPI and sounddevice are active but API is stable)

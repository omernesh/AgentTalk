# Hebrew TTS Setup Guide

AgentTalk supports two Hebrew TTS backends, both created by [maxmelichov](https://github.com/maxmelichov).
Choose the option that best fits your environment.

## Overview

| Feature              | HebrewPiper (Option A)            | Light-BlueTTS (Option B)            |
|----------------------|-----------------------------------|-------------------------------------|
| Setup effort         | Medium (Docker + model download)  | High (Python deps + 9 ONNX files)   |
| Docker required      | Yes                               | No                                  |
| Network required     | No (Docker runs locally)          | No (fully local inference)          |
| New Python deps      | None (requests already present)   | torch, onnxruntime, phonikud, etc.  |
| Disk usage           | ~300 MB (Docker image + models)   | ~3 GB (torch + ONNX models)         |
| GPU support          | No                                | Yes (use_gpu=True in TTSConfig)     |
| Voices               | 2 (male, female)                  | Multiple JSON style files           |
| Sample rate          | 22050 Hz                          | 44100 Hz                            |
| Quality              | Good                              | Better (local neural inference)     |

---

## Option A: HebrewPiper (PiperStream via Docker)

The simpler setup. PiperStream runs a REST API inside Docker that accepts raw Hebrew text,
applies automatic diacritization (phonikud), and returns synthesized WAV audio.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Setup Steps

**1. Clone the PiperStream repository:**

```bash
git clone https://github.com/maxmelichov/PiperStream
cd PiperStream
```

**2. Download the ONNX voice models:**

Follow the instructions in the PiperStream README to download `onnx.zip` and extract
the model files into the project directory. The repo provides links to the male and female
Piper ONNX models (`piper_medium_male.onnx`, `piper_medium_female.onnx`).

**3. Start the Docker service:**

```bash
docker compose up --build -d
```

The first build takes approximately 3 minutes. Subsequent starts are faster.

**4. Verify the service is running:**

```bash
curl http://localhost:8000/health
```

Expected response: `{"status": "ok"}` or similar success indicator.

**5. Switch AgentTalk to Hebrew:**

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"model": "hebrewpiper", "hebrewpiper_voice": "female"}'
```

**6. Test Hebrew speech:**

```bash
curl -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "שלום עולם, זה מבחן"}'
```

### Voice Options

- `"female"` (default) — uses `piper_medium_female.onnx`
- `"male"` — uses `piper_medium_male.onnx`

Switch voice via:

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"hebrewpiper_voice": "male"}'
```

List available voices:

```bash
curl http://localhost:5050/hebrew-voices
```

---

## Option B: Light-BlueTTS (Local Python Inference)

The higher-quality option. Light-BlueTTS runs fully locally using ONNX models — no Docker
or network service required. Requires significant disk space for PyTorch and model files.

### Prerequisites

- Python 3.10 or newer (AgentTalk requires 3.11)
- Approximately 3 GB of free disk space (PyTorch + ONNX models)

### Setup Steps

**1. Clone the Light-BlueTTS repository:**

```bash
git clone https://github.com/maxmelichov/Light-BlueTTS C:\path\to\Light-BlueTTS
```

Replace `C:\path\to\Light-BlueTTS` with your preferred absolute path.

**2. Install Python dependencies:**

```bash
pip install onnxruntime phonikud phonikud-onnx soundfile torch torchaudio
```

Alternatively, follow the repo's `uv sync` instructions if it provides a `pyproject.toml`.

**3. Download the ONNX model files:**

Follow the Light-BlueTTS README to download the `onnx_models/` directory (9 ONNX files
including `backbone.onnx`, `text_encoder.onnx`, `vocoder.onnx`, and others).

Also download `phonikud-1.0.onnx` as listed in the repo requirements.

Place these inside your Light-BlueTTS clone:

```
C:\path\to\Light-BlueTTS\
  onnx_models\
    backbone.onnx
    text_encoder.onnx
    vocoder.onnx
    ... (6 more ONNX files)
  phonikud-1.0.onnx
  voices\
    female1.json
    ... (other style files)
```

**4. Add Light-BlueTTS to your Python path:**

Windows (Command Prompt):

```cmd
set PYTHONPATH=C:\path\to\Light-BlueTTS
```

Windows (PowerShell):

```powershell
$env:PYTHONPATH = "C:\path\to\Light-BlueTTS"
```

macOS / Linux:

```bash
export PYTHONPATH=/path/to/Light-BlueTTS
```

For a permanent setting, add this to your shell profile or system environment variables.

**5. Configure AgentTalk:**

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lightblue",
    "lightblue_onnx_dir": "C:/path/to/Light-BlueTTS/onnx_models",
    "lightblue_phonikud_path": "C:/path/to/Light-BlueTTS/phonikud-1.0.onnx",
    "lightblue_voice_path": "C:/path/to/Light-BlueTTS/voices/female1.json"
  }'
```

Use forward slashes in paths even on Windows — Python handles both.

**6. Test Hebrew speech:**

```bash
curl -X POST http://localhost:5050/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "שלום עולם, זה מבחן"}'
```

### Voice Options

Voices are style JSON files in the `voices/` directory of the Light-BlueTTS clone.
List available voices once `lightblue_voice_path` is configured:

```bash
curl http://localhost:5050/hebrew-voices
```

Switch voice by updating `lightblue_voice_path`:

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"lightblue_voice_path": "C:/path/to/Light-BlueTTS/voices/male1.json"}'
```

---

## Switching Back to English

```bash
curl -X POST http://localhost:5050/config \
  -H "Content-Type: application/json" \
  -d '{"model": "kokoro"}'
```

Your Hebrew config keys (`hebrewpiper_host`, `lightblue_onnx_dir`, etc.) remain saved in
`config.json` so switching back to Hebrew does not require reconfiguration.

---

## Troubleshooting

**PiperStream ConnectionError — "PiperStream not reachable at http://localhost:8000":**
- Check that Docker Desktop is running.
- Verify the PiperStream container is up: `docker ps | grep piper`
- Ensure port 8000 is not occupied by another service: `netstat -ano | findstr :8000`
- Restart the container: `docker compose restart`

**Light-BlueTTS ImportError — "Light-BlueTTS not installed":**
- Verify `PYTHONPATH` includes the path to the cloned repo: `python -c "import hebrew_inference_helper"`
- Ensure all deps are installed: `pip show onnxruntime phonikud torch`
- On Windows, restart your terminal after setting `PYTHONPATH`

**Light-BlueTTS RuntimeError — "onnx_dir not configured":**
- `lightblue_onnx_dir` was not set in POST /config.
- Run the configure step in Option B, Step 5 above.

**Garbled or silent Hebrew audio:**
- Ensure the text is UTF-8 encoded before sending. Windows terminals may use cp1255.
- Test with a simple curl command rather than piping from other tools.
- Check `agenttalk.log` in `%APPDATA%\AgentTalk\` for synthesis errors.

**First synthesis is slow (Light-BlueTTS):**
- ONNX JIT compilation runs on first inference. Subsequent calls are faster.
- GPU acceleration (`use_gpu=True`) is not currently configurable via /config — it requires
  reinstantiating the engine (restart AgentTalk service after model path changes).

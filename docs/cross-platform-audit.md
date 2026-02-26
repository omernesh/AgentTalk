# AgentTalk Cross-Platform Audit

Date: 2026-02-26
Audited files: `agenttalk/config_loader.py`, `agenttalk/installer.py`, `agenttalk/tray.py`, `agenttalk/audio_duck.py`, `agenttalk/service.py`

---

## Summary

AgentTalk is currently Windows-only. The service architecture is portable (FastAPI + uvicorn + sounddevice), but several modules hard-code Windows-specific paths, APIs, and launch mechanisms.

---

## File-by-File Analysis

### agenttalk/config_loader.py

| Line | Issue | Portable? |
|------|-------|-----------|
| 17-20 | `_config_path()` uses `os.environ.get("APPDATA")` and falls back to `Path.home() / "AppData" / "Roaming"` — Windows-only config location | No — needs platform branch |

**macOS equivalent:** `~/Library/Application Support/AgentTalk/config.json`
**Linux equivalent:** `$XDG_CONFIG_HOME/AgentTalk/config.json` (fallback: `~/.config/AgentTalk/config.json`)

**Fix:** Add `_config_dir()` helper with `platform.system()` branch; replace `_config_path()` to call `_config_dir() / "config.json"`.

---

### agenttalk/installer.py

| Line | Issue | Portable? |
|------|-------|-----------|
| 22 | `APPDATA = Path(os.environ.get("APPDATA") or ...)` — Windows env var | No |
| 23 | `MODELS_DIR = APPDATA / "AgentTalk" / "models"` — derived from APPDATA | No |
| 117 | `ICON_PATH = APPDATA / "AgentTalk" / "icon.ico"` — Windows ICO format, Windows path | No |
| 148-208 | `create_shortcut()` — entire function uses `winshell`, `.lnk` format, `pythonw.exe` | Windows-only |
| No `register_autostart()` function | Auto-start functionality is missing; `create_shortcut()` is a manual launch mechanism, not a real auto-start | Missing on all platforms |

**macOS auto-start:** `~/Library/LaunchAgents/ai.agenttalk.plist` (launchd)
**Linux auto-start:** `~/.config/systemd/user/agenttalk.service` (systemd --user)
**Windows auto-start:** Task Scheduler XML or startup folder `.lnk`

**Fix:**
1. Import `_config_dir` from `config_loader` for cross-platform path resolution.
2. Add `register_autostart()` with `platform.system()` branches.
3. Guard `create_shortcut()` (and `winshell` import) behind `platform_system == "Windows"`.
4. `.ico` icon generation is Windows-only; on macOS/Linux, skip icon or generate `.png`.

---

### agenttalk/tray.py

| Line | Issue | Portable? |
|------|-------|-----------|
| 87-88 | `_piper_dir()` uses `os.environ.get("APPDATA")` and Windows path | No |

**pystray itself** is cross-platform (supports Win32, Cocoa/macOS, GTK/Linux AppIndicator).
Pillow (used for icon generation) is cross-platform.

**Fix:** Import `_config_dir` from `config_loader` and compute `_piper_dir()` as `_config_dir() / "models" / "piper"`.

---

### agenttalk/audio_duck.py

| Line | Issue | Portable? |
|------|-------|-----------|
| 1-128 | Entire module imports `comtypes` and `pycaw` — Windows Core Audio API (WASAPI) | Windows-only |
| 23-24 | Top-level imports: `import comtypes` and `from pycaw.pycaw import AudioUtilities` — fail on import on macOS/Linux | Critical — crashes on non-Windows |

**macOS equivalent:** No equivalent of WASAPI session-level ducking (macOS doesn't expose per-app volume APIs in the same way)
**Linux equivalent:** PulseAudio `pactl set-sink-input-volume` could duck streams, but is complex

**Fix:** Guard the entire module behind `platform.system() == "Windows"`. In `tts_worker.py` / `service.py`, replace direct `AudioDucker()` instantiation with a platform-conditional stub:

```python
import platform
if platform.system() == "Windows":
    from agenttalk.audio_duck import AudioDucker
    _ducker = AudioDucker()
else:
    class _NoOpDucker:
        def duck(self): pass
        def unduck(self): pass
        @property
        def is_ducked(self): return False
    _ducker = _NoOpDucker()
```

---

### agenttalk/service.py

| Line | Issue | Portable? |
|------|-------|-----------|
| 36-39 | `APPDATA_DIR = Path(os.environ["APPDATA"]) / "AgentTalk"` — `os.environ["APPDATA"]` raises `KeyError` on macOS/Linux | Critical — crashes on non-Windows |
| 37 | `LOG_FILE`, `PID_FILE`, `MODELS_DIR`, `MODEL_PATH`, `VOICES_PATH` all derived from APPDATA_DIR | No |
| 314 | Description string references "Windows" explicitly | Minor — cosmetic |
| 449 | `list_piper_voices()` uses `MODELS_DIR` (Windows-derived) for path | No |

**Fix:** Replace `os.environ["APPDATA"]` with `_config_dir()` imported from `config_loader`, deriving all paths from that cross-platform base.

---

### agenttalk/hooks/session_start_hook.py

| Line | Issue | Portable? |
|------|-------|-----------|
| 15 | `APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))` — Windows-only | No |
| 76-86 | `subprocess.Popen` with `DETACHED_PROCESS` and `CREATE_NEW_PROCESS_GROUP` — Windows-only `creationflags` | Windows-only |

**Fix:**
1. Use `_config_dir()` for APPDATA path.
2. For non-Windows, use `subprocess.Popen` with `start_new_session=True` instead of Windows `creationflags`.

---

## What Is Already Portable

| Component | Status |
|-----------|--------|
| FastAPI + uvicorn HTTP server | Fully portable |
| sounddevice audio playback | Portable (PortAudio cross-platform) |
| kokoro-onnx TTS engine | Portable (ONNX Runtime cross-platform) |
| piper-tts | Portable (piper-tts package supports Win/Mac/Linux) |
| pysbd sentence segmenter | Fully portable |
| pystray tray icon | Portable (Win32/Cocoa/GTK backends) |
| Pillow image generation | Fully portable |
| TTS queue / worker threading | Fully portable |
| preprocessor.py | Fully portable |
| Claude Code hooks logic | Portable (shell-based POST) |

---

## Required Changes Summary

| Priority | File | Change |
|----------|------|--------|
| Critical | `agenttalk/service.py` | Replace `os.environ["APPDATA"]` with `_config_dir()` call |
| Critical | `agenttalk/audio_duck.py` | Guard entire file behind Windows platform check |
| High | `agenttalk/config_loader.py` | Add `_config_dir()` with macOS/Linux branches |
| High | `agenttalk/installer.py` | Add `register_autostart()` (launchd/systemd/Task Scheduler); guard `create_shortcut()` to Windows-only |
| Medium | `agenttalk/tray.py` | Use `_config_dir()` in `_piper_dir()` |
| Medium | `agenttalk/hooks/session_start_hook.py` | Use `_config_dir()`, use `start_new_session=True` on non-Windows |
| Low | `pyproject.toml` | Remove `Operating System :: Microsoft :: Windows` classifier; add platform extras |

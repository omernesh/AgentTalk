"""
config_loader.py — Read/write %APPDATA%/AgentTalk/config.json.

Provides load_config() which returns the persisted settings dict.
Returns {} if the file is absent or malformed — never raises.

Phase 4 consumers: service.py reads pre_cue_path and post_cue_path at startup.
Phase 5: save_config() added for runtime persistence of all 7 CFG-02 settings fields.
"""
import json
import logging
import os
import threading
from pathlib import Path


def _config_path() -> Path:
    """Return the platform path to config.json."""
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(appdata) / "AgentTalk" / "config.json"


_CONFIG_LOCK = threading.Lock()


def load_config() -> dict:
    """
    Read %APPDATA%/AgentTalk/config.json and return its contents as a dict.

    Returns {} if:
    - The file does not exist (first run, no config yet).
    - The file contains invalid JSON (corrupted config).

    Never raises — config loading is best-effort. Logs a warning on parse error.

    CUE-04: Audio cue paths are configurable via config.json.
    """
    path = _config_path()
    if not path.exists():
        logging.debug("No config file found at %s — using defaults.", path)
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        cfg = json.loads(text)
        if not isinstance(cfg, dict):
            logging.warning("config.json does not contain a JSON object — ignoring.")
            return {}
        logging.debug("Loaded config from %s: %s", path, list(cfg.keys()))
        return cfg
    except Exception:
        logging.warning(
            "Failed to load config from %s — using defaults.", path, exc_info=True
        )
        return {}


def save_config(state: dict) -> None:
    """
    Persist runtime state to config.json atomically.

    Writes to .json.tmp then calls Path.replace() — atomic on Windows
    (os.replace() is guaranteed atomic within the same filesystem, Python 3.3+).

    Thread-safe via _CONFIG_LOCK — both the FastAPI handler thread and
    the tts_worker thread could call this concurrently.

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
        try:
            tmp.write_text(json.dumps(persisted, indent=2), encoding="utf-8")
            tmp.replace(path)  # os.replace() — atomic on Windows
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    logging.debug("Config saved to %s", path)

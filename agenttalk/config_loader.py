"""
config_loader.py — Read %APPDATA%/AgentTalk/config.json.

Provides load_config() which returns the persisted settings dict.
Returns {} if the file is absent or malformed — never raises.

Phase 4 consumers: service.py reads pre_cue_path and post_cue_path at startup.
Phase 5 will add write support (save_config) for slash command and tray setters.
"""
import json
import logging
import os
import pathlib


def _config_path() -> pathlib.Path:
    """Return the platform path to config.json."""
    appdata = os.environ.get("APPDATA", str(pathlib.Path.home()))
    return pathlib.Path(appdata) / "AgentTalk" / "config.json"


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

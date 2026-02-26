"""
AgentTalk background service — Phase 1: Service Skeleton and Core Audio.

Launch via: pythonw.exe agenttalk/service.py
Console suppression is handled by the pythonw.exe interpreter itself.
No special subprocess flags are needed for the service process itself.
"""
import os
import sys
import logging
import atexit
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# APPDATA paths — module-level constants (stdlib imports only at this point)
# ---------------------------------------------------------------------------
APPDATA_DIR = Path(os.environ["APPDATA"]) / "AgentTalk"
LOG_FILE    = APPDATA_DIR / "agenttalk.log"
PID_FILE    = APPDATA_DIR / "service.pid"
MODELS_DIR  = APPDATA_DIR / "models"


# ---------------------------------------------------------------------------
# Logging — must be initialised before any other code runs in main()
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """Configure file-only logging. pythonw.exe discards stdout/stderr."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            # No StreamHandler — pythonw.exe silently discards stdout/stderr
        ],
    )

    def _log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _log_uncaught


# ---------------------------------------------------------------------------
# Main entry point (scaffold — Plan 02 adds PID lock, Kokoro, HTTP server)
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()  # MUST be first — before any third-party imports or other code
    logging.info("=== AgentTalk service starting (scaffold) ===")
    logging.info("APPDATA_DIR: %s", APPDATA_DIR)
    logging.info("LOG_FILE: %s", LOG_FILE)
    logging.info("PID_FILE: %s", PID_FILE)
    logging.info("MODELS_DIR: %s", MODELS_DIR)
    try:
        logging.info("Scaffold startup complete. Plan 02 will add PID lock, Kokoro, and HTTP server.")
        # Keep main thread alive temporarily (Plan 02 will replace this)
        threading.Event().wait(timeout=2)
        logging.info("Scaffold exiting cleanly.")
    except Exception:
        logging.exception("Fatal error during scaffold startup")
        sys.exit(1)


if __name__ == "__main__":
    main()

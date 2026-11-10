"""
control_center/logger.py — logging for the Control Center.

Reuses the project's existing ``Bots_Folder/logger_config`` so the Control
Center writes into the very same ``Logs/`` directory and uses the same
colour scheme as the bots.
"""

import logging
import sys

_NAME = "control-center"


def _fallback_logger() -> logging.Logger:
    logger = logging.getLogger(_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            f"[{_NAME.upper():16s}] %(asctime)s %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
    return logger


def get_logger(name: str = _NAME) -> logging.Logger:
    """Return a logger configured like the rest of the project."""
    try:
        from logger_config import get_logger as _project_logger
        return _project_logger(name)
    except Exception:
        return _fallback_logger()


def configure_windows_encoding() -> None:
    """Force UTF-8 on stdout/stderr (Windows consoles default to cp1252)."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

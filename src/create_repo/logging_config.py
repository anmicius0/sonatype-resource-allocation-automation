"""
logging_config.py

Centralized logging configuration for the application and Uvicorn.

Goals:
- Ensure all logs (our app, FastAPI, Uvicorn, libraries) are written to a file
- Keep messages simple and readable for developers
- Avoid console noise unless explicitly enabled elsewhere
- Use a rotating file handler to prevent unbounded file growth
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Dict, Any


def configure_logging(log_file: Path, level: str = "INFO") -> Dict[str, Any]:
    """Apply the logging configuration and return it.

    This both configures Python logging immediately (so early startup logs are captured)
    and returns the dict so it can be passed to Uvicorn to keep a consistent setup.
    """
    # Simple, easy-to-read log line
    # example: 2025-08-08 12:34:56 | INFO     | create_repo.core:42 | Operation completed
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {
                "format": fmt,
                "datefmt": datefmt,
            }
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": level,
                "formatter": "simple",
                "filename": str(log_file),
                "mode": "a",
                "maxBytes": 5 * 1024 * 1024,  # 5 MB
                "backupCount": 3,
                "encoding": "utf-8",
            }
        },
        "loggers": {
            # Make sure our package logs are captured
            "create_repo": {"handlers": ["file"], "level": level, "propagate": False},
            # Uvicorn and FastAPI loggers
            "uvicorn": {"handlers": ["file"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["file"], "level": level, "propagate": False},
            "uvicorn.access": {
                "handlers": ["file"],
                "level": level,
                "propagate": False,
            },
            "fastapi": {"handlers": ["file"], "level": level, "propagate": False},
            # Noisy libraries can be tuned here if needed
            "urllib3": {"handlers": ["file"], "level": "WARNING", "propagate": False},
            "httpx": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        },
        "root": {"handlers": ["file"], "level": level},
    }
    logging.config.dictConfig(config)
    return config
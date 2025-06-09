"""
Common utilities, exceptions, and logging configuration.
"""

import json
import logging
import logging.config
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# --- Custom Exceptions ---


class ValidationError(ValueError):
    """Exception for validation errors (HTTP 400)."""

    pass


class ConfigurationError(Exception):
    """Exception for configuration errors (HTTP 500)."""

    pass


# --- Utility Functions ---


def get_application_path() -> Path:
    """Determines the application's root directory, supporting both scripts and frozen executables."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # For PyInstaller executables, the root is the directory containing the executable.
        return Path(sys.executable).parent
    else:
        # For scripts, assume the project root is three levels up from this file's location
        # (src/create_repo/common.py -> src/create_repo -> src -> project_root).
        return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=64)
def load_json_file(filename: str, default: Any = None) -> Any:
    """Loads a JSON file with caching, raising specific errors on failure."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"Configuration file not found: {filename}")
        return default
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in '{filename}': {e}")
    except PermissionError:
        raise ConfigurationError(f"Permission denied accessing '{filename}'")
    except Exception as e:
        raise ConfigurationError(f"Error reading '{filename}': {e}")


def parse_csv(value: str, default: Optional[List[str]] = None) -> List[str]:
    """Parses a comma-separated string into a list of strings."""
    if not value:
        return default or []
    return [v.strip() for v in value.split(",") if v.strip()]


def get_resource_path(relative_path: Union[str, Path]) -> Path:
    """
    Get the absolute path to a resource, handling both development and frozen (PyInstaller) states.
    """
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    return Path(base_path) / relative_path


# --- Logging Configuration ---


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

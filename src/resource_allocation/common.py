"""
Common utilities, exceptions, and logging configuration.
"""

import json
import logging
import logging.config
import sys
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
def get_app_path() -> Path:
    """
    Determines the application's root directory for external files (config/.env, logs/).
    Only support PyInstaller executables.
    """
    # For PyInstaller executables, external files should be relative to the executable
    app_path = Path(sys.executable).parent
    return app_path


def load_json_file(filename: str) -> Dict[str, Any]:
    """Loads a JSON file with caching, raising specific errors on failure."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        logging.warning(f"Configuration file not found: {filename}")
        raise ConfigurationError(f"Configuration file not found: {filename}")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in '{filename}': {e}")
        raise ConfigurationError(f"Invalid JSON in '{filename}': {e}")
    except PermissionError:
        logging.error(f"Permission denied accessing '{filename}'")
        raise ConfigurationError(f"Permission denied accessing '{filename}'")
    except Exception as e:
        logging.error(f"Error reading '{filename}': {e}")
        raise ConfigurationError(f"Error reading '{filename}': {e}")


def parse_csv(value: str, default: Optional[List[str]] = None) -> List[str]:
    """Parses a comma-separated string into a list of strings."""
    if not value:
        return default or []
    return [v.strip() for v in value.split(",") if v.strip()]


def get_resource_path(relative_path: Union[str, Path]) -> Path:
    """
    Get the absolute path to a bundled resource (like JSON config files).

    For PyInstaller executables: Uses the temporary extraction directory (_MEIPASS)
    For development: Uses the project root directory
    """
    if getattr(sys, "frozen", False):
        # For PyInstaller executables, use the temporary extraction directory
        base_path = Path(getattr(sys, "_MEIPASS", ""))
        resource_path = base_path / relative_path
    else:
        # For development, use the source directory structure
        base_path = Path(__file__).resolve().parent.parent.parent
        resource_path = base_path / relative_path

    return resource_path


# --- Logging Configuration ---
def configure_logging(log_file: Path, level: str = "INFO") -> Dict[str, Any]:
    """Apply the logging configuration and return it."""
    # Simple, easy-to-read log line
    # example: 2025-08-08 12:34:56 | INFO | resource_allocation.core:42 | Operation completed
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
            "resource_allocation": {
                "handlers": ["file"],
                "level": level,
                "propagate": False,
            },
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

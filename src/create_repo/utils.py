"""
utils.py

General utility functions for file operations and data processing.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, List, Optional, Union
from functools import lru_cache

from create_repo.app_config import ConfigurationError

logger = logging.getLogger(__name__)


def get_application_path() -> Path:
    """Determimes the application's root directory, supporting both scripts and frozen executables."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # For PyInstaller executables, the root is the directory containing the executable.
        return Path(sys.executable).parent
    else:
        # For scripts, assume the project root is three levels up from this file's location
        # (src/create_repo/utils.py -> src/create_repo -> src -> project_root).
        return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=64)
def load_json_file(filename: str, default: Any = None) -> Any:
    """Loads a JSON file with caching, raising specific errors on failure."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {filename}")
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

import json


def load_json_file(filename, default=None):
    """Load a JSON file with absolute path, return default if not found."""
    try:
        with open(filename) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def parse_bool(value, default=False):
    """Parse a boolean environment variable."""
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


def parse_csv(value, default=None):
    """Parse a comma-separated environment variable into a list."""
    if not value:
        return default or []
    return [v.strip() for v in value.split(",") if v.strip()]

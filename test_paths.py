#!/usr/bin/env python3
"""
Test script to verify path detection for both development and executable modes.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from create_repo.common import get_application_path, get_resource_path


def test_paths():
    """Test path detection functions."""
    print("=== Path Detection Test ===")
    print(f"Python executable: {sys.executable}")
    print(f"Script location: {__file__}")
    print(f"Is frozen: {getattr(sys, 'frozen', False)}")
    print(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'Not available')}")
    print()

    # Test application path
    app_path = get_application_path()
    print(f"Application path: {app_path}")
    print(f"App path exists: {app_path.exists()}")
    print()

    # Test expected external file locations
    env_file = app_path / "config" / ".env"
    print(f"Expected .env file: {env_file}")
    print(f".env file exists: {env_file.exists()}")

    logs_dir = app_path / "logs"
    print(f"Expected logs directory: {logs_dir}")
    print(f"Logs directory exists: {logs_dir.exists()}")
    print()

    # Test bundled resource paths
    org_config = get_resource_path("config/organisations.json")
    print(f"Organizations config: {org_config}")
    print(f"Organizations config exists: {org_config.exists()}")

    pm_config = get_resource_path("config/package_manager.json")
    print(f"Package manager config: {pm_config}")
    print(f"Package manager config exists: {pm_config.exists()}")
    print()

    print("=== Summary ===")
    if getattr(sys, "frozen", False):
        print("Running as executable - external files should be relative to executable")
        print("Bundled resources should be in temporary extraction directory")
    else:
        print("Running as script - all files should be relative to project root")


if __name__ == "__main__":
    test_paths()

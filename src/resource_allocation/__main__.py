"""
Entry point for the Nexus Repository and Privilege Manager API application.
"""

import logging
import os
import sys
from typing import Dict, Any

import uvicorn
from dotenv import load_dotenv

from resource_allocation.common import (
    get_app_path,
    configure_logging,
)


def main():
    """Main application entry point."""
    try:
        app_config = _initialize_app()
        _log_startup_info(app_config)
        _start_server(app_config)
    except Exception as e:
        print(f"Failed to start application: {e}")
        sys.exit(1)


def _initialize_app() -> Dict[str, Any]:
    """Initialize application configuration."""
    app_path = get_app_path()
    env_file_path = app_path / "config" / ".env"

    if not env_file_path.exists():
        raise FileNotFoundError(f".env file not found at {env_file_path}")

    load_dotenv(env_file_path)

    # Setup logging once
    log_dir = app_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_config = configure_logging(log_file, log_level)

    return {
        "app_path": app_path,
        "env_file_path": env_file_path,
        "log_file": log_file,
        "log_level": log_level,
        "log_config": log_config,
        "host": os.getenv("API_HOST", "127.0.0.1"),
        "port": int(os.getenv("PORT", 5000)),
    }


def _log_startup_info(config: Dict[str, Any]) -> None:
    """Log startup information concisely."""
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting Nexus Repository Manager API")
    logger.info(
        f"Server: {config['host']}:{config['port']} | Log Level: {config['log_level']}"
    )
    logger.info(f"Config: {config['env_file_path']} | Logs: {config['log_file']}")
    logger.info(f"API Token: {'Configured' if os.getenv('API_TOKEN') else 'Missing'}")
    logger.info(f"Nexus: {os.getenv('NEXUS_URL', 'Not configured')}")
    logger.info(f"IQ Server: {os.getenv('IQSERVER_URL', 'Not configured')}")


def _start_server(config: Dict[str, Any]) -> None:
    """Start the uvicorn server with the given configuration."""
    uvicorn.run(
        "resource_allocation.api:app",
        host=config["host"],
        port=config["port"],
        log_config=config["log_config"],
        log_level=config["log_level"].lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()

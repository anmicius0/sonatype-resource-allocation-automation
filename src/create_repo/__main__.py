"""
Entry point for the Nexus Repository and Privilege Manager API application.
"""

import os
import logging
from dotenv import load_dotenv
import uvicorn

from create_repo.utils import get_application_path
from create_repo.logging_config import configure_logging


# --- Main Entry Point ---


def main():
    """Initializes and runs the FastAPI application."""
    app_path = get_application_path()
    load_dotenv(app_path / ".env")

    # Ensure the logs directory exists under the application path
    log_dir = app_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # Log file path
    log_file = log_dir / "app.log"

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    # Configure centralized logging and capture everything to the file
    log_config = configure_logging(log_file, log_level)

    port = int(os.getenv("PORT", 5000))
    host = os.getenv("API_HOST", "127.0.0.1")

    logging.info(f"Starting Nexus Repository Manager API on {host}:{port}")
    uvicorn.run(
        "create_repo.api:app",
        host=host,
        port=port,
        log_config=log_config,
        log_level=log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()

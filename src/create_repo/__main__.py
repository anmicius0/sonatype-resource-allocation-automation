"""
Entry point for the Nexus Repository and Privilege Manager API application.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

from create_repo.common import get_application_path, configure_logging


# --- Main Entry Point ---


def main():
    """Initializes and runs the FastAPI application."""
    # Set up basic logging first for early debugging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    app_path = get_application_path()

    # Load environment variables from config/.env under application path
    env_file_path = app_path / "config" / ".env"

    # Debug information before checking .env file
    logger.debug(f"Application path: {app_path}")
    logger.debug(f"Looking for .env file at: {env_file_path}")
    logger.debug(f"Is frozen executable: {getattr(sys, 'frozen', False)}")
    if getattr(sys, "frozen", False):
        logger.debug(f"Executable location: {sys.executable}")
        logger.debug(f"MEIPASS: {getattr(sys, '_MEIPASS', 'Not available')}")

    if not env_file_path.exists():
        logger.error(f".env file not found at {env_file_path}")
        logger.error(f"Application path resolved to: {app_path.absolute()}")
        logger.error(
            f"Config directory should be at: {(app_path / 'config').absolute()}"
        )
        logger.error(
            "Please ensure the config/.env file is placed relative to the executable"
        )
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            logger.error(
                f"For executable deployment, place config/.env at: {exe_dir / 'config' / '.env'}"
            )
        logger.error(f"Current working directory: {Path.cwd()}")
        logger.error(f"Contents of app_path ({app_path}):")
        try:
            for item in app_path.iterdir():
                logger.error(f"  {item.name}{'/' if item.is_dir() else ''}")
        except Exception as e:
            logger.error(f"  Error listing directory: {e}")
        sys.exit(1)

    logger.info(f"Found .env file at: {env_file_path}")
    load_dotenv(env_file_path)

    # Ensure the logs directory exists under the application path
    log_dir = app_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # Log file path
    log_file = log_dir / "app.log"

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_config = configure_logging(log_file, log_level)

    port = int(os.getenv("PORT", 5000))
    host = os.getenv("API_HOST", "127.0.0.1")

    # Log startup information
    logging.info("=" * 60)
    logging.info("Nexus Repository Manager API Starting Up")
    logging.info("=" * 60)
    logging.info(f"Application path: {app_path}")
    logging.info(f"Environment file: {env_file_path}")
    logging.info(f"Is frozen executable: {getattr(sys, 'frozen', False)}")
    if getattr(sys, "frozen", False):
        logging.info(f"Executable path: {sys.executable}")
        logging.info(
            f"PyInstaller temp dir: {getattr(sys, '_MEIPASS', 'Not available')}"
        )
    logging.info(f"Log file: {log_file}")
    logging.info(f"Log level: {log_level}")
    logging.info(f"Server will start on {host}:{port}")
    logging.info(f"Debug mode: {os.getenv('DEBUG', 'false')}")
    logging.info(f"API token configured: {'Yes' if os.getenv('API_TOKEN') else 'No'}")
    logging.info(f"Nexus URL: {os.getenv('NEXUS_URL', 'Not configured')}")
    logging.info(f"IQ Server URL: {os.getenv('IQSERVER_URL', 'Not configured')}")
    logging.info("=" * 60)

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

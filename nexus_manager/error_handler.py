import logging
import sys
from typing import Callable, TypeVar, Any, Optional
from functools import wraps
import requests

# Type variable for generic function signatures
F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Enhanced error handling for Nexus operations with detailed API error reporting."""

    @staticmethod
    def handle_operation(
        operation_type: str = "operation", return_none_on_error: bool = False
    ):
        """Generic error handler that can be configured for different operation types."""

        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Connection failed during {operation_type}: {e}")
                    print(
                        f"❌ Connection failed. Check server connectivity.",
                        file=sys.stderr,
                    )
                    return None if return_none_on_error else False

                except requests.exceptions.HTTPError as e:
                    status_code = (
                        getattr(e.response, "status_code", None) if e.response else None
                    )
                    response_text = ""
                    if e.response:
                        try:
                            response_data = e.response.json()
                            if isinstance(response_data, dict):
                                response_text = response_data.get(
                                    "message", str(response_data)
                                )
                            else:
                                response_text = str(response_data)
                        except (ValueError, TypeError):
                            response_text = e.response.text

                    if status_code == 401:
                        logger.error(f"Authentication failed during {operation_type}")
                        print(
                            "❌ Authentication failed. Check credentials.",
                            file=sys.stderr,
                        )
                    elif status_code == 403:
                        logger.error(f"Access forbidden during {operation_type}")
                        print(
                            "❌ Access forbidden. Check permissions.", file=sys.stderr
                        )
                    elif status_code == 404:
                        logger.warning(f"Resource not found during {operation_type}")
                        print(
                            f"⚠️ Resource not found during {operation_type}",
                            file=sys.stderr,
                        )
                        return None if return_none_on_error else False
                    elif status_code == 409:
                        logger.warning(f"Resource conflict during {operation_type}")
                        print(
                            f"⚠️ Resource already exists during {operation_type}",
                            file=sys.stderr,
                        )
                        return None if return_none_on_error else False
                    elif status_code == 400:
                        logger.error(
                            f"Bad request during {operation_type}: {response_text}"
                        )
                        print(
                            f"❌ Bad request during {operation_type}: {response_text}",
                            file=sys.stderr,
                        )
                    else:
                        logger.error(
                            f"HTTP error {status_code} during {operation_type}: {response_text}"
                        )
                        print(
                            f"❌ HTTP error during {operation_type}: {status_code} - {response_text}",
                            file=sys.stderr,
                        )
                    return None if return_none_on_error else False

                except (ValueError, RuntimeError, KeyError, FileNotFoundError) as e:
                    logger.error(f"Error during {operation_type}: {e}")
                    print(f"❌ {operation_type.title()} Error: {e}", file=sys.stderr)
                    return None if return_none_on_error else False

                except Exception as e:
                    logger.error(
                        f"Unexpected error during {operation_type}: {type(e).__name__} - {e}"
                    )
                    print(
                        f"❌ Unexpected error during {operation_type}: {e}",
                        file=sys.stderr,
                    )
                    return None if return_none_on_error else False

            return wrapper  # type: ignore[return-value]

        return decorator

    @staticmethod
    def handle_config_error(func: F) -> F:
        """Handle configuration errors with immediate exit."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except (ValueError, FileNotFoundError, KeyError) as e:
                logger.error(f"Configuration error: {e}")
                print(f"❌ Configuration Error: {e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                logger.error(f"Unexpected configuration error: {e}")
                print(f"❌ Unexpected Configuration Error: {e}", file=sys.stderr)
                sys.exit(1)

        return wrapper  # type: ignore[return-value]

    @staticmethod
    def handle_main_execution(func: F) -> F:
        """Handle main execution with graceful error handling and proper exit codes."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                logger.info("Operation cancelled by user")
                print("\n⏹️ Operation cancelled by user.", file=sys.stderr)
                sys.exit(130)
            except (
                ValueError,
                RuntimeError,
                ConnectionError,
                requests.exceptions.HTTPError,
            ) as e:
                logger.error(f"Operation failed: {e}")
                print(f"❌ Error: {e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                logger.error(f"Unexpected error: {type(e).__name__} - {e}")
                print(f"❌ Unexpected Error: {type(e).__name__} - {e}", file=sys.stderr)
                sys.exit(1)

        return wrapper  # type: ignore[return-value]


# Simplified exception classes
class NexusOperationError(Exception):
    """Base exception for Nexus operations."""

    pass

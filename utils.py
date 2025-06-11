import logging
from functools import wraps


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def log_exceptions(func):
    """Decorator to log any exception raised by the wrapped function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - simple logging wrapper
            logging.getLogger(func.__module__).exception("Error in %s", func.__name__)
            raise

    return wrapper


def async_log_exceptions(func):
    """Async variant of log_exceptions."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception:
            logging.getLogger(func.__module__).exception("Error in %s", func.__name__)
            raise

    return wrapper

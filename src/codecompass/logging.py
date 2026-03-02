import logging
import os
import sys


BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
GREY = "\033[0;90m"
RED = "\033[0;31m"
NC = "\033[0m"

_LOG_SUCCESS = 25  # between INFO(20) and WARNING(30)
logging.addLevelName(_LOG_SUCCESS, "SUCCESS")

_STYLES: dict = {
    logging.DEBUG: (GREY, "[DEBUG]"),
    logging.INFO: (BLUE, "[INFO]"),
    _LOG_SUCCESS: (GREEN, "[SUCCESS]"),
    logging.WARNING: (YELLOW, "[WARNING]"),
    logging.ERROR: (RED, "[ERROR]"),
}


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color, prefix = _STYLES.get(record.levelno, (NC, f"[{record.levelname}]"))
        return f"{color}{prefix}{NC} {record.getMessage()}"


class _StderrHandler(logging.StreamHandler):
    """StreamHandler that always resolves sys.stderr at emit time (supports pytest capsys)."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        self.setFormatter(_ColorFormatter())

    @property  # type: ignore[override]
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _) -> None:
        pass


_logger = logging.getLogger("codecompass")
_logger.addHandler(_StderrHandler())
_logger.propagate = False
_logger.setLevel(logging.DEBUG)

_env_level = os.environ.get("LOG_LEVEL", "").upper()
if _env_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
    _logger.setLevel(getattr(logging, _env_level))


def log_info(message: str) -> None:
    _logger.info(message)


def log_success(message: str) -> None:
    _logger.log(_LOG_SUCCESS, message)


def log_warning(message: str) -> None:
    _logger.warning(message)


def log_debug(message: str) -> None:
    _logger.debug(message)


def log_error(message: str) -> None:
    _logger.error(message)

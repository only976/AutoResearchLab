import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = Path(os.environ.get("ARL_LOG_DIR", PROJECT_ROOT / "logs"))

_LOGGING_CONFIGURED = False


def _ensure_log_dir(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_logging(level: int = logging.INFO, log_dir: Optional[str] = None) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    target_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    log_path = _ensure_log_dir(target_dir)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        str(log_path / "system.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    error_handler = TimedRotatingFileHandler(
        str(log_path / "error.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        logging.getLogger(logger_name).propagate = True

    _LOGGING_CONFIGURED = True


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    configure_logging(level)
    return logging.getLogger(name)

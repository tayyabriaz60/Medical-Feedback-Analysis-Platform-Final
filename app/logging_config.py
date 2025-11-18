"""
Centralized logging configuration for the Medical Feedback Analysis Platform.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class _ColoredFormatter(logging.Formatter):
    """Lightweight color formatter for development console logs."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        base_level = record.levelname
        if base_level in self.COLORS and self._use_color():
            record.levelname = f"{self.COLORS[base_level]}{base_level}{self.RESET}"
        return super().format(record)

    @staticmethod
    def _use_color() -> bool:
        return os.getenv("NO_COLOR", "0") != "1"


def setup_logging(
    log_level: Optional[str] = None,
    log_file: str = "logs/app.log",
    enable_console: bool = True,
    enable_file: bool = True,
) -> logging.Logger:
    """
    Configure the root logger with sensible defaults for console and file outputs.
    """
    env_level = (log_level or os.getenv("LOG_LEVEL") or "INFO").upper()
    numeric_level = getattr(logging, env_level, logging.INFO)

    logs_path = Path(log_file).parent
    logs_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - "
        "[%(filename)s:%(lineno)d:%(funcName)s] - %(message)s"
    )

    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        if os.getenv("ENVIRONMENT", "development") == "development":
            console_handler.setFormatter(_ColoredFormatter(formatter._fmt))
        else:
            console_handler.setFormatter(formatter)
        console_handler.setLevel(numeric_level)
        root_logger.addHandler(console_handler)

    if enable_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(detailed_formatter)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

    # Silence noisy dependencies
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    root_logger.debug("Logging configured", extra={"level": env_level})
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Helper to get module-specific loggers."""
    return logging.getLogger(name)



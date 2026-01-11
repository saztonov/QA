"""Application-wide logging module for program flow tracking.

This module provides structured logging to both console and file,
helping debug and track application behavior beyond API interactions.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class AppLogger:
    """Application-wide logger for program flow tracking."""

    LOGS_DIR = Path("logs")

    def __init__(self, name: str = "qa_app", console_level: int = logging.INFO):
        """Initialize application logger.

        Args:
            name: Logger name.
            console_level: Logging level for console output.
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if self.logger.handlers:
            return

        # Console handler - INFO level by default
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(self._get_formatter(detailed=False))
        self.logger.addHandler(console_handler)

        # File handler - DEBUG level for full details
        self._setup_file_handler()

    def _get_formatter(self, detailed: bool = False) -> logging.Formatter:
        """Get log formatter.

        Args:
            detailed: If True, include function name and line number.
        """
        if detailed:
            return logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        return logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )

    def _setup_file_handler(self) -> None:
        """Setup file handler for logging to file."""
        try:
            self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            log_file = self.LOGS_DIR / f"app_{datetime.now():%Y%m%d_%H%M%S}.log"

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(self._get_formatter(detailed=True))
            self.logger.addHandler(file_handler)

            self._log_file_path = log_file
        except Exception as e:
            print(f"Warning: Could not setup file logging: {e}")
            self._log_file_path = None

    @property
    def log_file_path(self) -> Optional[Path]:
        """Get path to the current log file."""
        return getattr(self, '_log_file_path', None)

    # Main logging methods
    def info(self, msg: str) -> None:
        """Log info message."""
        self.logger.info(msg)

    def debug(self, msg: str) -> None:
        """Log debug message."""
        self.logger.debug(msg)

    def warning(self, msg: str) -> None:
        """Log warning message."""
        self.logger.warning(msg)

    def error(self, msg: str, exc_info: bool = False) -> None:
        """Log error message.

        Args:
            msg: Error message.
            exc_info: If True, include exception traceback.
        """
        self.logger.error(msg, exc_info=exc_info)

    def exception(self, msg: str) -> None:
        """Log exception with full traceback."""
        self.logger.exception(msg)

    # Convenience methods for specific events
    def startup(self, version: str = "1.0") -> None:
        """Log application startup."""
        self.info(f"{'='*60}")
        self.info(f"Application starting - version {version}")
        self.info(f"Log file: {self.log_file_path}")
        self.info(f"{'='*60}")

    def shutdown(self) -> None:
        """Log application shutdown."""
        self.info("Application shutting down")
        self.info(f"{'='*60}")

    def document_loaded(self, path: str, blocks_count: int) -> None:
        """Log document loading."""
        self.info(f"Document loaded: {path} ({blocks_count} blocks)")

    def crops_loaded(self, path: str) -> None:
        """Log crops folder loading."""
        self.info(f"Crops folder loaded: {path}")

    def planning_start(self, question: str) -> None:
        """Log planning start."""
        self.debug(f"Planning: {question[:100]}...")

    def planning_complete(self, decision: str, blocks_count: int, rois_count: int) -> None:
        """Log planning completion."""
        self.info(f"Plan: {decision} (blocks={blocks_count}, rois={rois_count})")

    def answering_start(self, question: str, iteration: int) -> None:
        """Log answering start."""
        self.debug(f"Answering (iter {iteration}): {question[:100]}...")

    def answering_complete(self, confidence: str, citations_count: int) -> None:
        """Log answering completion."""
        self.info(f"Answer: confidence={confidence}, citations={citations_count}")

    def roi_selected(self, image_path: str, bbox: tuple) -> None:
        """Log ROI selection."""
        self.debug(f"ROI selected: {image_path} bbox={bbox}")

    def mode_changed(self, mode: str, planner: str, answerer: str) -> None:
        """Log processing mode change."""
        self.info(f"Mode changed: {mode} (planner={planner}, answerer={answerer})")

    def index_progress(self, current: int, total: int) -> None:
        """Log indexing progress."""
        self.debug(f"Indexing: {current}/{total}")

    def cache_operation(self, operation: str, details: str) -> None:
        """Log cache operation."""
        self.debug(f"Cache {operation}: {details}")

    def ui_action(self, action: str) -> None:
        """Log UI action."""
        self.debug(f"UI: {action}")


# Singleton instance
app_logger = AppLogger()

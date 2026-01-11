"""API Logger module for detailed logging of all API operations.

This module provides dataclasses and utilities for comprehensive logging
of API requests, responses, and processing details.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import json
import os


class LogEventType(Enum):
    """Types of log events."""
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    PLANNING_START = "PLANNING_START"
    PLANNING_COMPLETE = "PLANNING_COMPLETE"
    ANSWERING_START = "ANSWERING_START"
    ANSWERING_COMPLETE = "ANSWERING_COMPLETE"
    EVIDENCE_LOAD = "EVIDENCE_LOAD"
    SUMMARIZATION = "SUMMARIZATION"
    INDEXING = "INDEXING"


class OperationType(Enum):
    """Types of API operations."""
    PLANNING = "planning"
    ANSWERING = "answering"
    SUMMARIZING = "summarizing"
    INDEXING = "indexing"
    CHAT = "chat"


@dataclass
class FileInfo:
    """Information about a file sent to API."""
    path: str
    size_bytes: int = 0
    mime_type: str = ""

    @classmethod
    def from_path(cls, file_path: str) -> "FileInfo":
        """Create FileInfo from file path."""
        size = 0
        mime_type = ""
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".pdf": "application/pdf",
                ".txt": "text/plain",
                ".md": "text/markdown",
            }
            mime_type = mime_types.get(ext, "application/octet-stream")
        return cls(path=file_path, size_bytes=size, mime_type=mime_type)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "size_human": self._format_size(self.size_bytes),
            "mime_type": self.mime_type,
        }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in human-readable form."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"


@dataclass
class APILogEntry:
    """Complete log entry for an API operation."""

    # Identification
    timestamp: datetime
    event_type: LogEventType
    operation: OperationType
    model: str

    # Timing
    duration_ms: float = 0.0

    # Request data (full)
    system_prompt: Optional[str] = None
    user_message: str = ""
    files_info: list[FileInfo] = field(default_factory=list)
    images_info: list[FileInfo] = field(default_factory=list)

    # Response data (full)
    response_raw: Optional[str] = None
    response_parsed: Optional[dict] = None
    thoughts: Optional[str] = None

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0

    # Status
    status: str = "success"  # success, error, timeout
    error_message: Optional[str] = None

    # Additional context
    iteration: int = 1
    decision: Optional[str] = None  # For planning: ANSWER_FROM_TEXT, NEED_BLOCKS, etc.
    confidence: Optional[str] = None  # For answering: high, medium, low
    citations_count: int = 0

    def __post_init__(self):
        """Calculate total tokens if not provided."""
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens + self.thoughts_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "operation": self.operation.value,
            "model": self.model,
            "duration_ms": round(self.duration_ms, 2),
            "duration_human": self._format_duration(self.duration_ms),

            # Request
            "request": {
                "system_prompt": self.system_prompt,
                "system_prompt_length": len(self.system_prompt) if self.system_prompt else 0,
                "user_message": self.user_message,
                "user_message_length": len(self.user_message),
                "files": [f.to_dict() for f in self.files_info],
                "images": [f.to_dict() for f in self.images_info],
                "files_count": len(self.files_info),
                "images_count": len(self.images_info),
            },

            # Response
            "response": {
                "raw": self.response_raw,
                "raw_length": len(self.response_raw) if self.response_raw else 0,
                "parsed": self.response_parsed,
                "thoughts": self.thoughts,
                "thoughts_length": len(self.thoughts) if self.thoughts else 0,
            },

            # Tokens
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "thoughts": self.thoughts_tokens,
                "total": self.total_tokens,
            },

            # Status
            "status": self.status,
            "error_message": self.error_message,

            # Context
            "context": {
                "iteration": self.iteration,
                "decision": self.decision,
                "confidence": self.confidence,
                "citations_count": self.citations_count,
            },
        }

    def to_compact_dict(self) -> dict:
        """Convert to compact dictionary for timeline display."""
        return {
            "time": self.timestamp.strftime("%H:%M:%S.%f")[:-3],
            "type": self.event_type.value,
            "operation": self.operation.value,
            "model": self._short_model_name(),
            "duration": self._format_duration(self.duration_ms),
            "tokens": f"in:{self.input_tokens:,} out:{self.output_tokens:,}",
            "status": self.status,
            "files": len(self.files_info) + len(self.images_info),
        }

    def _short_model_name(self) -> str:
        """Get short model name for display."""
        if "flash" in self.model.lower():
            return "Flash"
        elif "pro" in self.model.lower():
            return "Pro"
        return self.model.split("-")[-1] if "-" in self.model else self.model

    @staticmethod
    def _format_duration(ms: float) -> str:
        """Format duration in human-readable form."""
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60000:
            return f"{ms/1000:.1f}s"
        else:
            minutes = int(ms // 60000)
            seconds = (ms % 60000) / 1000
            return f"{minutes}m {seconds:.0f}s"


class APILogger:
    """Central logger for API operations."""

    def __init__(self, max_entries: int = 1000):
        self.entries: list[APILogEntry] = []
        self.max_entries = max_entries
        self._listeners: list[callable] = []

    def add_listener(self, callback: callable):
        """Add a listener for new log entries."""
        self._listeners.append(callback)

    def remove_listener(self, callback: callable):
        """Remove a listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def log(self, entry: APILogEntry):
        """Add a log entry and notify listeners."""
        self.entries.append(entry)

        # Rotate if needed
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        # Notify listeners
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception as e:
                print(f"[APILogger] Listener error: {e}")

    def log_planning_start(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        files: list[str] = None,
        images: list[str] = None,
    ) -> APILogEntry:
        """Log the start of a planning operation."""
        entry = APILogEntry(
            timestamp=datetime.now(),
            event_type=LogEventType.PLANNING_START,
            operation=OperationType.PLANNING,
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
            files_info=[FileInfo.from_path(f) for f in (files or [])],
            images_info=[FileInfo.from_path(f) for f in (images or [])],
            status="in_progress",
        )
        self.log(entry)
        return entry

    def log_planning_complete(
        self,
        model: str,
        duration_ms: float,
        response_raw: str,
        response_parsed: dict,
        decision: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thoughts: str = None,
        thoughts_tokens: int = 0,
    ) -> APILogEntry:
        """Log completion of a planning operation."""
        entry = APILogEntry(
            timestamp=datetime.now(),
            event_type=LogEventType.PLANNING_COMPLETE,
            operation=OperationType.PLANNING,
            model=model,
            duration_ms=duration_ms,
            response_raw=response_raw,
            response_parsed=response_parsed,
            decision=decision,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thoughts=thoughts,
            thoughts_tokens=thoughts_tokens,
            status="success",
        )
        self.log(entry)
        return entry

    def log_answering_start(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        files: list[str] = None,
        images: list[str] = None,
        iteration: int = 1,
    ) -> APILogEntry:
        """Log the start of an answering operation."""
        entry = APILogEntry(
            timestamp=datetime.now(),
            event_type=LogEventType.ANSWERING_START,
            operation=OperationType.ANSWERING,
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
            files_info=[FileInfo.from_path(f) for f in (files or [])],
            images_info=[FileInfo.from_path(f) for f in (images or [])],
            iteration=iteration,
            status="in_progress",
        )
        self.log(entry)
        return entry

    def log_answering_complete(
        self,
        model: str,
        duration_ms: float,
        response_raw: str,
        response_parsed: dict,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thoughts: str = None,
        thoughts_tokens: int = 0,
        confidence: str = None,
        citations_count: int = 0,
        iteration: int = 1,
    ) -> APILogEntry:
        """Log completion of an answering operation."""
        entry = APILogEntry(
            timestamp=datetime.now(),
            event_type=LogEventType.ANSWERING_COMPLETE,
            operation=OperationType.ANSWERING,
            model=model,
            duration_ms=duration_ms,
            response_raw=response_raw,
            response_parsed=response_parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thoughts=thoughts,
            thoughts_tokens=thoughts_tokens,
            confidence=confidence,
            citations_count=citations_count,
            iteration=iteration,
            status="success",
        )
        self.log(entry)
        return entry

    def log_error(
        self,
        operation: OperationType,
        model: str,
        error_message: str,
        duration_ms: float = 0.0,
    ) -> APILogEntry:
        """Log an error."""
        entry = APILogEntry(
            timestamp=datetime.now(),
            event_type=LogEventType.ERROR,
            operation=operation,
            model=model,
            duration_ms=duration_ms,
            status="error",
            error_message=error_message,
        )
        self.log(entry)
        return entry

    def get_all_entries(self) -> list[dict]:
        """Get all entries as dictionaries."""
        return [e.to_dict() for e in self.entries]

    def get_compact_entries(self) -> list[dict]:
        """Get all entries in compact form."""
        return [e.to_compact_dict() for e in self.entries]

    def clear(self):
        """Clear all entries."""
        self.entries.clear()

    def export_to_file(self, file_path: str):
        """Export all entries to a JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.get_all_entries(), f, ensure_ascii=False, indent=2)


# Global logger instance
api_logger = APILogger()

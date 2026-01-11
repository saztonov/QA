"""Process Timeline Widget for displaying API operations in real-time.

This widget shows a vertical timeline of all operations (planning, answering, etc.)
with details about models used, files sent, tokens consumed, and timing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class EventType(Enum):
    """Types of timeline events."""
    PLANNING_START = "planning_start"
    PLANNING_COMPLETE = "planning_complete"
    EVIDENCE_LOAD = "evidence_load"
    ANSWERING_START = "answering_start"
    ANSWERING_COMPLETE = "answering_complete"
    FOLLOWUP = "followup"
    SUMMARIZATION = "summarization"
    INDEXING_START = "indexing_start"
    INDEXING_PROGRESS = "indexing_progress"
    INDEXING_COMPLETE = "indexing_complete"
    ERROR = "error"
    USER_MESSAGE = "user_message"
    MODEL_MESSAGE = "model_message"


# Color scheme for different event types
EVENT_COLORS = {
    EventType.PLANNING_START: "#2196F3",      # Blue
    EventType.PLANNING_COMPLETE: "#4CAF50",   # Green
    EventType.EVIDENCE_LOAD: "#FF9800",       # Orange
    EventType.ANSWERING_START: "#9C27B0",     # Purple
    EventType.ANSWERING_COMPLETE: "#4CAF50",  # Green
    EventType.FOLLOWUP: "#FFC107",            # Amber
    EventType.SUMMARIZATION: "#00BCD4",       # Cyan
    EventType.INDEXING_START: "#795548",      # Brown
    EventType.INDEXING_PROGRESS: "#795548",   # Brown
    EventType.INDEXING_COMPLETE: "#4CAF50",   # Green
    EventType.ERROR: "#F44336",               # Red
    EventType.USER_MESSAGE: "#0d47a1",        # Dark Blue
    EventType.MODEL_MESSAGE: "#37474f",       # Grey
}

# Labels for event types
EVENT_LABELS = {
    EventType.PLANNING_START: "Planning",
    EventType.PLANNING_COMPLETE: "Plan Ready",
    EventType.EVIDENCE_LOAD: "Loading Evidence",
    EventType.ANSWERING_START: "Generating Answer",
    EventType.ANSWERING_COMPLETE: "Answer Ready",
    EventType.FOLLOWUP: "Followup Request",
    EventType.SUMMARIZATION: "Summarizing",
    EventType.INDEXING_START: "Indexing Started",
    EventType.INDEXING_PROGRESS: "Indexing...",
    EventType.INDEXING_COMPLETE: "Indexing Complete",
    EventType.ERROR: "Error",
    EventType.USER_MESSAGE: "User",
    EventType.MODEL_MESSAGE: "Model",
}


@dataclass
class ProcessEvent:
    """Represents a single event in the timeline."""
    timestamp: datetime
    event_type: EventType
    title: str
    model: Optional[str] = None  # "Flash" / "Pro" / None
    status: str = "in_progress"  # in_progress, completed, error
    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    files_requested: List[str] = field(default_factory=list)
    files_sent: List[str] = field(default_factory=list)
    details: Optional[str] = None
    error_message: Optional[str] = None
    # For expandable content
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    response_raw: Optional[str] = None


class ProcessEventWidget(QFrame):
    """Widget representing a single event in the timeline."""

    expanded = Signal(bool)
    clicked = Signal(object)  # Emits the ProcessEvent

    def __init__(self, event: ProcessEvent, parent=None):
        super().__init__(parent)
        self.event = event
        self._is_expanded = False
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI for this event."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Get color for this event type
        color = EVENT_COLORS.get(self.event.event_type, "#555")
        status_color = {
            "in_progress": "#FFC107",  # Amber
            "completed": "#4CAF50",    # Green
            "error": "#F44336",        # Red
        }.get(self.event.status, "#888")

        self.setStyleSheet(f"""
            ProcessEventWidget {{
                background-color: #2d2d2d;
                border-left: 3px solid {status_color};
                border-radius: 4px;
                margin: 2px 4px;
                padding: 0px;
            }}
            ProcessEventWidget:hover {{
                background-color: #3d3d3d;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header row: timestamp, type badge, model badge
        header = QHBoxLayout()
        header.setSpacing(6)

        # Timestamp
        time_str = self.event.timestamp.strftime("%H:%M:%S")
        time_label = QLabel(time_str)
        time_label.setStyleSheet("color: #888; font-size: 10px;")
        time_label.setFixedWidth(55)
        header.addWidget(time_label)

        # Event type badge
        type_label = EVENT_LABELS.get(self.event.event_type, str(self.event.event_type.value))
        badge = QLabel(type_label)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        header.addWidget(badge)

        # Model badge (if applicable)
        if self.event.model:
            model_color = "#2196F3" if self.event.model == "Flash" else "#9C27B0"
            model_badge = QLabel(self.event.model)
            model_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {model_color};
                    color: white;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
            header.addWidget(model_badge)

        header.addStretch()

        # Duration (if available)
        if self.event.duration_ms > 0:
            duration_str = self._format_duration(self.event.duration_ms)
            duration_label = QLabel(duration_str)
            duration_label.setStyleSheet("color: #aaa; font-size: 10px;")
            header.addWidget(duration_label)

        layout.addLayout(header)

        # Title
        title_label = QLabel(self.event.title)
        title_label.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Details row (tokens, files)
        if self.event.input_tokens > 0 or self.event.output_tokens > 0 or self.event.files_sent:
            details_layout = QHBoxLayout()
            details_layout.setSpacing(12)

            # Tokens
            if self.event.input_tokens > 0 or self.event.output_tokens > 0:
                tokens_text = f"in:{self.event.input_tokens:,}"
                if self.event.output_tokens > 0:
                    tokens_text += f" out:{self.event.output_tokens:,}"
                tokens_label = QLabel(tokens_text)
                tokens_label.setStyleSheet("color: #4fc3f7; font-size: 10px;")
                details_layout.addWidget(tokens_label)

            # Files
            if self.event.files_sent:
                files_text = f"{len(self.event.files_sent)} file(s)"
                files_label = QLabel(files_text)
                files_label.setStyleSheet("color: #ff9800; font-size: 10px;")
                details_layout.addWidget(files_label)

            details_layout.addStretch()
            layout.addLayout(details_layout)

        # Additional details (if any)
        if self.event.details:
            details_label = QLabel(self.event.details)
            details_label.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
            details_label.setWordWrap(True)
            layout.addWidget(details_label)

        # Error message (if error)
        if self.event.error_message:
            error_label = QLabel(self.event.error_message)
            error_label.setStyleSheet("color: #f44336; font-size: 10px;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

        # Expanded content (initially hidden)
        self.expanded_frame = QFrame()
        self.expanded_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 4px;
                margin-top: 4px;
            }
        """)
        self.expanded_frame.setVisible(False)
        expanded_layout = QVBoxLayout(self.expanded_frame)
        expanded_layout.setContentsMargins(6, 6, 6, 6)
        expanded_layout.setSpacing(4)

        # Add expandable content
        if self.event.system_prompt:
            sp_header = QLabel("System Prompt:")
            sp_header.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
            expanded_layout.addWidget(sp_header)

            sp_text = QLabel(self.event.system_prompt[:500] + "..." if len(self.event.system_prompt) > 500 else self.event.system_prompt)
            sp_text.setStyleSheet("color: #aaa; font-size: 10px;")
            sp_text.setWordWrap(True)
            sp_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            expanded_layout.addWidget(sp_text)

        if self.event.user_prompt:
            up_header = QLabel("User Prompt:")
            up_header.setStyleSheet("color: #81c784; font-size: 10px; font-weight: bold;")
            expanded_layout.addWidget(up_header)

            up_text = QLabel(self.event.user_prompt[:500] + "..." if len(self.event.user_prompt) > 500 else self.event.user_prompt)
            up_text.setStyleSheet("color: #aaa; font-size: 10px;")
            up_text.setWordWrap(True)
            up_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            expanded_layout.addWidget(up_text)

        if self.event.response_raw:
            resp_header = QLabel("Response:")
            resp_header.setStyleSheet("color: #ce93d8; font-size: 10px; font-weight: bold;")
            expanded_layout.addWidget(resp_header)

            resp_text = QLabel(self.event.response_raw[:500] + "..." if len(self.event.response_raw) > 500 else self.event.response_raw)
            resp_text.setStyleSheet("color: #aaa; font-size: 10px;")
            resp_text.setWordWrap(True)
            resp_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            expanded_layout.addWidget(resp_text)

        if self.event.files_sent:
            files_header = QLabel("Files Sent:")
            files_header.setStyleSheet("color: #ff9800; font-size: 10px; font-weight: bold;")
            expanded_layout.addWidget(files_header)

            for f in self.event.files_sent[:5]:
                file_label = QLabel(f"  - {os.path.basename(f)}")
                file_label.setStyleSheet("color: #aaa; font-size: 10px;")
                expanded_layout.addWidget(file_label)

        layout.addWidget(self.expanded_frame)

    def mousePressEvent(self, event):
        """Toggle expanded state on click."""
        self._is_expanded = not self._is_expanded
        self.expanded_frame.setVisible(self._is_expanded)
        self.expanded.emit(self._is_expanded)
        self.clicked.emit(self.event)

    def update_event(self, **kwargs):
        """Update the event with new data."""
        for key, value in kwargs.items():
            if hasattr(self.event, key):
                setattr(self.event, key, value)
        # Rebuild UI
        # For simplicity, just update status color
        if "status" in kwargs:
            status_color = {
                "in_progress": "#FFC107",
                "completed": "#4CAF50",
                "error": "#F44336",
            }.get(self.event.status, "#888")
            self.setStyleSheet(f"""
                ProcessEventWidget {{
                    background-color: #2d2d2d;
                    border-left: 3px solid {status_color};
                    border-radius: 4px;
                    margin: 2px 4px;
                }}
                ProcessEventWidget:hover {{
                    background-color: #3d3d3d;
                }}
            """)

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


class ProcessTimelineWidget(QWidget):
    """Main widget displaying the process timeline."""

    event_clicked = Signal(object)  # Emits ProcessEvent when clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events: List[ProcessEvent] = []
        self._event_widgets: List[ProcessEventWidget] = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup the main UI."""
        self.setStyleSheet("""
            ProcessTimelineWidget {
                background-color: #1e1e1e;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)

        title = QLabel("Process Timeline")
        title.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 12px;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: none;
                padding: 4px 12px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        clear_btn.clicked.connect(self.clear)
        header_layout.addWidget(clear_btn)

        layout.addWidget(header_frame)

        # Scroll area for events
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e1e;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.events_container = QWidget()
        self.events_container.setStyleSheet("background-color: #1e1e1e;")
        self.events_layout = QVBoxLayout(self.events_container)
        self.events_layout.setContentsMargins(4, 4, 4, 4)
        self.events_layout.setSpacing(4)
        self.events_layout.addStretch()

        self.scroll_area.setWidget(self.events_container)
        layout.addWidget(self.scroll_area, 1)

        # Stats footer
        self.stats_frame = QFrame()
        self.stats_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-top: 1px solid #3c3c3c;
            }
        """)
        stats_layout = QHBoxLayout(self.stats_frame)
        stats_layout.setContentsMargins(10, 6, 10, 6)

        self.stats_label = QLabel("Events: 0 | Total tokens: 0")
        self.stats_label.setStyleSheet("color: #888; font-size: 10px;")
        stats_layout.addWidget(self.stats_label)

        layout.addWidget(self.stats_frame)

    def add_event(self, event: ProcessEvent) -> ProcessEventWidget:
        """Add a new event to the timeline.

        Args:
            event: The ProcessEvent to add.

        Returns:
            The created ProcessEventWidget.
        """
        self.events.append(event)

        # Create widget
        event_widget = ProcessEventWidget(event)
        event_widget.clicked.connect(self._on_event_clicked)
        self._event_widgets.append(event_widget)

        # Insert before stretch
        count = self.events_layout.count()
        self.events_layout.insertWidget(count - 1, event_widget)

        # Update stats
        self._update_stats()

        # Auto-scroll to bottom
        self._scroll_to_bottom()

        return event_widget

    def update_last_event(self, **kwargs) -> None:
        """Update the last event with new data.

        Args:
            **kwargs: Fields to update (status, duration_ms, input_tokens, etc.)
        """
        if not self._event_widgets:
            return

        last_widget = self._event_widgets[-1]
        last_widget.update_event(**kwargs)

        # Update the event dataclass too
        for key, value in kwargs.items():
            if hasattr(self.events[-1], key):
                setattr(self.events[-1], key, value)

        self._update_stats()

    def clear(self) -> None:
        """Clear all events from the timeline."""
        # Remove all widgets
        for widget in self._event_widgets:
            self.events_layout.removeWidget(widget)
            widget.deleteLater()

        self.events.clear()
        self._event_widgets.clear()
        self._update_stats()

    def get_total_tokens(self) -> tuple[int, int]:
        """Get total input and output tokens across all events.

        Returns:
            Tuple of (total_input_tokens, total_output_tokens)
        """
        total_input = sum(e.input_tokens for e in self.events)
        total_output = sum(e.output_tokens for e in self.events)
        return total_input, total_output

    def _update_stats(self) -> None:
        """Update the statistics label."""
        total_in, total_out = self.get_total_tokens()
        total = total_in + total_out
        self.stats_label.setText(
            f"Events: {len(self.events)} | "
            f"Tokens: in {total_in:,} + out {total_out:,} = {total:,}"
        )

    def _scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the timeline."""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_event_clicked(self, event: ProcessEvent) -> None:
        """Handle event widget click."""
        self.event_clicked.emit(event)


# Convenience function for creating events from usage dict
def create_event_from_usage(
    event_type: EventType,
    title: str,
    usage: dict,
    status: str = "completed"
) -> ProcessEvent:
    """Create a ProcessEvent from a usage dictionary.

    Args:
        event_type: Type of event.
        title: Title for the event.
        usage: Usage dictionary from planner/answerer.
        status: Event status.

    Returns:
        ProcessEvent instance.
    """
    model = usage.get("model", "")
    if "flash" in model.lower():
        model_short = "Flash"
    elif "pro" in model.lower():
        model_short = "Pro"
    else:
        model_short = None

    return ProcessEvent(
        timestamp=datetime.now(),
        event_type=event_type,
        title=title,
        model=model_short,
        status=status,
        duration_ms=usage.get("duration_ms", 0.0),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        files_sent=[f.get("path", f.get("name", "unknown")) for f in usage.get("files_info", [])] +
                   [f.get("path", f.get("name", "unknown")) for f in usage.get("images_info", [])],
        system_prompt=usage.get("system_prompt_full"),
        user_prompt=usage.get("user_prompt_full"),
        response_raw=usage.get("response_raw"),
    )

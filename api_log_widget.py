"""API Log widget for displaying JSON logs of model interactions."""

import json
import os
from datetime import datetime
from typing import Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QTextDocument


class JsonSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for JSON content."""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._formats = {}
        self._setup_formats()

    def _setup_formats(self):
        """Setup text formats for different JSON elements."""
        # Keys
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#9cdcfe"))
        self._formats["key"] = key_format

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))
        self._formats["string"] = string_format

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#b5cea8"))
        self._formats["number"] = number_format

        # Booleans and null
        bool_format = QTextCharFormat()
        bool_format.setForeground(QColor("#569cd6"))
        self._formats["bool"] = bool_format

        # Brackets
        bracket_format = QTextCharFormat()
        bracket_format.setForeground(QColor("#ffd700"))
        self._formats["bracket"] = bracket_format

    def highlightBlock(self, text: str):
        """Highlight a block of text."""
        import re

        # Highlight keys (before colon)
        for match in re.finditer(r'"([^"\\]|\\.)*"\s*:', text):
            self.setFormat(match.start(), match.end() - match.start() - 1, self._formats["key"])

        # Highlight string values
        for match in re.finditer(r':\s*"([^"\\]|\\.)*"', text):
            start = text.find('"', match.start())
            self.setFormat(start, match.end() - start, self._formats["string"])

        # Highlight numbers
        for match in re.finditer(r':\s*(-?\d+\.?\d*)', text):
            start = match.start() + len(match.group(0)) - len(match.group(1))
            self.setFormat(start, len(match.group(1)), self._formats["number"])

        # Highlight booleans and null
        for match in re.finditer(r'\b(true|false|null)\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats["bool"])

        # Highlight brackets
        for match in re.finditer(r'[\[\]{}]', text):
            self.setFormat(match.start(), 1, self._formats["bracket"])


class ApiLogWidget(QWidget):
    """Widget for displaying API interaction logs in JSON format."""

    def __init__(self):
        super().__init__()
        self.log_entries: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
                padding: 8px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)

        title = QLabel("API Log")
        title.setStyleSheet("""
            QLabel {
                color: #4fc3f7;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                padding: 4px 12px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #007acc;
            }
        """)
        clear_btn.clicked.connect(self.clear_log)
        header_layout.addWidget(clear_btn)

        # Download button
        download_btn = QPushButton("Download JSON")
        download_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                padding: 4px 12px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        download_btn.clicked.connect(self.download_log)
        header_layout.addWidget(download_btn)

        layout.addWidget(header)

        # Log display area
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 10))
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 10px;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Apply syntax highlighting
        self.highlighter = JsonSyntaxHighlighter(self.log_display.document())

        layout.addWidget(self.log_display)

        # Stats footer
        self.stats_label = QLabel("Entries: 0")
        self.stats_label.setStyleSheet("""
            QLabel {
                background-color: #252526;
                color: #888;
                padding: 6px 10px;
                font-size: 11px;
                border-top: 1px solid #3c3c3c;
            }
        """)
        layout.addWidget(self.stats_label)

    def add_log_entry(self, entry_type: str, data: dict) -> None:
        """Add a new log entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "data": data
        }
        self.log_entries.append(entry)
        self._update_display()

    def log_request(self, text: str, images: list[str] = None, files: list[str] = None, model: str = None) -> None:
        """Log an outgoing request to the model."""
        data = {
            "model": model,
            "message": text[:500] + "..." if len(text) > 500 else text,
            "message_length": len(text),
        }
        if images:
            data["images"] = [os.path.basename(p) for p in images]
            data["images_count"] = len(images)
        if files:
            data["files"] = [os.path.basename(p) for p in files]
            data["files_count"] = len(files)

        self.add_log_entry("REQUEST", data)

    def log_response(self, text: str, needs_blocks: bool = False, needs_images: bool = False,
                     requested_blocks: list = None, requested_images: list = None,
                     thoughts: str = None) -> None:
        """Log an incoming response from the model."""
        data = {
            "response": text[:1000] + "..." if len(text) > 1000 else text,
            "response_length": len(text),
            "needs_blocks": needs_blocks,
            "needs_images": needs_images,
            "has_thoughts": thoughts is not None,
        }
        if thoughts:
            data["thoughts_preview"] = thoughts[:500] + "..." if len(thoughts) > 500 else thoughts
            data["thoughts_length"] = len(thoughts)
        if requested_blocks:
            data["requested_blocks"] = [b.block_id for b in requested_blocks]
        if requested_images:
            data["requested_images"] = [i.filename for i in requested_images]

        self.add_log_entry("RESPONSE", data)

    def log_files_sent(self, file_paths: list[str], context: str = "") -> None:
        """Log files being sent to the model."""
        data = {
            "files": [os.path.basename(p) for p in file_paths],
            "files_count": len(file_paths),
            "file_sizes": {os.path.basename(p): os.path.getsize(p) for p in file_paths if os.path.exists(p)},
            "context": context[:200] + "..." if len(context) > 200 else context,
        }
        self.add_log_entry("FILES_SENT", data)

    def log_images_sent(self, image_paths: list[str], context: str = "") -> None:
        """Log images being sent to the model."""
        data = {
            "images": [os.path.basename(p) for p in image_paths],
            "images_count": len(image_paths),
            "context": context[:200] + "..." if len(context) > 200 else context,
        }
        self.add_log_entry("IMAGES_SENT", data)

    def log_system_prompt(self, prompt: str) -> None:
        """Log system prompt being set."""
        data = {
            "prompt_length": len(prompt) if prompt else 0,
            "prompt_preview": prompt[:500] + "..." if prompt and len(prompt) > 500 else prompt,
        }
        self.add_log_entry("SYSTEM_PROMPT", data)

    def log_model_change(self, model: str) -> None:
        """Log model change."""
        self.add_log_entry("MODEL_CHANGE", {"model": model})

    def log_new_chat(self) -> None:
        """Log new chat started."""
        self.add_log_entry("NEW_CHAT", {"message": "New chat session started"})

    def log_error(self, error: str) -> None:
        """Log an error."""
        self.add_log_entry("ERROR", {"error": error})

    def log_document_loaded(self, document_path: str, blocks_count: int) -> None:
        """Log document loaded."""
        data = {
            "document": os.path.basename(document_path),
            "blocks_count": blocks_count,
        }
        self.add_log_entry("DOCUMENT_LOADED", data)

    def log_crops_loaded(self, crops_dir: str) -> None:
        """Log crops folder loaded."""
        data = {
            "crops_dir": os.path.basename(crops_dir),
        }
        self.add_log_entry("CROPS_LOADED", data)

    def _update_display(self) -> None:
        """Update the display with current log entries."""
        # Format as pretty JSON
        json_str = json.dumps(self.log_entries, indent=2, ensure_ascii=False)
        self.log_display.setPlainText(json_str)

        # Scroll to bottom
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Update stats
        self.stats_label.setText(f"Entries: {len(self.log_entries)}")

    def clear_log(self) -> None:
        """Clear all log entries."""
        self.log_entries.clear()
        self._update_display()

    def download_log(self) -> None:
        """Download log as JSON file."""
        if not self.log_entries:
            return

        filename = f"api_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save API Log",
            filename,
            "JSON Files (*.json)"
        )

        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.log_entries, f, indent=2, ensure_ascii=False)

    def get_log_data(self) -> list[dict]:
        """Get all log entries."""
        return self.log_entries.copy()

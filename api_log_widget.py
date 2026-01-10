"""API Log widget for displaying JSON logs of model interactions.

Features:
- JSON syntax highlighting
- Auto-rotation at MAX_LOG_ENTRIES to prevent UI slowdown
- Export to file functionality
"""

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
    """Widget for displaying API interaction logs in JSON format.

    Features:
    - Auto-rotation: When log exceeds MAX_LOG_ENTRIES, oldest entries are removed
    - Rotated entries are stored in _rotated_count for statistics
    """

    MAX_LOG_ENTRIES = 1000  # Limit to prevent UI slowdown
    ROTATION_BATCH_SIZE = 100  # Number of entries to remove on rotation

    def __init__(self):
        super().__init__()
        self.log_entries: list[dict] = []
        self._rotated_count = 0  # Track total rotated entries
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
        """Add a new log entry with automatic rotation.

        When log exceeds MAX_LOG_ENTRIES, oldest entries are removed
        in batches of ROTATION_BATCH_SIZE to prevent frequent rotations.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "data": data
        }
        self.log_entries.append(entry)

        # Perform rotation if exceeded limit
        if len(self.log_entries) > self.MAX_LOG_ENTRIES:
            self._rotate_log()

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

    def log_plan_request(
        self,
        question: str,
        model: str = "gemini-3-flash-preview",
        context_stats: dict = None,
    ) -> None:
        """Log a planning request to Flash model.

        Args:
            question: The user's question.
            model: Model name being used.
            context_stats: Optional context statistics from planner.
        """
        data = {
            "model": model,
            "question": question[:500] + "..." if len(question) > 500 else question,
            "question_length": len(question),
            "stage": "planning",
        }

        # Add context stats if provided
        if context_stats:
            data["context"] = {
                "system_prompt_length": context_stats.get("system_prompt_length", 0),
                "estimated_tokens": context_stats.get("estimated_tokens", 0),
                "conversation_turns": context_stats.get("conversation_turns", 0),
                "has_summary": context_stats.get("has_summary", False),
            }

        self.add_log_entry("PLAN_REQUEST", data)

    def log_plan_response(self, plan_data: dict, raw_json: str = None, usage: dict = None) -> None:
        """Log planning response from Flash model.

        Args:
            plan_data: Dictionary with plan details (decision, reasoning, blocks, etc.)
            raw_json: Optional raw JSON response for debugging.
            usage: Optional usage metadata from API (tokens).
        """
        data = {
            "decision": plan_data.get("decision", "unknown"),
            "reasoning": plan_data.get("reasoning", "")[:300],
            "requested_blocks_count": len(plan_data.get("requested_blocks", [])),
            "requested_rois_count": len(plan_data.get("requested_rois", [])),
            "user_requests_count": len(plan_data.get("user_requests", [])),
            "stage": "planning",
        }

        # Add usage metadata if available
        if usage:
            data["usage"] = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "thoughts_tokens": usage.get("thoughts_tokens", 0),
            }

        # Add block details if present
        if plan_data.get("requested_blocks"):
            data["requested_blocks"] = [
                {
                    "block_id": b.get("block_id"),
                    "priority": b.get("priority"),
                    "reason": b.get("reason", "")[:100]
                }
                for b in plan_data["requested_blocks"][:5]  # Limit to 5 for readability
            ]

        # Add ROI details if present
        if plan_data.get("requested_rois"):
            data["requested_rois"] = [
                {
                    "block_id": r.get("block_id"),
                    "page": r.get("page"),
                    "dpi": r.get("dpi"),
                }
                for r in plan_data["requested_rois"][:3]  # Limit to 3
            ]

        # Add user requests if present
        if plan_data.get("user_requests"):
            data["user_requests"] = [
                {
                    "kind": u.get("kind"),
                    "text": u.get("text", "")[:100]
                }
                for u in plan_data["user_requests"][:3]
            ]

        if raw_json:
            data["raw_json_length"] = len(raw_json)

        self.add_log_entry("PLAN_RESPONSE", data)

    def log_rois_rendered(self, rois_info: list[dict], crop_paths: list[str]) -> None:
        """Log ROI rendering and cropping.

        Args:
            rois_info: List of ROI details [{block_id, page, bbox, dpi}, ...]
            crop_paths: List of paths to rendered crop files.
        """
        data = {
            "rois_count": len(rois_info),
            "crops_count": len(crop_paths),
            "rois": [
                {
                    "block_id": r.get("block_id"),
                    "page": r.get("page"),
                    "dpi": r.get("dpi"),
                    "bbox": r.get("bbox"),
                }
                for r in rois_info[:5]  # Limit to 5 for readability
            ],
            "crop_files": [os.path.basename(p) for p in crop_paths[:5]],
            "total_crops_size_kb": sum(
                os.path.getsize(p) for p in crop_paths if os.path.exists(p)
            ) // 1024,
        }
        self.add_log_entry("ROIS_RENDERED", data)

    def log_evidence_sent(self, evidence_paths: list[str], evidence_type: str = "crops") -> None:
        """Log evidence images being sent to model.

        Args:
            evidence_paths: List of paths to evidence images.
            evidence_type: Type of evidence (crops, full_pages, mixed).
        """
        data = {
            "evidence_type": evidence_type,
            "files_count": len(evidence_paths),
            "files": [os.path.basename(p) for p in evidence_paths[:10]],
            "total_size_kb": sum(
                os.path.getsize(p) for p in evidence_paths if os.path.exists(p)
            ) // 1024,
        }
        self.add_log_entry("EVIDENCE_SENT", data)

    def log_answer_request(
        self,
        question: str,
        model: str = "gemini-3-pro-preview",
        iteration: int = 1,
        images_count: int = 0,
        files_count: int = 0,
        context_stats: dict = None,
    ) -> None:
        """Log an answer request to Pro model.

        Args:
            question: The user's question.
            model: Model name being used.
            iteration: Current iteration number.
            images_count: Number of images being sent.
            files_count: Number of files being sent.
            context_stats: Optional context statistics from answerer.
        """
        data = {
            "model": model,
            "question": question[:500] + "..." if len(question) > 500 else question,
            "question_length": len(question),
            "iteration": iteration,
            "images_count": images_count,
            "files_count": files_count,
            "stage": "answering",
        }

        # Add context stats if provided
        if context_stats:
            data["context"] = {
                "system_prompt_length": context_stats.get("system_prompt_length", 0),
                "estimated_text_tokens": context_stats.get("estimated_text_tokens", 0),
                "media_resolution": context_stats.get("media_resolution", ""),
                "conversation_turns": context_stats.get("conversation_turns", 0),
                "total_media_size_kb": context_stats.get("total_media_size_kb", 0),
            }
            # Add media file details if present
            if context_stats.get("media_files"):
                data["media_files"] = context_stats["media_files"][:10]  # Limit to 10

        self.add_log_entry("ANSWER_REQUEST", data)

    def log_answer_response(
        self,
        answer_data: dict,
        raw_json: str = None,
        iteration: int = 1,
        usage: dict = None
    ) -> None:
        """Log answer response from Pro model.

        Args:
            answer_data: Dictionary with answer details.
            raw_json: Optional raw JSON response.
            iteration: Current iteration number.
            usage: Optional usage metadata from API (tokens).
        """
        data = {
            "iteration": iteration,
            "confidence": answer_data.get("confidence", "unknown"),
            "answer_length": len(answer_data.get("answer_markdown", "")),
            "answer_preview": answer_data.get("answer_markdown", "")[:300] + "...",
            "citations_count": len(answer_data.get("citations", [])),
            "needs_more_evidence": answer_data.get("needs_more_evidence", False),
            "followup_blocks_count": len(answer_data.get("followup_blocks", [])),
            "followup_rois_count": len(answer_data.get("followup_rois", [])),
            "stage": "answering",
        }

        # Add usage metadata if available
        if usage:
            data["usage"] = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "thoughts_tokens": usage.get("thoughts_tokens", 0),
            }
            if usage.get("thought_text"):
                data["has_thoughts"] = True
            if usage.get("thought_signature"):
                data["has_thought_signature"] = True

        # Add citation details
        if answer_data.get("citations"):
            data["citations"] = [
                {
                    "kind": c.get("kind"),
                    "id": c.get("id"),
                    "page": c.get("page"),
                }
                for c in answer_data["citations"][:5]
            ]

        # Add followup details if needs more evidence
        if answer_data.get("needs_more_evidence"):
            if answer_data.get("followup_blocks"):
                data["followup_blocks"] = [
                    {"block_id": b.get("block_id"), "reason": b.get("reason", "")[:50]}
                    for b in answer_data["followup_blocks"][:3]
                ]
            if answer_data.get("followup_rois"):
                data["followup_rois"] = [
                    {"block_id": r.get("block_id"), "page": r.get("page")}
                    for r in answer_data["followup_rois"][:3]
                ]

        if raw_json:
            data["raw_json_length"] = len(raw_json)

        self.add_log_entry("ANSWER_RESPONSE", data)

    def log_summary_update(
        self,
        old_summary_length: int,
        new_summary_length: int,
        turns_summarized: int,
    ) -> None:
        """Log conversation summary update.

        Args:
            old_summary_length: Length of previous summary.
            new_summary_length: Length of new summary.
            turns_summarized: Number of turns that were summarized.
        """
        data = {
            "old_summary_length": old_summary_length,
            "new_summary_length": new_summary_length,
            "turns_summarized": turns_summarized,
            "model": "gemini-3-flash-preview",
        }
        self.add_log_entry("SUMMARY_UPDATE", data)

    def log_conversation_memory_state(self, memory_stats: dict) -> None:
        """Log current state of conversation memory.

        Args:
            memory_stats: Statistics from ConversationMemory.get_stats().
        """
        data = {
            "turns_count": memory_stats.get("turns_count", 0),
            "max_turns": memory_stats.get("max_turns", 0),
            "summary_length": memory_stats.get("summary_length", 0),
            "total_text_length": memory_stats.get("total_text_length", 0),
            "estimated_tokens": memory_stats.get("estimated_tokens", 0),
            "has_summary": memory_stats.get("has_summary", False),
        }
        self.add_log_entry("CONVERSATION_MEMORY", data)

    def log_indexing_start(self, crops_dir: str, total_blocks: int) -> None:
        """Log start of block indexing.

        Args:
            crops_dir: Directory being indexed.
            total_blocks: Total number of blocks to index.
        """
        data = {
            "crops_dir": os.path.basename(crops_dir),
            "total_blocks": total_blocks,
            "status": "started",
        }
        self.add_log_entry("INDEXING_START", data)

    def log_indexing_progress(
        self,
        indexed: int,
        total: int,
        current_blocks: str,
    ) -> None:
        """Log indexing progress.

        Args:
            indexed: Number of blocks indexed so far.
            total: Total number of blocks.
            current_blocks: IDs of blocks being indexed.
        """
        data = {
            "indexed": indexed,
            "total": total,
            "progress_percent": round(indexed / total * 100, 1) if total > 0 else 0,
            "current": current_blocks,
        }
        self.add_log_entry("INDEXING_PROGRESS", data)

    def log_indexing_error(self, block_ids: str, error: str) -> None:
        """Log indexing error for specific blocks.

        Args:
            block_ids: IDs of blocks that failed.
            error: Error message.
        """
        data = {
            "block_ids": block_ids,
            "error": error,
        }
        self.add_log_entry("INDEXING_ERROR", data)

    def log_indexing_complete(
        self,
        total_blocks: int,
        indexed_blocks: int,
        failed_blocks: int,
        output_path: str,
    ) -> None:
        """Log completion of block indexing.

        Args:
            total_blocks: Total number of blocks.
            indexed_blocks: Number successfully indexed.
            failed_blocks: Number that failed.
            output_path: Path where index was saved.
        """
        data = {
            "total_blocks": total_blocks,
            "indexed_blocks": indexed_blocks,
            "failed_blocks": failed_blocks,
            "success_rate": round(indexed_blocks / total_blocks * 100, 1) if total_blocks > 0 else 0,
            "output_path": os.path.basename(output_path),
            "status": "complete",
        }
        self.add_log_entry("INDEXING_COMPLETE", data)

    def _rotate_log(self) -> None:
        """Remove oldest entries when log exceeds MAX_LOG_ENTRIES.

        Removes ROTATION_BATCH_SIZE entries at once to avoid frequent rotations.
        Adds a rotation marker entry to indicate when rotation occurred.
        """
        to_remove = self.ROTATION_BATCH_SIZE
        self._rotated_count += to_remove

        # Remove oldest entries
        del self.log_entries[:to_remove]

        # Add rotation marker
        rotation_marker = {
            "timestamp": datetime.now().isoformat(),
            "type": "LOG_ROTATION",
            "data": {
                "message": f"Removed {to_remove} oldest entries",
                "total_rotated": self._rotated_count,
                "remaining_entries": len(self.log_entries),
            }
        }
        self.log_entries.insert(0, rotation_marker)

    def _update_display(self) -> None:
        """Update the display with current log entries."""
        # Format as pretty JSON
        json_str = json.dumps(self.log_entries, indent=2, ensure_ascii=False)
        self.log_display.setPlainText(json_str)

        # Scroll to bottom
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Update stats with rotation info
        stats_text = f"Entries: {len(self.log_entries)}"
        if self._rotated_count > 0:
            stats_text += f" ({self._rotated_count} rotated)"
        self.stats_label.setText(stats_text)

    def clear_log(self) -> None:
        """Clear all log entries and reset rotation counter."""
        self.log_entries.clear()
        self._rotated_count = 0
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

"""Chat widget component for Qt6."""

import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QLabel,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QFont

from image_viewer import ImageViewer


class ImageThumbnail(QLabel):
    """Thumbnail widget for displaying images."""

    clicked = Signal(str)

    def __init__(self, image_path: str, size: int = 100):
        super().__init__()
        self.image_path = image_path
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            scaled = pixmap.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        else:
            self.setText("?")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet("""
            QLabel {
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                background: #2d2d2d;
            }
            QLabel:hover {
                border-color: #007acc;
            }
        """)

    def mousePressEvent(self, event):
        self.clicked.emit(self.image_path)


class MessageBubble(QFrame):
    """Message bubble widget."""

    thumbnail_clicked = Signal(str)  # Emits image path when any thumbnail is clicked

    def __init__(self, text: str, is_user: bool, images: Optional[list[str]] = None):
        super().__init__()
        self.is_user = is_user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Images section
        if images:
            images_layout = QHBoxLayout()
            images_layout.setSpacing(4)
            for img_path in images[:5]:  # Limit to 5 thumbnails
                thumb = ImageThumbnail(img_path, 60)
                thumb.clicked.connect(self.thumbnail_clicked.emit)
                images_layout.addWidget(thumb)
            images_layout.addStretch()
            layout.addLayout(images_layout)

        # Text content
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        layout.addWidget(text_label)

        # Styling - dark theme
        if is_user:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #0d47a1;
                    border-radius: 12px;
                    margin-left: 50px;
                }
                QLabel {
                    color: #e3f2fd;
                }
            """)
        else:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #37474f;
                    border-radius: 12px;
                    margin-right: 50px;
                }
                QLabel {
                    color: #eceff1;
                }
            """)


class ChatWidget(QWidget):
    """Main chat widget."""

    message_sent = Signal(str)
    roi_selected = Signal(str, float, float, float, float)  # image_path, x0, y0, x1, y1

    def __init__(self):
        super().__init__()
        self._all_images: list[str] = []  # Track all images for navigation
        self._image_viewer: Optional[ImageViewer] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Dark theme for main widget
        self.setStyleSheet("""
            ChatWidget {
                background-color: #1e1e1e;
            }
        """)

        # Chat history area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e1e;
                border: none;
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

        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background-color: #1e1e1e;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(10, 10, 10, 10)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area, 1)

        # Input area - dark theme
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-top: 1px solid #3c3c3c;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 10, 10, 10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введите сообщение...")
        self.input_field.setMinimumHeight(40)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 20px;
                padding: 8px 16px;
                font-size: 14px;
                color: #e0e0e0;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QLineEdit::placeholder {
                color: #888;
            }
        """)
        self.input_field.returnPressed.connect(self._on_send)

        self.send_button = QPushButton("Send")
        self.send_button.setMinimumHeight(40)
        self.send_button.setMinimumWidth(80)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:disabled {
                background-color: #455a64;
                color: #90a4ae;
            }
        """)
        self.send_button.clicked.connect(self._on_send)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)

        layout.addWidget(input_frame)

    def _on_send(self):
        """Handle send button click."""
        text = self.input_field.text().strip()
        if text:
            self.input_field.clear()
            self.message_sent.emit(text)

    def add_user_message(self, text: str, images: Optional[list[str]] = None):
        """Add a user message to the chat."""
        # Remove stretch before adding
        self._remove_stretch()

        bubble = MessageBubble(text, is_user=True, images=images)
        bubble.thumbnail_clicked.connect(self._open_image_viewer)
        self.messages_layout.addWidget(bubble)

        # Track images for navigation
        if images:
            for img in images:
                if img not in self._all_images:
                    self._all_images.append(img)

        # Add stretch back
        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def add_model_message(self, text: str, thoughts: Optional[str] = None, images: Optional[list[str]] = None):
        """Add a model message to the chat."""
        self._remove_stretch()

        # Show thoughts first if available
        if thoughts:
            self._add_thoughts_bubble(thoughts)

        bubble = MessageBubble(text, is_user=False, images=images)
        bubble.thumbnail_clicked.connect(self._open_image_viewer)
        self.messages_layout.addWidget(bubble)

        # Track images for navigation
        if images:
            for img in images:
                if img not in self._all_images:
                    self._all_images.append(img)

        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def _add_thoughts_bubble(self, thoughts: str):
        """Add a thoughts bubble (collapsible)."""
        thoughts_frame = QFrame()
        thoughts_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a3d;
                border: 1px solid #4a4a6a;
                border-radius: 8px;
                margin-right: 50px;
                margin-bottom: 4px;
            }
        """)

        thoughts_layout = QVBoxLayout(thoughts_frame)
        thoughts_layout.setContentsMargins(10, 8, 10, 8)
        thoughts_layout.setSpacing(4)

        # Header
        header = QLabel("Размышления модели")
        header.setStyleSheet("""
            QLabel {
                color: #9fa8da;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        thoughts_layout.addWidget(header)

        # Thoughts content
        thoughts_text = QLabel(thoughts[:2000] + "..." if len(thoughts) > 2000 else thoughts)
        thoughts_text.setWordWrap(True)
        thoughts_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        thoughts_text.setStyleSheet("""
            QLabel {
                color: #b0bec5;
                font-size: 12px;
                font-style: italic;
            }
        """)
        thoughts_layout.addWidget(thoughts_text)

        self.messages_layout.addWidget(thoughts_frame)

    def add_sent_images_message(self, image_paths: list[str], context: str = ""):
        """Add a message showing images sent to the model."""
        self._remove_stretch()

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1a3a1a;
                border: 1px solid #2e7d32;
                border-radius: 8px;
                margin-left: 50px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QLabel(f"Отправлено изображений: {len(image_paths)}")
        header.setStyleSheet("color: #81c784; font-weight: bold; font-size: 11px;")
        layout.addWidget(header)

        # Show thumbnails
        if image_paths:
            images_layout = QHBoxLayout()
            images_layout.setSpacing(4)
            for img_path in image_paths[:5]:  # Limit to 5 thumbnails
                thumb = ImageThumbnail(img_path, 60)
                thumb.clicked.connect(self._open_image_viewer)
                images_layout.addWidget(thumb)
            images_layout.addStretch()
            layout.addLayout(images_layout)

            # Track images for navigation
            for img in image_paths:
                if img not in self._all_images:
                    self._all_images.append(img)

        self.messages_layout.addWidget(frame)
        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def add_system_message(self, text: str):
        """Add a system notification message."""
        self._remove_stretch()

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: #90a4ae;
                font-style: italic;
                padding: 10px;
            }
        """)
        self.messages_layout.addWidget(label)

        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def add_answer_with_citations(
        self,
        answer_text: str,
        citations: list[dict],
        confidence: str = "medium",
        thoughts: Optional[str] = None
    ):
        """Add an answer message with citations block.

        Args:
            answer_text: The main answer in markdown format.
            citations: List of citation dicts with keys: kind, id, page, note.
            confidence: Confidence level (high, medium, low).
            thoughts: Optional model thoughts to display.
        """
        self._remove_stretch()

        # Show thoughts first if available
        if thoughts:
            self._add_thoughts_bubble(thoughts)

        # Main answer bubble
        answer_frame = QFrame()
        answer_frame.setStyleSheet("""
            QFrame {
                background-color: #37474f;
                border-radius: 12px;
                margin-right: 50px;
            }
        """)

        answer_layout = QVBoxLayout(answer_frame)
        answer_layout.setContentsMargins(10, 8, 10, 8)
        answer_layout.setSpacing(6)

        # Answer text
        answer_label = QLabel(answer_text)
        answer_label.setWordWrap(True)
        answer_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        answer_label.setStyleSheet("color: #eceff1;")
        answer_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        answer_layout.addWidget(answer_label)

        # Confidence indicator
        confidence_colors = {
            "high": "#4caf50",
            "medium": "#ff9800",
            "low": "#f44336"
        }
        confidence_label = QLabel(f"Уверенность: {confidence}")
        confidence_label.setStyleSheet(f"""
            QLabel {{
                color: {confidence_colors.get(confidence, '#888')};
                font-size: 11px;
                font-style: italic;
            }}
        """)
        answer_layout.addWidget(confidence_label)

        self.messages_layout.addWidget(answer_frame)

        # Citations block (separate from answer)
        if citations:
            self._add_citations_block(citations)

        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def _add_citations_block(self, citations: list[dict]):
        """Add a citations block below the answer."""
        citations_frame = QFrame()
        citations_frame.setStyleSheet("""
            QFrame {
                background-color: #263238;
                border: 1px solid #37474f;
                border-radius: 8px;
                margin-right: 50px;
                margin-top: 4px;
            }
        """)

        citations_layout = QVBoxLayout(citations_frame)
        citations_layout.setContentsMargins(10, 8, 10, 8)
        citations_layout.setSpacing(4)

        # Header
        header = QLabel(f"Источники ({len(citations)})")
        header.setStyleSheet("""
            QLabel {
                color: #4fc3f7;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        citations_layout.addWidget(header)

        # Citations list
        for citation in citations[:10]:  # Limit to 10 citations
            cite_widget = self._create_citation_item(citation)
            citations_layout.addWidget(cite_widget)

        if len(citations) > 10:
            more_label = QLabel(f"... и ещё {len(citations) - 10} источников")
            more_label.setStyleSheet("color: #78909c; font-size: 10px; font-style: italic;")
            citations_layout.addWidget(more_label)

        self.messages_layout.addWidget(citations_frame)

    def _create_citation_item(self, citation: dict) -> QFrame:
        """Create a single citation item widget."""
        item_frame = QFrame()
        item_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        item_frame.setStyleSheet("""
            QFrame {
                background-color: #1e272e;
                border-radius: 4px;
                padding: 2px;
            }
            QFrame:hover {
                background-color: #2c3e50;
            }
        """)

        item_layout = QHBoxLayout(item_frame)
        item_layout.setContentsMargins(8, 4, 8, 4)
        item_layout.setSpacing(8)

        # Icon based on kind
        kind = citation.get("kind", "text_block")
        icon_text = "📄" if kind == "text_block" else "🖼️"
        icon_label = QLabel(icon_text)
        icon_label.setFixedWidth(20)
        item_layout.addWidget(icon_label)

        # Block ID and page
        block_id = citation.get("id", "?")
        page = citation.get("page")
        id_text = f"[{block_id}]"
        if page:
            id_text += f" стр. {page}"

        id_label = QLabel(id_text)
        id_label.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 11px;")
        id_label.setFixedWidth(150)
        item_layout.addWidget(id_label)

        # Note
        note = citation.get("note", "")
        if note:
            note_label = QLabel(note[:80] + "..." if len(note) > 80 else note)
            note_label.setStyleSheet("color: #b0bec5; font-size: 11px;")
            note_label.setWordWrap(True)
            item_layout.addWidget(note_label, 1)

        return item_frame

    def add_followup_notice(self, iteration: int, max_iterations: int):
        """Add a notice about followup iteration."""
        self._remove_stretch()

        text = f"Требуется дополнительная информация (итерация {iteration}/{max_iterations})..."
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: #ff9800;
                font-style: italic;
                padding: 8px;
                background-color: #3e2723;
                border-radius: 4px;
            }
        """)
        self.messages_layout.addWidget(label)

        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def _remove_stretch(self):
        """Remove stretch item from layout."""
        count = self.messages_layout.count()
        if count > 0:
            item = self.messages_layout.itemAt(count - 1)
            if item.spacerItem():
                self.messages_layout.removeItem(item)

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the chat."""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _open_image_viewer(self, image_path: str):
        """Open the image viewer for the given image.

        Args:
            image_path: Path to the image to display.
        """
        if not os.path.exists(image_path):
            return

        # Create or reuse the image viewer
        if self._image_viewer is None:
            self._image_viewer = ImageViewer(self)
            self._image_viewer.roi_confirmed.connect(self._on_roi_confirmed)

        # Load all tracked images for navigation
        self._image_viewer.load_images(self._all_images)

        # Find and show the clicked image
        if image_path in self._all_images:
            index = self._all_images.index(image_path)
            self._image_viewer.show_image(index)
        else:
            # Image not in list, add it and show
            self._all_images.append(image_path)
            self._image_viewer.load_images(self._all_images)
            self._image_viewer.show_image(len(self._all_images) - 1)

        self._image_viewer.show()
        self._image_viewer.raise_()
        self._image_viewer.activateWindow()

    def _on_roi_confirmed(self, image_path: str, x0: float, y0: float, x1: float, y1: float):
        """Handle ROI confirmation from the image viewer.

        Args:
            image_path: Path to the source image.
            x0, y0, x1, y1: Normalized ROI coordinates (0.0-1.0).
        """
        # Emit signal for main window to handle
        self.roi_selected.emit(image_path, x0, y0, x1, y1)

        # Add a system message about the ROI selection
        self.add_system_message(
            f"Выбрана область: ({x0:.2f}, {y0:.2f}) - ({x1:.2f}, {y1:.2f})"
        )

    def get_all_images(self) -> list[str]:
        """Get list of all tracked images.

        Returns:
            List of image paths that have been displayed in the chat.
        """
        return self._all_images.copy()

    def clear_chat(self):
        """Clear all messages."""
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear tracked images
        self._all_images.clear()

        self.messages_layout.addStretch()

    def set_input_enabled(self, enabled: bool):
        """Enable or disable input."""
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def set_loading(self, loading: bool):
        """Show loading state."""
        self.set_input_enabled(not loading)
        if loading:
            self.send_button.setText("...")
        else:
            self.send_button.setText("Send")

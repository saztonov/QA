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
                border: 1px solid #ccc;
                border-radius: 4px;
                background: #f5f5f5;
            }
            QLabel:hover {
                border-color: #007bff;
            }
        """)

    def mousePressEvent(self, event):
        self.clicked.emit(self.image_path)


class MessageBubble(QFrame):
    """Message bubble widget."""

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

        # Styling
        if is_user:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #007bff;
                    border-radius: 12px;
                    margin-left: 50px;
                }
                QLabel {
                    color: white;
                }
            """)
        else:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #e9ecef;
                    border-radius: 12px;
                    margin-right: 50px;
                }
                QLabel {
                    color: #212529;
                }
            """)


class ChatWidget(QWidget):
    """Main chat widget."""

    message_sent = Signal(str)
    images_requested = Signal(list)  # List of image paths

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat history area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(10, 10, 10, 10)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-top: 1px solid #dee2e6;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 10, 10, 10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.setMinimumHeight(40)
        self.input_field.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ced4da;
                border-radius: 20px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #007bff;
            }
        """)
        self.input_field.returnPressed.connect(self._on_send)

        self.send_button = QPushButton("Send")
        self.send_button.setMinimumHeight(40)
        self.send_button.setMinimumWidth(80)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
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
        self.messages_layout.addWidget(bubble)

        # Add stretch back
        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def add_model_message(self, text: str):
        """Add a model message to the chat."""
        self._remove_stretch()

        bubble = MessageBubble(text, is_user=False)
        self.messages_layout.addWidget(bubble)

        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def add_system_message(self, text: str):
        """Add a system notification message."""
        self._remove_stretch()

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-style: italic;
                padding: 10px;
            }
        """)
        self.messages_layout.addWidget(label)

        self.messages_layout.addStretch()
        self._scroll_to_bottom()

    def add_image_request_message(self, filenames: list[str]):
        """Add a message showing requested images."""
        text = "Model requests images:\n" + "\n".join(f"  - {f}" for f in filenames)
        self._remove_stretch()

        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 10px;
                color: #856404;
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

    def clear_chat(self):
        """Clear all messages."""
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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

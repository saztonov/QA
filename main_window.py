"""Main window for Gemini Chat application."""

import os
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QComboBox,
    QLabel,
    QFileDialog,
    QMessageBox,
    QFrame,
    QGroupBox,
    QApplication,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

from config import Config, load_config
from gemini_client import GeminiClient, ModelResponse
from image_manager import ImageManager
from chat_widget import ChatWidget
from document_parser import DocumentParser
from prompt_builder import PromptBuilder
from block_manager import BlockManager


class WorkerSignals(QObject):
    """Signals for worker thread."""

    finished = Signal(object)  # ModelResponse
    error = Signal(str)


class SendMessageWorker(QThread):
    """Worker thread for sending messages to Gemini."""

    def __init__(
        self,
        client: GeminiClient,
        text: str,
        images: Optional[list[str]] = None,
        files: Optional[list[str]] = None,
    ):
        super().__init__()
        self.client = client
        self.text = text
        self.images = images
        self.files = files
        self.signals = WorkerSignals()

    def run(self):
        try:
            response = self.client.send_message(
                text=self.text,
                image_paths=self.images,
                file_paths=self.files,
            )
            self.signals.finished.emit(response)
        except Exception as e:
            self.signals.error.emit(str(e))


class SendImagesWorker(QThread):
    """Worker thread for sending images only."""

    def __init__(self, client: GeminiClient, images: list[str], context: str = ""):
        super().__init__()
        self.client = client
        self.images = images
        self.context = context
        self.signals = WorkerSignals()

    def run(self):
        try:
            response = self.client.send_images_only(self.images, self.context)
            self.signals.finished.emit(response)
        except Exception as e:
            self.signals.error.emit(str(e))


class SendFilesWorker(QThread):
    """Worker thread for sending files (PDF blocks)."""

    def __init__(self, client: GeminiClient, files: list[str], context: str = ""):
        super().__init__()
        self.client = client
        self.files = files
        self.context = context
        self.signals = WorkerSignals()

    def run(self):
        try:
            response = self.client.send_files_only(self.files, self.context)
            self.signals.finished.emit(response)
        except Exception as e:
            self.signals.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.gemini_client = GeminiClient(config)
        self.image_manager = ImageManager(config)
        self.current_worker: Optional[QThread] = None

        # Initialize document handling
        self.document_parser: Optional[DocumentParser] = None
        self.prompt_builder: Optional[PromptBuilder] = None
        self.block_manager: Optional[BlockManager] = None
        self._init_document_system()

        self._setup_ui()
        self._connect_signals()
        self._update_document_status()

    def _init_document_system(self) -> None:
        """Initialize the document parsing and prompt system."""
        if self.config.document_md_path.exists():
            try:
                self.document_parser = DocumentParser(self.config.document_md_path)
                self.prompt_builder = PromptBuilder(self.document_parser)
                self.block_manager = BlockManager(self.config, self.document_parser)

                # Set system prompt for the Gemini client
                system_prompt = self.prompt_builder.build_system_prompt()
                self.gemini_client.set_system_prompt(system_prompt)
            except Exception as e:
                print(f"Warning: Could not initialize document system: {e}")

    def _setup_ui(self):
        """Setup the main UI."""
        self.setWindowTitle("Gemini Chat")
        self.setMinimumSize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - files and settings
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel - chat
        self.chat_widget = ChatWidget()
        splitter.addWidget(self.chat_widget)

        splitter.setSizes([300, 700])
        main_layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with files and settings."""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-right: 1px solid #dee2e6;
            }
        """)
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(400)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # Model selection
        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout(model_group)

        self.model_combo = QComboBox()
        for model in self.config.available_models:
            self.model_combo.addItem(model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_layout.addWidget(self.model_combo)

        layout.addWidget(model_group)

        # Search directories
        dirs_group = QGroupBox("Search Directories")
        dirs_layout = QVBoxLayout(dirs_group)

        self.dirs_list = QListWidget()
        self.dirs_list.setMaximumHeight(100)
        dirs_layout.addWidget(self.dirs_list)

        dirs_buttons = QHBoxLayout()
        add_dir_btn = QPushButton("Add")
        add_dir_btn.clicked.connect(self._add_search_directory)
        remove_dir_btn = QPushButton("Remove")
        remove_dir_btn.clicked.connect(self._remove_search_directory)
        dirs_buttons.addWidget(add_dir_btn)
        dirs_buttons.addWidget(remove_dir_btn)
        dirs_layout.addLayout(dirs_buttons)

        layout.addWidget(dirs_group)

        # Loaded files
        files_group = QGroupBox("Loaded Files")
        files_layout = QVBoxLayout(files_group)

        self.files_list = QListWidget()
        files_layout.addWidget(self.files_list)

        files_buttons = QHBoxLayout()
        add_files_btn = QPushButton("Add Files")
        add_files_btn.clicked.connect(self._add_files)
        clear_files_btn = QPushButton("Clear")
        clear_files_btn.clicked.connect(self._clear_files)
        files_buttons.addWidget(add_files_btn)
        files_buttons.addWidget(clear_files_btn)
        files_layout.addLayout(files_buttons)

        layout.addWidget(files_group)

        # Document status
        doc_group = QGroupBox("Документ")
        doc_layout = QVBoxLayout(doc_group)

        self.doc_status_label = QLabel("Загрузка...")
        self.doc_status_label.setWordWrap(True)
        self.doc_status_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        doc_layout.addWidget(self.doc_status_label)

        self.blocks_count_label = QLabel("")
        self.blocks_count_label.setStyleSheet("color: #28a745; font-weight: bold;")
        doc_layout.addWidget(self.blocks_count_label)

        layout.addWidget(doc_group)

        # Actions
        actions_layout = QVBoxLayout()

        new_chat_btn = QPushButton("New Chat")
        new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        new_chat_btn.clicked.connect(self._new_chat)
        actions_layout.addWidget(new_chat_btn)

        layout.addLayout(actions_layout)
        layout.addStretch()

        return panel

    def _update_document_status(self) -> None:
        """Update the document status in the UI."""
        if self.document_parser:
            try:
                doc_data = self.document_parser.parse()
                self.doc_status_label.setText(f"Загружен: document.md")
                block_count = len(doc_data.image_blocks)
                self.blocks_count_label.setText(f"{block_count} графических блоков")
            except Exception as e:
                self.doc_status_label.setText(f"Ошибка: {str(e)[:50]}")
                self.blocks_count_label.setText("")
        else:
            self.doc_status_label.setText("Документ не найден")
            self.blocks_count_label.setText("")

    def _connect_signals(self):
        """Connect signals."""
        self.chat_widget.message_sent.connect(self._on_message_sent)

    def _on_model_changed(self, model: str):
        """Handle model change."""
        self.gemini_client.set_model(model)
        self.chat_widget.add_system_message(f"Model changed to: {model}")

    def _add_search_directory(self):
        """Add a search directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory"
        )
        if directory:
            if self.image_manager.add_search_directory(directory):
                self.dirs_list.addItem(directory)

    def _remove_search_directory(self):
        """Remove selected search directory."""
        current = self.dirs_list.currentItem()
        if current:
            self.image_manager.remove_search_directory(current.text())
            self.dirs_list.takeItem(self.dirs_list.row(current))

    def _add_files(self):
        """Add files to load."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files",
            "",
            "Images & Documents (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf *.txt *.md)"
        )
        for file_path in files:
            if self.image_manager.add_loaded_file(file_path):
                self.files_list.addItem(os.path.basename(file_path))

    def _clear_files(self):
        """Clear loaded files."""
        self.image_manager.clear_loaded_files()
        self.files_list.clear()

    def _new_chat(self):
        """Start a new chat."""
        self.gemini_client.start_new_chat()
        self.chat_widget.clear_chat()

        # Show document status
        if self.document_parser:
            doc_data = self.document_parser.parse()
            block_count = len(doc_data.image_blocks)
            self.chat_widget.add_system_message(
                f"Новый чат. Документ загружен: {block_count} графических блоков доступно."
            )
        else:
            self.chat_widget.add_system_message("Новый чат начат")

    def _on_message_sent(self, text: str):
        """Handle user message."""
        # Get loaded images
        images = self.image_manager.get_loaded_images()
        files = [f for f in self.image_manager.get_loaded_files()
                 if not self.image_manager.is_image_file(f)]

        # Show user message in chat
        self.chat_widget.add_user_message(text, images if images else None)

        # Disable input while processing
        self.chat_widget.set_loading(True)

        # Send to Gemini in background thread
        self.current_worker = SendMessageWorker(
            self.gemini_client, text, images, files
        )
        self.current_worker.signals.finished.connect(self._on_response_received)
        self.current_worker.signals.error.connect(self._on_error)
        self.current_worker.start()

    def _on_response_received(self, response: ModelResponse):
        """Handle response from Gemini."""
        self.chat_widget.set_loading(False)
        self.chat_widget.add_model_message(response.text)

        # Check if model is requesting document blocks (new flow)
        if response.needs_blocks and response.requested_blocks:
            requested_ids = [r.block_id for r in response.requested_blocks]
            self.chat_widget.add_system_message(
                f"Модель запрашивает блоки: {', '.join(requested_ids)}"
            )
            self._send_requested_blocks(requested_ids)
            return

        # Check if model is requesting images (old flow)
        if response.needs_images and response.requested_images:
            # Model is requesting images
            requested_names = [r.filename for r in response.requested_images]
            self.chat_widget.add_image_request_message(requested_names)

            # Try to find requested images
            found_images = []
            not_found = []

            for req in response.requested_images:
                matches = self.image_manager.find_image(req.filename)
                if matches:
                    found_images.extend(matches[:1])  # Take first match
                else:
                    not_found.append(req.filename)

            if found_images:
                self.chat_widget.add_system_message(
                    f"Found {len(found_images)} image(s), sending to model..."
                )
                self._send_found_images(found_images)
            elif not_found:
                # Let user manually add images
                self.chat_widget.add_system_message(
                    f"Could not find: {', '.join(not_found)}\n"
                    "Please add the images manually using 'Add Files' button."
                )

    def _send_requested_blocks(self, block_ids: list[str]) -> None:
        """Send requested document blocks to the model."""
        if not self.block_manager:
            self.chat_widget.add_system_message(
                "Система документов не инициализирована."
            )
            return

        # Get file paths for requested blocks
        found_paths, not_found_ids = self.block_manager.get_block_files_for_ids(block_ids)

        if not_found_ids:
            self.chat_widget.add_system_message(
                f"Блоки не найдены: {', '.join(not_found_ids)}"
            )

        if found_paths:
            # Build context message
            block_descriptions = []
            for block_id in block_ids:
                if self.block_manager.is_block_available(block_id):
                    desc = self.block_manager.get_block_description(block_id)
                    block_descriptions.append(desc)

            context = "Вот запрошенные графические блоки:\n" + "\n".join(
                f"- {desc}" for desc in block_descriptions
            ) + "\n\nПроанализируй эти изображения и дай полный ответ на вопрос пользователя."

            self.chat_widget.add_system_message(
                f"Отправляю {len(found_paths)} блок(ов) модели..."
            )
            self._send_block_files(found_paths, context)
        else:
            self.chat_widget.add_system_message(
                "Ни один из запрошенных блоков не найден."
            )

    def _send_block_files(self, file_paths: list[str], context: str = "") -> None:
        """Send block files to the model."""
        self.chat_widget.set_loading(True)

        self.current_worker = SendFilesWorker(
            self.gemini_client,
            file_paths,
            context
        )
        self.current_worker.signals.finished.connect(self._on_response_received)
        self.current_worker.signals.error.connect(self._on_error)
        self.current_worker.start()

    def _send_found_images(self, images: list[str]):
        """Send found images to model."""
        self.chat_widget.set_loading(True)

        self.current_worker = SendImagesWorker(
            self.gemini_client,
            images,
            "Here are the requested images."
        )
        self.current_worker.signals.finished.connect(self._on_response_received)
        self.current_worker.signals.error.connect(self._on_error)
        self.current_worker.start()

    def _on_error(self, error: str):
        """Handle error."""
        self.chat_widget.set_loading(False)
        self.chat_widget.add_system_message(f"Error: {error}")
        QMessageBox.warning(self, "Error", error)

"""Main window for Gemini Chat application."""

import os
from pathlib import Path
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
    QScrollArea,
    QTabWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from datetime import datetime

from config import Config, load_config
from gemini_client import GeminiClient, ModelResponse
from chat_widget import ChatWidget
from document_parser import DocumentParser
from prompt_builder import PromptBuilder
from block_manager import BlockManager
from api_log_widget import ApiLogWidget
from model_settings_widget import ModelSettingsWidget, GenerationConfig
from process_timeline_widget import ProcessTimelineWidget, ProcessEvent, EventType, create_event_from_usage
from planner import Planner
from answerer import Answerer
from schemas import (
    Plan, PlanDecision, RequestedROI, Answer,
    FollowupBlock, FollowupROI, BBoxNorm
)
from evidence import EvidenceManager
from conversation_memory import ConversationMemory
from summarizer import Summarizer
from block_indexer import BlockIndexer, BlockIndex, load_block_index
from thinking_context import ThinkingContext
from workers import (
    SendMessageWorker,
    SendFilesWorker,
    SendImagesWorker,
    PlanWorker,
    AnswerWorker,
    SummarizerWorker,
    IndexWorker,
)
from handlers import MainWindowHandlers


class MainWindow(MainWindowHandlers, QMainWindow):
    """Main application window."""

    MAX_ANSWER_ITERATIONS = 3  # Maximum iterations for followup evidence

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.gemini_client = GeminiClient(config)
        self.current_worker: Optional[QThread] = None

        # Initialize document handling (not loaded at startup)
        self.document_parser: Optional[DocumentParser] = None
        self.prompt_builder: Optional[PromptBuilder] = None
        self.block_manager: Optional[BlockManager] = None
        self.loaded_document_path: Optional[str] = None
        self.loaded_crops_dir: Optional[str] = None

        # Initialize conversation memory (stores last N text turns + summary)
        self.conversation_memory = ConversationMemory(max_turns=10)

        # Initialize thinking context for thought signatures continuity
        self.thinking_context = ThinkingContext()

        # Initialize summarizer for compressing conversation history
        self.summarizer = Summarizer(config)
        self.summarizer_worker: Optional[SummarizerWorker] = None

        # Initialize planner for structured query planning
        self.planner = Planner(config, conversation_memory=self.conversation_memory)
        self.use_planner = True  # Can be toggled via settings if needed

        # Initialize answerer for structured answers with thinking context
        self.answerer = Answerer(
            config,
            conversation_memory=self.conversation_memory,
            thinking_context=self.thinking_context
        )

        # Initialize evidence manager for ROI rendering
        self.evidence_manager = EvidenceManager()

        # Initialize block indexer
        self.block_indexer = BlockIndexer(config)
        self.block_index: Optional[BlockIndex] = None
        self.index_worker: Optional[IndexWorker] = None

        # Current generation settings
        self._current_media_resolution = "MEDIA_RESOLUTION_MEDIUM"

        # Current query state for iterative answering
        self._current_question: Optional[str] = None
        self._current_iteration: int = 0
        self._accumulated_evidence_paths: list[str] = []
        self._accumulated_file_paths: list[str] = []

        # Pending user ROI (selected via ImageViewer before asking a question)
        self._pending_user_roi: Optional[dict] = None

        self._setup_ui()
        self._connect_signals()

    def _init_document_system(self, document_path: str, crops_dir: Optional[str] = None) -> bool:
        """Initialize the document parsing and prompt system with given paths."""
        from pathlib import Path
        doc_path = Path(document_path)

        if not doc_path.exists():
            return False

        try:
            self.document_parser = DocumentParser(doc_path)
            self.prompt_builder = PromptBuilder(self.document_parser)

            # Update config paths for block manager
            if crops_dir:
                self.config.crops_dir = Path(crops_dir)
            self.config.document_md_path = doc_path

            self.block_manager = BlockManager(self.config, self.document_parser)

            # Set system prompt for the Gemini client
            system_prompt = self.prompt_builder.build_system_prompt()
            self.gemini_client.set_system_prompt(system_prompt)

            # Update planner and answerer with document parser
            self.planner.set_parser(self.document_parser)
            self.answerer.set_parser(self.document_parser)

            self.loaded_document_path = document_path
            self.loaded_crops_dir = crops_dir
            return True
        except Exception as e:
            print(f"Warning: Could not initialize document system: {e}")
            return False

    def _setup_ui(self):
        """Setup the main UI."""
        self.setWindowTitle("Gemini Chat")
        self.setMinimumSize(1300, 700)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - files and settings
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Center panel - chat
        self.chat_widget = ChatWidget()
        splitter.addWidget(self.chat_widget)

        # Right panel - Timeline and API log tabs
        right_panel = QTabWidget()
        right_panel.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 8px 16px;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #4fc3f7;
                border-bottom: 2px solid #4fc3f7;
            }
            QTabBar::tab:hover {
                background-color: #3d3d3d;
            }
        """)
        right_panel.setMinimumWidth(300)
        right_panel.setMaximumWidth(550)

        # Timeline widget (primary)
        self.timeline_widget = ProcessTimelineWidget()
        right_panel.addTab(self.timeline_widget, "Timeline")

        # API log widget (detailed)
        self.api_log_widget = ApiLogWidget()
        right_panel.addTab(self.api_log_widget, "API Log")

        splitter.addWidget(right_panel)

        splitter.setSizes([280, 620, 400])
        main_layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with files and settings."""
        # Dark theme styles
        dark_style = """
            QFrame#leftPanel {
                background-color: #1e1e1e;
                border-right: 1px solid #3c3c3c;
            }
            QGroupBox {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #4fc3f7;
            }
            QListWidget {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                color: #d4d4d4;
                padding: 4px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 3px;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QListWidget::item:hover {
                background-color: #2a2d2e;
            }
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 10px;
                color: #d4d4d4;
                min-height: 20px;
            }
            QComboBox:hover {
                border-color: #007acc;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #007acc;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QLabel {
                color: #d4d4d4;
            }
        """

        # Main container
        container = QFrame()
        container.setObjectName("leftPanel")
        container.setStyleSheet(dark_style)
        container.setMinimumWidth(300)
        container.setMaximumWidth(420)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1e1e1e;
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

        panel = QWidget()
        panel.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Model selection
        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout(model_group)

        self.model_combo = QComboBox()
        for model in self.config.available_models:
            self.model_combo.addItem(model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_layout.addWidget(self.model_combo)

        layout.addWidget(model_group)

        # Model settings
        self.model_settings_widget = ModelSettingsWidget()
        self.model_settings_widget.settings_changed.connect(self._on_settings_changed)
        layout.addWidget(self.model_settings_widget)

        # Documents section (document.md + crops folder)
        docs_group = QGroupBox("Документы")
        docs_layout = QVBoxLayout(docs_group)

        self.docs_list = QListWidget()
        self.docs_list.setMaximumHeight(120)
        docs_layout.addWidget(self.docs_list)

        # Document status
        self.doc_status_label = QLabel("Документы не загружены")
        self.doc_status_label.setWordWrap(True)
        self.doc_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        docs_layout.addWidget(self.doc_status_label)

        self.blocks_count_label = QLabel("")
        self.blocks_count_label.setStyleSheet("color: #4caf50; font-weight: bold; padding: 2px 4px;")
        docs_layout.addWidget(self.blocks_count_label)

        docs_buttons = QHBoxLayout()
        add_doc_btn = QPushButton("Добавить")
        add_doc_btn.clicked.connect(self._add_document)
        remove_doc_btn = QPushButton("Убрать")
        remove_doc_btn.clicked.connect(self._remove_document)
        docs_buttons.addWidget(add_doc_btn)
        docs_buttons.addWidget(remove_doc_btn)
        docs_layout.addLayout(docs_buttons)

        # Block index section
        self.index_status_label = QLabel("Индекс блоков: не создан")
        self.index_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        docs_layout.addWidget(self.index_status_label)

        self.build_index_btn = QPushButton("Построить индекс блоков")
        self.build_index_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0a3d91;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #888;
            }
        """)
        self.build_index_btn.clicked.connect(self._build_block_index)
        self.build_index_btn.setEnabled(False)  # Enabled when crops folder is loaded
        docs_layout.addWidget(self.build_index_btn)

        layout.addWidget(docs_group)

        # Actions
        actions_layout = QVBoxLayout()

        new_chat_btn = QPushButton("New Chat")
        new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #388e3c;
            }
            QPushButton:pressed {
                background-color: #1b5e20;
            }
        """)
        new_chat_btn.clicked.connect(self._new_chat)
        actions_layout.addWidget(new_chat_btn)

        layout.addLayout(actions_layout)
        layout.addStretch()

        # Setup scroll area
        scroll.setWidget(panel)
        container_layout.addWidget(scroll)

        return container

    def _update_document_status(self) -> None:
        """Update the document status in the UI."""
        if self.document_parser:
            try:
                doc_data = self.document_parser.parse()
                doc_name = os.path.basename(self.loaded_document_path) if self.loaded_document_path else "document.md"
                self.doc_status_label.setText(f"Загружен: {doc_name}")
                block_count = len(doc_data.image_blocks)
                self.blocks_count_label.setText(f"{block_count} графических блоков")
            except Exception as e:
                self.doc_status_label.setText(f"Ошибка: {str(e)[:50]}")
                self.blocks_count_label.setText("")
        else:
            self.doc_status_label.setText("Документы не загружены")
            self.blocks_count_label.setText("")

    def _update_docs_list(self) -> None:
        """Update the documents list in the UI."""
        self.docs_list.clear()
        if self.loaded_document_path:
            self.docs_list.addItem(f"📄 {os.path.basename(self.loaded_document_path)}")
        if self.loaded_crops_dir:
            self.docs_list.addItem(f"📁 {os.path.basename(self.loaded_crops_dir)}/")

    def _add_document(self) -> None:
        """Add document.md file or crops folder."""
        # Show menu to choose what to add
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                color: #d4d4d4;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """)

        add_doc_action = menu.addAction("📄 Добавить document.md")
        add_crops_action = menu.addAction("📁 Добавить папку crops")

        action = menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

        if action == add_doc_action:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Выберите document.md",
                "",
                "Markdown Files (*.md);;All Files (*)"
            )
            if file_path:
                success = self._init_document_system(file_path, self.loaded_crops_dir)
                if success:
                    self._update_docs_list()
                    self._update_document_status()
                    self.chat_widget.add_system_message(f"Загружен документ: {os.path.basename(file_path)}")
                    # Log document loaded
                    doc_data = self.document_parser.parse()
                    self.api_log_widget.log_document_loaded(file_path, len(doc_data.image_blocks))
                    # Log system prompt
                    if self.prompt_builder:
                        self.api_log_widget.log_system_prompt(self.prompt_builder.build_system_prompt())
                else:
                    QMessageBox.warning(self, "Ошибка", "Не удалось загрузить документ")

        elif action == add_crops_action:
            directory = QFileDialog.getExistingDirectory(
                self, "Выберите папку с кропами"
            )
            if directory:
                self.loaded_crops_dir = directory
                if self.loaded_document_path:
                    # Reinitialize with new crops directory
                    self._init_document_system(self.loaded_document_path, directory)
                else:
                    from pathlib import Path
                    self.config.crops_dir = Path(directory)
                self._update_docs_list()
                self._update_document_status()
                self.chat_widget.add_system_message(f"Загружена папка кропов: {os.path.basename(directory)}")
                # Log crops loaded
                self.api_log_widget.log_crops_loaded(directory)

                # Enable index button and try to load existing index
                self.build_index_btn.setEnabled(True)
                self._try_load_existing_index(directory)

    def _remove_document(self) -> None:
        """Remove selected document or crops folder."""
        current = self.docs_list.currentItem()
        if not current:
            return

        text = current.text()
        if text.startswith("📄"):
            # Remove document
            self.loaded_document_path = None
            self.document_parser = None
            self.prompt_builder = None
            self.block_manager = None
            self.gemini_client.set_system_prompt(None)
            self.chat_widget.add_system_message("Документ удален")
        elif text.startswith("📁"):
            # Remove crops folder
            self.loaded_crops_dir = None
            self.block_manager = None
            self.block_index = None
            self.build_index_btn.setEnabled(False)
            self._update_index_status()
            self.chat_widget.add_system_message("Папка кропов удалена")

        self._update_docs_list()
        self._update_document_status()

    def _connect_signals(self):
        """Connect signals."""
        self.chat_widget.message_sent.connect(self._on_message_sent)
        self.chat_widget.roi_selected.connect(self._on_user_roi_selected)

    def _on_model_changed(self, model: str):
        """Handle model change."""
        self.gemini_client.set_model(model)
        self.chat_widget.add_system_message(f"Model changed to: {model}")
        self.api_log_widget.log_model_change(model)

    def _on_settings_changed(self, config: GenerationConfig):
        """Handle generation settings change."""
        self.gemini_client.set_generation_config(config)

        # Update media resolution for answerer
        self._current_media_resolution = config.media_resolution
        self.answerer.set_media_resolution(config.media_resolution)

        # Log settings change
        self.api_log_widget.add_log_entry("SETTINGS_CHANGE", {
            "temperature": config.temperature,
            "top_p": config.top_p,
            "top_k": config.top_k,
            "max_output_tokens": config.max_output_tokens,
            "media_resolution": config.media_resolution,
            "presence_penalty": config.presence_penalty,
            "frequency_penalty": config.frequency_penalty,
        })

    def _new_chat(self):
        """Start a new chat."""
        self.gemini_client.start_new_chat()
        self.chat_widget.clear_chat()
        self.api_log_widget.log_new_chat()

        # Clear Timeline
        self.timeline_widget.clear()

        # Clear conversation memory and thinking context
        self.conversation_memory.clear()
        self.thinking_context.clear()

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
        # Show user message in chat
        self.chat_widget.add_user_message(text)

        # Disable input while processing
        self.chat_widget.set_loading(True)

        # Use planner if document is loaded and planner is enabled
        if self.use_planner and self.document_parser:
            # Get context stats for logging
            context_stats = self.planner.get_context_stats()

            # Log planning request with context stats
            self.api_log_widget.log_plan_request(
                text,
                model=Planner.MODEL_NAME,
                context_stats=context_stats,
            )
            self.chat_widget.add_system_message("Planning...")

            # Add Timeline event for planning start
            self.timeline_widget.add_event(ProcessEvent(
                timestamp=datetime.now(),
                event_type=EventType.PLANNING_START,
                title="Planning query",
                model="Flash",
                status="in_progress",
            ))

            # Run planning in background
            self.current_worker = PlanWorker(self.planner, text)
            self.current_worker.signals.finished.connect(self._on_plan_received)
            self.current_worker.signals.error.connect(self._on_plan_error)
            self.current_worker.start()
        else:
            # Direct send without planning (legacy flow)
            self.api_log_widget.log_request(
                text=text,
                model=self.gemini_client.current_model
            )
            self.current_worker = SendMessageWorker(
                self.gemini_client, text
            )
            self.current_worker.signals.finished.connect(self._on_response_received)
            self.current_worker.signals.error.connect(self._on_error)
            self.current_worker.start()

    # =========================================================================
    # Block Indexing Methods
    # =========================================================================

    def _get_output_dir(self) -> Path:
        """Get or create output directory for index files."""
        output_dir = Path(self.loaded_crops_dir).parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _get_index_path(self) -> Path:
        """Get path for block index file."""
        return self._get_output_dir() / "block_index.json"

    def _try_load_existing_index(self, crops_dir: str) -> None:
        """Try to load existing block index from output directory.

        Args:
            crops_dir: Path to crops directory.
        """
        # Look for index in output folder (sibling to crops)
        output_dir = Path(crops_dir).parent / "output"
        index_path = output_dir / "block_index.json"

        if index_path.exists():
            self.block_index = load_block_index(index_path)
            if self.block_index:
                self._update_index_status()
                # Update planner with index
                self.planner.set_block_index(self.block_index)
                self.chat_widget.add_system_message(
                    f"Загружен индекс блоков: {self.block_index.indexed_blocks} блоков"
                )

    def _update_index_status(self) -> None:
        """Update the index status label in UI."""
        if self.block_index and self.block_index.indexed_blocks > 0:
            total = self.block_index.total_blocks
            indexed = self.block_index.indexed_blocks
            failed = len(self.block_index.failed_blocks)

            if failed > 0:
                status = f"Индекс: {indexed}/{total} блоков ({failed} ошибок)"
                self.index_status_label.setStyleSheet("color: #ffa726; font-size: 11px; padding: 4px;")
            else:
                status = f"Индекс: {indexed}/{total} блоков"
                self.index_status_label.setStyleSheet("color: #4caf50; font-size: 11px; padding: 4px;")

            self.index_status_label.setText(status)
        else:
            self.index_status_label.setText("Индекс блоков: не создан")
            self.index_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")


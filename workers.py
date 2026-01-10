"""Worker classes for background operations in Qt threads."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal, QObject

from gemini_client import GeminiClient
from planner import Planner
from answerer import Answerer
from conversation_memory import ConversationMemory
from summarizer import Summarizer
from block_indexer import BlockIndexer


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


class SendImagesWorker(QThread):
    """Worker thread for sending images (PNG crops)."""

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


class PlanWorkerSignals(QObject):
    """Signals for plan worker thread."""

    finished = Signal(object, str, str)  # Plan, raw_json, original_question
    error = Signal(str)


class PlanWorker(QThread):
    """Worker thread for planning with Flash model."""

    def __init__(self, planner: Planner, question: str):
        super().__init__()
        self.planner = planner
        self.question = question
        self.signals = PlanWorkerSignals()

    def run(self):
        try:
            plan, raw_json = self.planner.plan_with_raw_response(self.question)
            self.signals.finished.emit(plan, raw_json, self.question)
        except Exception as e:
            self.signals.error.emit(str(e))


class AnswerWorkerSignals(QObject):
    """Signals for answer worker thread."""

    finished = Signal(object, str, str, int)  # Answer, raw_json, original_question, iteration
    error = Signal(str)


class AnswerWorker(QThread):
    """Worker thread for answering with Pro model."""

    def __init__(
        self,
        answerer: Answerer,
        question: str,
        image_paths: list[str] = None,
        file_paths: list[str] = None,
        context_message: str = None,
        iteration: int = 1
    ):
        super().__init__()
        self.answerer = answerer
        self.question = question
        self.image_paths = image_paths or []
        self.file_paths = file_paths or []
        self.context_message = context_message
        self.iteration = iteration
        self.signals = AnswerWorkerSignals()

    def run(self):
        try:
            answer, raw_json = self.answerer.answer_with_raw_response(
                question=self.question,
                image_paths=self.image_paths,
                file_paths=self.file_paths,
                context_message=self.context_message,
                iteration=self.iteration
            )
            self.signals.finished.emit(answer, raw_json, self.question, self.iteration)
        except Exception as e:
            self.signals.error.emit(str(e))


class SummarizerWorkerSignals(QObject):
    """Signals for summarizer worker thread."""

    finished = Signal(str, int)  # new_summary, turns_summarized
    error = Signal(str)


class SummarizerWorker(QThread):
    """Worker thread for summarizing conversation in background."""

    def __init__(self, summarizer: Summarizer, memory: ConversationMemory):
        super().__init__()
        self.summarizer = summarizer
        self.memory = memory
        self.signals = SummarizerWorkerSignals()

    def run(self):
        try:
            turns_to_summarize = self.memory.get_turns_for_summarization()
            if turns_to_summarize:
                new_summary = self.summarizer.summarize(
                    previous_summary=self.memory.summary,
                    turns_to_summarize=turns_to_summarize,
                )
                self.signals.finished.emit(new_summary, len(turns_to_summarize))
            else:
                self.signals.finished.emit(self.memory.summary, 0)
        except Exception as e:
            self.signals.error.emit(str(e))


class IndexWorkerSignals(QObject):
    """Signals for block indexer worker thread."""

    progress = Signal(int, int, str)  # indexed, total, current_blocks
    error = Signal(str, str)  # block_ids, error_message
    finished = Signal(object)  # BlockIndex


class IndexWorker(QThread):
    """Worker thread for building block index."""

    def __init__(self, indexer: BlockIndexer, crops_dir: str, output_path: str):
        super().__init__()
        self.indexer = indexer
        self.crops_dir = crops_dir
        self.output_path = output_path
        self.signals = IndexWorkerSignals()

        # Connect indexer callbacks
        self.indexer.on_progress = self._on_progress
        self.indexer.on_error = self._on_error

    def _on_progress(self, indexed: int, total: int, message: str):
        self.signals.progress.emit(indexed, total, message)

    def _on_error(self, block_ids: str, error: str):
        self.signals.error.emit(block_ids, error)

    def run(self):
        try:
            index = self.indexer.index_directory(
                crops_dir=Path(self.crops_dir),
                output_path=Path(self.output_path),
                skip_existing=True,
            )
            self.signals.finished.emit(index)
        except Exception as e:
            self.signals.error.emit("all", str(e))
            self.signals.finished.emit(None)

"""Event handlers mixin for MainWindow.

This module contains all event handler methods extracted from MainWindow
to reduce the main file size while maintaining functionality.
"""

import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from schemas import (
    Plan, PlanDecision, RequestedROI, Answer,
)
from answerer import Answerer
from block_indexer import BlockIndex, load_block_index

if TYPE_CHECKING:
    from gemini_client import ModelResponse
    from workers import (
        AnswerWorker,
        SummarizerWorker,
        SendFilesWorker,
        IndexWorker,
    )


class MainWindowHandlers:
    """Mixin class containing event handlers for MainWindow.

    This class is designed to be inherited by MainWindow along with QMainWindow.
    All methods access instance attributes through self, which will resolve
    to the MainWindow instance at runtime.
    """

    # =========================================================================
    # Planner Handlers
    # =========================================================================

    def _on_plan_received(self, plan: Plan, raw_json: str, original_question: str, usage: dict = None):
        """Handle planning response from Flash model."""
        usage = usage or {}

        # Log the plan response with usage
        self.api_log_widget.log_plan_response(plan.model_dump(), raw_json, usage=usage)

        # Show plan decision in chat
        decision_messages = {
            PlanDecision.ANSWER_FROM_TEXT: "Plan: Answer from text context",
            PlanDecision.NEED_BLOCKS: f"Plan: Need {len(plan.requested_blocks)} block(s)",
            PlanDecision.NEED_ZOOM_ROI: f"Plan: Need {len(plan.requested_rois)} ROI(s)",
            PlanDecision.ASK_USER: "Plan: Need clarification",
        }
        self.chat_widget.add_system_message(
            f"{decision_messages.get(plan.decision, 'Plan received')} - {plan.reasoning[:100]}"
        )

        # Process based on decision
        if plan.decision == PlanDecision.ANSWER_FROM_TEXT:
            self._send_to_pro_model(original_question)

        elif plan.decision == PlanDecision.NEED_BLOCKS:
            block_ids = plan.get_block_ids()
            if block_ids:
                self._send_blocks_and_question(block_ids, original_question)
            else:
                self._send_to_pro_model(original_question)

        elif plan.decision == PlanDecision.NEED_ZOOM_ROI:
            if plan.requested_rois:
                self._send_rois_and_question(plan.requested_rois, original_question)
            else:
                self._send_to_pro_model(original_question)

        elif plan.decision == PlanDecision.ASK_USER:
            self.chat_widget.set_loading(False)
            if plan.user_requests:
                questions = "\n".join(f"- {r.text}" for r in plan.user_requests)
                self.chat_widget.add_model_message(
                    f"Need clarification:\n{questions}"
                )
            else:
                self.chat_widget.add_model_message(
                    "Could you please clarify your question?"
                )

    def _on_plan_error(self, error: str):
        """Handle planning error - fallback to direct send."""
        self.chat_widget.add_system_message(f"Planning error: {error}. Using direct send.")
        self.api_log_widget.log_error(f"Planning error: {error}")
        self.chat_widget.set_loading(False)

    # =========================================================================
    # Query State Management
    # =========================================================================

    def _reset_query_state(self):
        """Reset the query state for a new question."""
        self._current_question = None
        self._current_iteration = 0
        self._accumulated_evidence_paths = []
        self._accumulated_file_paths = []
        self._pending_user_roi = None

    # =========================================================================
    # Answerer Methods
    # =========================================================================

    def _send_to_answerer(
        self,
        question: str,
        image_paths: list[str] = None,
        file_paths: list[str] = None,
        context_message: str = None,
        iteration: int = 1
    ):
        """Send question to Pro model (Answerer) with optional evidence."""
        from workers import AnswerWorker

        image_paths = image_paths or []
        file_paths = file_paths or []

        # Store state for potential followup iterations
        self._current_question = question
        self._current_iteration = iteration

        # Accumulate evidence across iterations
        for p in image_paths:
            if p not in self._accumulated_evidence_paths:
                self._accumulated_evidence_paths.append(p)
        for p in file_paths:
            if p not in self._accumulated_file_paths:
                self._accumulated_file_paths.append(p)

        # Get context stats for logging
        context_stats = self.answerer.get_context_stats(
            image_paths=self._accumulated_evidence_paths,
            file_paths=self._accumulated_file_paths,
        )

        # Log the answer request
        self.api_log_widget.log_answer_request(
            question=question,
            model=Answerer.MODEL_NAME,
            iteration=iteration,
            images_count=len(self._accumulated_evidence_paths),
            files_count=len(self._accumulated_file_paths),
            context_stats=context_stats,
        )

        self.chat_widget.add_system_message(
            f"Answering (iteration {iteration}/{self.MAX_ANSWER_ITERATIONS})..."
        )

        # Send to Answerer
        self.current_worker = AnswerWorker(
            answerer=self.answerer,
            question=question,
            image_paths=self._accumulated_evidence_paths,
            file_paths=self._accumulated_file_paths,
            context_message=context_message,
            iteration=iteration
        )
        self.current_worker.signals.finished.connect(self._on_answer_received)
        self.current_worker.signals.error.connect(self._on_answer_error)
        self.current_worker.start()

    def _send_to_pro_model(self, question: str):
        """Send question to Pro model without additional blocks."""
        self._reset_query_state()
        self._send_to_answerer(question, iteration=1)

    def _send_blocks_and_question(self, block_ids: list[str], question: str):
        """Send blocks and question to Pro model."""
        if not self.block_manager:
            self.chat_widget.add_system_message("Block manager not initialized.")
            self._send_to_pro_model(question)
            return

        # Validate block IDs first
        valid_ids, invalid_ids = self._validate_block_ids(block_ids)

        if invalid_ids:
            self.chat_widget.add_system_message(
                f"Невалидные блоки (пропущены): {', '.join(invalid_ids)}"
            )
            self.api_log_widget.add_log_entry("BLOCK_VALIDATION_WARNING", {
                "invalid_ids": invalid_ids,
                "valid_ids": valid_ids,
            })

        if not valid_ids:
            self.chat_widget.add_system_message("Нет валидных блоков для отправки.")
            self._send_to_pro_model(question)
            return

        # Get file paths for validated blocks
        found_paths, not_found_ids = self.block_manager.get_block_files_for_ids(valid_ids)

        if not_found_ids:
            self.chat_widget.add_system_message(
                f"Blocks not found: {', '.join(not_found_ids)}"
            )

        if found_paths:
            # Build context message
            block_descriptions = []
            for block_id in block_ids:
                if self.block_manager.is_block_available(block_id):
                    desc = self.block_manager.get_block_description(block_id)
                    block_descriptions.append(desc)

            context = "Предоставленные графические блоки:\n" + "\n".join(
                f"- {desc}" for desc in block_descriptions
            )

            # Show sent files in chat
            self.chat_widget.add_sent_images_message(found_paths)

            # Log files being sent
            self.api_log_widget.log_files_sent(found_paths, context)

            # Reset state and send to Answerer
            self._reset_query_state()
            self._send_to_answerer(
                question=question,
                file_paths=found_paths,
                context_message=context,
                iteration=1
            )
        else:
            self.chat_widget.add_system_message("No requested blocks available.")
            self._send_to_pro_model(question)

    def _send_rois_and_question(
        self,
        rois: list[RequestedROI],
        question: str,
        iteration: int = 1
    ):
        """Render ROIs as PNG crops and send to Pro model."""
        if not self.block_manager:
            self.chat_widget.add_system_message("Block manager not initialized.")
            self._send_to_pro_model(question)
            return

        # Get block paths for all ROIs
        block_ids = list(set(roi.block_id for roi in rois))
        found_paths_list, not_found_ids = self.block_manager.get_block_files_for_ids(block_ids)

        if not_found_ids:
            self.chat_widget.add_system_message(
                f"Blocks not found for ROI: {', '.join(not_found_ids)}"
            )

        # Build block_id -> path mapping
        block_paths = {}
        for block_id in block_ids:
            if self.block_manager.is_block_available(block_id):
                block_file = self.block_manager.get_block_file(block_id)
                if block_file:
                    block_paths[block_id] = block_file.file_path

        if not block_paths:
            self.chat_widget.add_system_message("No blocks available for ROI rendering.")
            self._send_to_pro_model(question)
            return

        # Render and crop ROIs
        self.chat_widget.add_system_message(f"Rendering {len(rois)} ROI(s)...")

        try:
            evidence_paths, render_warnings = self.evidence_manager.gather_evidence_for_rois(
                rois=rois,
                block_paths=block_paths,
                include_full_page=False
            )
            if render_warnings:
                for warning in render_warnings:
                    self.chat_widget.add_system_message(f"ROI warning: {warning}")
                    self.api_log_widget.add_log_entry("ROI_RENDER_WARNING", {"message": warning})
        except Exception as e:
            self.chat_widget.add_system_message(f"ROI rendering error: {e}")
            self.api_log_widget.log_error(f"ROI rendering error: {e}")
            self._send_blocks_and_question(block_ids, question)
            return

        if not evidence_paths:
            self.chat_widget.add_system_message("No evidence could be rendered.")
            self._send_to_pro_model(question)
            return

        # Log ROI rendering
        rois_info = [
            {
                "block_id": roi.block_id,
                "page": roi.page,
                "dpi": roi.dpi,
                "bbox": f"({roi.bbox_norm.x0:.2f},{roi.bbox_norm.y0:.2f})-({roi.bbox_norm.x1:.2f},{roi.bbox_norm.y1:.2f})",
            }
            for roi in rois
        ]
        evidence_str_paths = [str(p) for p in evidence_paths]
        self.api_log_widget.log_rois_rendered(rois_info, evidence_str_paths)

        # Build context message
        roi_descriptions = []
        for roi in rois:
            desc = f"ROI from block {roi.block_id}, page {roi.page}"
            if roi.reason:
                desc += f": {roi.reason}"
            roi_descriptions.append(desc)

        context = "Предоставленные области интереса (ROI):\n"
        context += "\n".join(f"- {desc}" for desc in roi_descriptions)
        context += "\n\nЭто увеличенные фрагменты чертежей для детального анализа."

        # Show sent evidence in chat
        self.chat_widget.add_sent_images_message(evidence_str_paths)
        self.api_log_widget.log_evidence_sent(evidence_str_paths, evidence_type="crops")

        if iteration == 1:
            self._reset_query_state()

        self._send_to_answerer(
            question=question,
            image_paths=evidence_str_paths,
            context_message=context,
            iteration=iteration
        )

    def _validate_block_ids(self, block_ids: list[str]) -> tuple[list[str], list[str]]:
        """Validate block IDs before sending to Answerer."""
        if not self.block_manager:
            return [], block_ids

        valid_ids = []
        invalid_ids = []

        for block_id in block_ids:
            if self.block_manager.is_block_available(block_id):
                valid_ids.append(block_id)
            else:
                invalid_ids.append(block_id)

        return valid_ids, invalid_ids

    # =========================================================================
    # Answer Handlers
    # =========================================================================

    def _on_answer_received(self, answer: Answer, raw_json: str, question: str, iteration: int, usage: dict = None):
        """Handle answer from Pro model (Answerer)."""
        usage = usage or {}
        self.chat_widget.set_loading(False)

        # Log the answer response with usage
        self.api_log_widget.log_answer_response(
            answer_data=answer.model_dump(),
            raw_json=raw_json,
            iteration=iteration,
            usage=usage
        )

        # Display answer with citations and token counts
        citations_dicts = [c.model_dump() for c in answer.citations]
        self.chat_widget.add_answer_with_citations(
            answer_text=answer.answer_markdown,
            citations=citations_dicts,
            confidence=answer.confidence,
            thoughts=usage.get("thought_text"),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0)
        )

        # Check if needs more evidence and haven't exceeded max iterations
        if answer.needs_more_evidence and iteration < self.MAX_ANSWER_ITERATIONS:
            self._process_followup_requests(answer, question, iteration)
        else:
            # Final answer - update conversation memory
            self.conversation_memory.add_user_turn(question)
            self.conversation_memory.add_assistant_turn(answer.answer_markdown)

            # Log conversation memory state
            self.api_log_widget.log_conversation_memory_state(
                self.conversation_memory.get_stats()
            )

            # Trigger background summarization if needed
            if self.conversation_memory.should_update_summary():
                self._trigger_summarization()

            if answer.needs_more_evidence:
                self.chat_widget.add_system_message(
                    f"Max iterations ({self.MAX_ANSWER_ITERATIONS}) reached. Answer may be incomplete."
                )
            self._reset_query_state()

    def _on_answer_error(self, error: str):
        """Handle error from Answerer."""
        self.chat_widget.set_loading(False)
        self.chat_widget.add_system_message(f"Answer error: {error}")
        self.api_log_widget.log_error(f"Answer error: {error}")
        self._reset_query_state()

    def _process_followup_requests(self, answer: Answer, question: str, current_iteration: int):
        """Process followup requests from the answer."""
        next_iteration = current_iteration + 1

        self.chat_widget.add_followup_notice(next_iteration, self.MAX_ANSWER_ITERATIONS)

        # Check for followup ROIs first (higher priority - zoomed details)
        if answer.followup_rois:
            rois = [
                RequestedROI(
                    block_id=roi.block_id,
                    page=roi.page,
                    bbox_norm=roi.bbox_norm,
                    dpi=roi.dpi,
                    reason=roi.reason
                )
                for roi in answer.followup_rois
            ]
            self._send_rois_and_question(rois, question, iteration=next_iteration)

        elif answer.followup_blocks:
            block_ids = [b.block_id for b in answer.followup_blocks]
            self._send_followup_blocks(block_ids, question, next_iteration)

        else:
            self.chat_widget.add_system_message(
                "Model indicated need for more evidence but didn't specify what."
            )
            self._reset_query_state()

    def _send_followup_blocks(self, block_ids: list[str], question: str, iteration: int):
        """Send followup block requests."""
        if not self.block_manager:
            self.chat_widget.add_system_message("Block manager not initialized.")
            self._reset_query_state()
            return

        found_paths, not_found_ids = self.block_manager.get_block_files_for_ids(block_ids)

        if not_found_ids:
            self.chat_widget.add_system_message(
                f"Followup blocks not found: {', '.join(not_found_ids)}"
            )

        if found_paths:
            block_descriptions = []
            for block_id in block_ids:
                if self.block_manager.is_block_available(block_id):
                    desc = self.block_manager.get_block_description(block_id)
                    block_descriptions.append(desc)

            context = "Дополнительные графические блоки:\n" + "\n".join(
                f"- {desc}" for desc in block_descriptions
            )

            self.chat_widget.add_sent_images_message(found_paths)
            self.api_log_widget.log_files_sent(found_paths, context)

            self._send_to_answerer(
                question=question,
                file_paths=found_paths,
                context_message=context,
                iteration=iteration
            )
        else:
            self.chat_widget.add_system_message("No followup blocks available.")
            self._reset_query_state()

    # =========================================================================
    # Summarization Handlers
    # =========================================================================

    def _trigger_summarization(self):
        """Trigger background summarization of conversation history."""
        from workers import SummarizerWorker

        if self.summarizer_worker and self.summarizer_worker.isRunning():
            return

        old_summary_length = len(self.conversation_memory.summary)

        self.summarizer_worker = SummarizerWorker(
            self.summarizer,
            self.conversation_memory,
        )
        self.summarizer_worker.signals.finished.connect(
            lambda summary, turns: self._on_summary_finished(
                summary, turns, old_summary_length
            )
        )
        self.summarizer_worker.signals.error.connect(self._on_summary_error)
        self.summarizer_worker.start()

    def _on_summary_finished(self, new_summary: str, turns_summarized: int, old_length: int):
        """Handle completed summarization."""
        if turns_summarized > 0:
            self.conversation_memory.update_summary(new_summary)
            self.api_log_widget.log_summary_update(
                old_summary_length=old_length,
                new_summary_length=len(new_summary),
                turns_summarized=turns_summarized,
            )

    def _on_summary_error(self, error: str):
        """Handle summarization error."""
        self.api_log_widget.log_error(f"Summarization error: {error}")

    # =========================================================================
    # Response Handlers (Legacy Chat Mode)
    # =========================================================================

    def _on_response_received(self, response: "ModelResponse"):
        """Handle response from Gemini."""
        from workers import SendFilesWorker

        self.chat_widget.set_loading(False)
        self.chat_widget.add_model_message(response.text, thoughts=response.thoughts)

        self.api_log_widget.log_response(
            text=response.text,
            needs_blocks=response.needs_blocks,
            needs_images=response.needs_images,
            requested_blocks=response.requested_blocks if response.needs_blocks else None,
            requested_images=response.requested_images if response.needs_images else None,
            thoughts=response.thoughts
        )

        if response.needs_blocks and response.requested_blocks:
            requested_ids = [r.block_id for r in response.requested_blocks]
            self.chat_widget.add_system_message(
                f"Модель запрашивает блоки: {', '.join(requested_ids)}"
            )
            self._send_requested_blocks(requested_ids)

    def _send_requested_blocks(self, block_ids: list[str]) -> None:
        """Send requested document blocks to the model."""
        if not self.block_manager:
            self.chat_widget.add_system_message(
                "Система документов не инициализирована."
            )
            return

        found_paths, not_found_ids = self.block_manager.get_block_files_for_ids(block_ids)

        if not_found_ids:
            self.chat_widget.add_system_message(
                f"Блоки не найдены: {', '.join(not_found_ids)}"
            )

        if found_paths:
            block_descriptions = []
            for block_id in block_ids:
                if self.block_manager.is_block_available(block_id):
                    desc = self.block_manager.get_block_description(block_id)
                    block_descriptions.append(desc)

            context = "Вот запрошенные графические блоки:\n" + "\n".join(
                f"- {desc}" for desc in block_descriptions
            ) + "\n\nПроанализируй эти изображения и дай полный ответ на вопрос пользователя."

            self.chat_widget.add_sent_images_message(found_paths)
            self._send_block_files(found_paths, context)
        else:
            self.chat_widget.add_system_message(
                "Ни один из запрошенных блоков не найден."
            )

    def _send_block_files(self, file_paths: list[str], context: str = "") -> None:
        """Send block files to the model."""
        from workers import SendFilesWorker

        self.chat_widget.set_loading(True)
        self.api_log_widget.log_files_sent(file_paths, context)

        self.current_worker = SendFilesWorker(
            self.gemini_client,
            file_paths,
            context
        )
        self.current_worker.signals.finished.connect(self._on_response_received)
        self.current_worker.signals.error.connect(self._on_error)
        self.current_worker.start()

    def _on_error(self, error: str):
        """Handle error."""
        self.chat_widget.set_loading(False)
        self.chat_widget.add_system_message(f"Error: {error}")
        self.api_log_widget.log_error(error)
        QMessageBox.warning(self, "Error", error)

    # =========================================================================
    # User ROI Handler
    # =========================================================================

    def _on_user_roi_selected(
        self,
        image_path: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float
    ):
        """Handle ROI selection from user via ImageViewer."""
        self.api_log_widget.add_log_entry("USER_ROI_SELECTED", {
            "image_path": image_path,
            "bbox": f"({x0:.3f}, {y0:.3f}) - ({x1:.3f}, {y1:.3f})",
        })

        if not self._current_question:
            self.chat_widget.add_system_message(
                "Область выбрана. Задайте вопрос для анализа этой области."
            )
            self._pending_user_roi = {
                "image_path": image_path,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
            }
            return

        self.chat_widget.add_system_message("Добавление выбранной области в запрос...")

        if os.path.exists(image_path):
            self._send_to_answerer(
                question=self._current_question,
                image_paths=[image_path],
                context_message=f"Пользователь выбрал дополнительную область для анализа: ({x0:.2f}, {y0:.2f}) - ({x1:.2f}, {y1:.2f})",
                iteration=self._current_iteration + 1
            )

    # =========================================================================
    # Block Indexing Handlers
    # =========================================================================

    def _build_block_index(self) -> None:
        """Start building block index in background."""
        from workers import IndexWorker

        if not self.loaded_crops_dir:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите папку с кропами")
            return

        if self.index_worker and self.index_worker.isRunning():
            QMessageBox.warning(self, "Ошибка", "Индексация уже выполняется")
            return

        pdf_count = len(list(Path(self.loaded_crops_dir).glob("*.pdf")))

        if pdf_count == 0:
            QMessageBox.warning(self, "Ошибка", "Папка не содержит PDF файлов")
            return

        self.api_log_widget.log_indexing_start(self.loaded_crops_dir, pdf_count)

        self.build_index_btn.setEnabled(False)
        self.build_index_btn.setText("Индексация...")
        self.chat_widget.add_system_message(f"Начало индексации {pdf_count} блоков...")

        output_path = str(self._get_index_path())

        self.index_worker = IndexWorker(
            self.block_indexer,
            self.loaded_crops_dir,
            output_path,
        )
        self.index_worker.signals.progress.connect(self._on_index_progress)
        self.index_worker.signals.error.connect(self._on_index_error)
        self.index_worker.signals.finished.connect(self._on_index_finished)
        self.index_worker.start()

    def _on_index_progress(self, indexed: int, total: int, message: str) -> None:
        """Handle indexing progress update."""
        self.api_log_widget.log_indexing_progress(indexed, total, message)

        percent = round(indexed / total * 100) if total > 0 else 0
        self.build_index_btn.setText(f"Индексация... {percent}%")
        self.index_status_label.setText(f"Индексация: {indexed}/{total} ({message})")

    def _on_index_error(self, block_ids: str, error: str) -> None:
        """Handle indexing error for specific blocks."""
        self.api_log_widget.log_indexing_error(block_ids, error)
        self.chat_widget.add_system_message(f"Ошибка индексации [{block_ids}]: {error}")

    def _on_index_finished(self, index: Optional[BlockIndex]) -> None:
        """Handle indexing completion."""
        self.build_index_btn.setEnabled(True)
        self.build_index_btn.setText("Построить индекс блоков")

        if index:
            self.block_index = index

            self.api_log_widget.log_indexing_complete(
                total_blocks=index.total_blocks,
                indexed_blocks=index.indexed_blocks,
                failed_blocks=len(index.failed_blocks),
                output_path=str(self._get_index_path()),
            )

            self._update_index_status()
            self.planner.set_block_index(self.block_index)
            self.chat_widget.add_system_message(
                f"Индексация завершена: {index.indexed_blocks}/{index.total_blocks} блоков"
            )

            if index.failed_blocks:
                self.chat_widget.add_system_message(
                    f"Не удалось проиндексировать: {', '.join(index.failed_blocks[:5])}"
                    + (f" и ещё {len(index.failed_blocks) - 5}" if len(index.failed_blocks) > 5 else "")
                )
        else:
            self.chat_widget.add_system_message("Индексация завершилась с ошибкой")

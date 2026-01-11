"""Answerer module for generating structured answers using Gemini Pro."""

import json
import os
import time
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING

from google import genai
from google.genai import types

from config import Config
from schemas import Answer, ANSWER_JSON_SCHEMA
from token_utils import (
    estimate_tokens,
    estimate_tokens_detailed,
    truncate_context_smart,
    get_model_token_limit,
    estimate_media_tokens,
)
from file_utils import create_file_part, create_image_part
from api_utils import execute_with_retry
from thinking_context import ThinkingContext

if TYPE_CHECKING:
    from document_parser import DocumentParser
    from conversation_memory import ConversationMemory


ANSWERER_SYSTEM_PROMPT = """Ты - эксперт по анализу проектной документации в области противопожарной безопасности и инженерных систем.

## Твоя задача:
Проанализировать предоставленные материалы (текст документации и/или изображения чертежей) и дать структурированный ответ на вопрос пользователя.

## Правила ответа:

1. **answer_markdown**: Полный, структурированный ответ на русском языке.
   - Используй Markdown для форматирования (заголовки, списки, таблицы где уместно).
   - Ссылайся на конкретные элементы документации.
   - Будь точен и конкретен.

2. **citations**: Указывай источники информации.
   - kind: "text_block" для текстовых блоков, "image_block" для графических.
   - id: ID блока из документации.
   - page: номер страницы (если известен).
   - note: краткое пояснение, что именно цитируется.

3. **needs_more_evidence**: Установи true только если:
   - Вопрос требует информации, которой нет в предоставленных материалах.
   - Нужен более детальный анализ конкретной области чертежа.
   - Ответ будет значительно полнее с дополнительными блоками.

4. **followup_blocks/followup_rois**: Если needs_more_evidence=true:
   - Укажи конкретные блоки или области, которые нужны.
   - Обоснуй почему они необходимы.

5. **confidence**: Оцени уверенность в ответе:
   - "high": Ответ полный и точный, все данные найдены.
   - "medium": Ответ корректный, но возможны уточнения.
   - "low": Информации недостаточно для полного ответа.

## Контекст документации:

{document_context}

## Список доступных блоков:

{image_blocks_summary}

## История диалога:

{conversation_context}

---

Проанализируй вопрос и предоставленные материалы, затем дай структурированный ответ в формате JSON.
"""


class Answerer:
    """Generates structured answers using Gemini Pro model."""

    MODEL_NAME = "gemini-3-pro-preview"  # Pro model for quality answers

    def __init__(
        self,
        config: Config,
        parser: Optional["DocumentParser"] = None,
        conversation_memory: Optional["ConversationMemory"] = None,
        media_resolution: str = "MEDIA_RESOLUTION_MEDIUM",
        thinking_context: Optional[ThinkingContext] = None,
    ):
        """Initialize answerer.

        Args:
            config: Application configuration with API key.
            parser: Optional document parser for context.
            conversation_memory: Optional conversation memory for context.
            media_resolution: Media resolution setting for images.
            thinking_context: Optional thinking context for maintaining reasoning continuity.
        """
        self.config = config
        self.parser = parser
        self.conversation_memory = conversation_memory
        self.media_resolution = media_resolution
        self.thinking_context = thinking_context or ThinkingContext()
        self.client = genai.Client(api_key=config.api_key)

    def set_parser(self, parser: "DocumentParser") -> None:
        """Set or update the document parser."""
        self.parser = parser

    def set_conversation_memory(self, memory: "ConversationMemory") -> None:
        """Set or update the conversation memory."""
        self.conversation_memory = memory

    def set_media_resolution(self, resolution: str) -> None:
        """Set media resolution for image processing.

        Args:
            resolution: One of MEDIA_RESOLUTION_LOW, MEDIA_RESOLUTION_MEDIUM, MEDIA_RESOLUTION_HIGH
        """
        self.media_resolution = resolution

    def set_thinking_context(self, context: ThinkingContext) -> None:
        """Set or update the thinking context."""
        self.thinking_context = context

    def _build_system_prompt(
        self,
        image_count: int = 0,
        file_count: int = 0,
    ) -> str:
        """Build system prompt with document and conversation context.

        Args:
            image_count: Number of images being sent (for token budget).
            file_count: Number of PDF files being sent (for token budget).

        Returns:
            Formatted system prompt string.
        """
        # Get model token limit and calculate budget
        model_limit = get_model_token_limit(self.MODEL_NAME)

        # Estimate media tokens
        media_tokens = estimate_media_tokens(
            image_count=image_count,
            file_count=file_count,
            resolution=self.media_resolution,
        )

        # Reserve tokens for: response (8192) + user question (~500) + media + overhead
        available_context_tokens = model_limit - 8192 - 500 - media_tokens

        # Document context
        if not self.parser:
            document_context = "Документ не загружен."
            image_blocks_summary = "Блоки недоступны."
        else:
            document_context = self.parser.get_document_context()
            image_blocks_summary = self.parser.get_image_blocks_summary()

        # Conversation context
        if self.conversation_memory:
            conversation_context = self.conversation_memory.get_context_for_model()
            if not conversation_context:
                conversation_context = "Новый диалог, история отсутствует."
        else:
            conversation_context = "Новый диалог, история отсутствует."

        # Calculate current token usage for static parts
        static_parts_tokens = estimate_tokens(
            image_blocks_summary + ANSWERER_SYSTEM_PROMPT
        )
        remaining_tokens = max(10000, available_context_tokens - static_parts_tokens)

        # Smart truncation: allocate 70% to document, 30% to conversation
        document_context, conversation_context = truncate_context_smart(
            document_context,
            conversation_context,
            max_total_tokens=remaining_tokens,
            doc_priority=0.7,
        )

        return ANSWERER_SYSTEM_PROMPT.format(
            document_context=document_context,
            image_blocks_summary=image_blocks_summary,
            conversation_context=conversation_context,
        )

    def answer(
        self,
        question: str,
        image_paths: Optional[list[Union[str, Path]]] = None,
        file_paths: Optional[list[Union[str, Path]]] = None,
        context_message: Optional[str] = None,
        iteration: int = 1,
    ) -> Answer:
        """Generate a structured answer to the question.

        Args:
            question: User's question to answer.
            image_paths: Optional list of PNG image paths (ROI crops, etc.).
            file_paths: Optional list of PDF file paths (full blocks).
            context_message: Optional additional context about provided materials.
            iteration: Current iteration number (for multi-step answering).

        Returns:
            Answer object with structured response.

        Raises:
            ValueError: If answering fails or returns invalid response.
        """
        image_paths = image_paths or []
        file_paths = file_paths or []

        # Build system prompt with token budget consideration
        system_prompt = self._build_system_prompt(
            image_count=len(image_paths),
            file_count=len(file_paths),
        )

        # Build content list
        contents = []

        # Add images first (PNG crops)
        for path in image_paths:
            if os.path.exists(path):
                contents.append(create_image_part(path))

        # Add files (PDFs)
        for path in file_paths:
            if os.path.exists(path):
                contents.append(create_file_part(path))

        # Build user prompt
        user_prompt = f"Вопрос пользователя: {question}"
        if context_message:
            user_prompt += f"\n\n{context_message}"
        if iteration > 1:
            user_prompt += f"\n\n[Это итерация {iteration} из 3. Постарайся дать максимально полный ответ с имеющимися данными.]"

        contents.append(user_prompt)

        # Configure generation with JSON schema and media resolution
        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=1.0,  # Fixed at 1.0 as per requirements
            top_p=0.95,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=ANSWER_JSON_SCHEMA,
            media_resolution=self.media_resolution,
        )

        try:
            # Execute with retry
            response_text = execute_with_retry(
                self.client, self.MODEL_NAME, contents, gen_config
            )

            try:
                answer_dict = json.loads(response_text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON response from answerer: {e}")

            # Validate and create Answer object
            answer = Answer.model_validate(answer_dict)

            return answer

        except Exception as e:
            # Return a fallback answer
            return Answer(
                answer_markdown=f"Произошла ошибка при формировании ответа: {str(e)}",
                citations=[],
                needs_more_evidence=False,
                followup_blocks=[],
                followup_rois=[],
                confidence="low"
            )

    def answer_with_raw_response(
        self,
        question: str,
        image_paths: Optional[list[Union[str, Path]]] = None,
        file_paths: Optional[list[Union[str, Path]]] = None,
        context_message: Optional[str] = None,
        iteration: int = 1,
    ) -> tuple[Answer, str, dict]:
        """Generate an answer and return parsed Answer, raw response, and usage metadata.

        Useful for logging and debugging.

        Returns:
            Tuple of (Answer object, raw JSON response string, usage dict).
            Usage dict contains full logging data including:
            - input_tokens, output_tokens, total_tokens, thoughts_tokens
            - duration_ms: execution time in milliseconds
            - system_prompt_full: complete system prompt
            - user_prompt_full: complete user prompt
            - files_info: details about files sent
            - images_info: details about images sent
            - model: model name
            - thought_text: extracted thinking text
        """
        image_paths = image_paths or []
        file_paths = file_paths or []

        # Build system prompt with token budget consideration
        system_prompt = self._build_system_prompt(
            image_count=len(image_paths),
            file_count=len(file_paths),
        )

        contents = []

        # Track files info for logging
        files_info = []
        images_info = []

        for path in image_paths:
            str_path = str(path)
            if os.path.exists(str_path):
                contents.append(create_image_part(str_path))
                images_info.append({
                    "path": str_path,
                    "name": os.path.basename(str_path),
                    "size_bytes": os.path.getsize(str_path),
                })

        for path in file_paths:
            str_path = str(path)
            if os.path.exists(str_path):
                contents.append(create_file_part(str_path))
                files_info.append({
                    "path": str_path,
                    "name": os.path.basename(str_path),
                    "size_bytes": os.path.getsize(str_path),
                })

        user_prompt = f"Вопрос пользователя: {question}"
        if context_message:
            user_prompt += f"\n\n{context_message}"
        if iteration > 1:
            user_prompt += f"\n\n[Это итерация {iteration} из 3. Постарайся дать максимально полный ответ с имеющимися данными.]"

        contents.append(user_prompt)

        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=1.0,  # Fixed at 1.0
            top_p=0.95,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=ANSWER_JSON_SCHEMA,
            media_resolution=self.media_resolution,
            # Enable thinking mode for better reasoning
            thinking_config=types.ThinkingConfig(
                include_thoughts=True,
                thinking_level="high",  # Gemini 3 Pro - high quality reasoning
            ),
        )

        # Initialize usage dict with full logging data
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "thoughts_tokens": 0,
            "duration_ms": 0.0,
            "system_prompt_full": system_prompt,
            "system_prompt_length": len(system_prompt),
            "user_prompt_full": user_prompt,
            "user_prompt_length": len(user_prompt),
            "files_info": files_info,
            "images_info": images_info,
            "files_count": len(files_info),
            "images_count": len(images_info),
            "model": self.MODEL_NAME,
            "media_resolution": self.media_resolution,
            "iteration": iteration,
            "thought_text": None,
            "thought_signature": None,
            "response_raw": None,
        }

        # Start timing
        start_time = time.time()

        try:
            # Execute API call directly to get full response
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=contents,
                config=gen_config,
            )

            # Calculate duration
            usage["duration_ms"] = (time.time() - start_time) * 1000

            # Extract usage metadata
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage["input_tokens"] = response.usage_metadata.prompt_token_count or 0
                usage["output_tokens"] = response.usage_metadata.candidates_token_count or 0
                usage["total_tokens"] = response.usage_metadata.total_token_count or 0
                if hasattr(response.usage_metadata, 'thoughts_token_count'):
                    usage["thoughts_tokens"] = response.usage_metadata.thoughts_token_count or 0

            # Extract thoughts and signature from response
            thought_text = self.thinking_context.add_from_response(response)
            if thought_text:
                usage["thought_text"] = thought_text
            if self.thinking_context.get_latest_signature():
                usage["thought_signature"] = self.thinking_context.get_latest_signature()

            response_text = response.text.strip()
            usage["response_raw"] = response_text

            answer_dict = json.loads(response_text)
            answer = Answer.model_validate(answer_dict)

            return answer, response_text, usage

        except Exception as e:
            # Calculate duration even on error
            usage["duration_ms"] = (time.time() - start_time) * 1000
            usage["error"] = str(e)

            fallback_answer = Answer(
                answer_markdown=f"Произошла ошибка: {str(e)}",
                citations=[],
                needs_more_evidence=False,
                followup_blocks=[],
                followup_rois=[],
                confidence="low"
            )
            fallback_json = fallback_answer.model_dump_json(indent=2)
            usage["response_raw"] = fallback_json
            return fallback_answer, fallback_json, usage

    def get_context_stats(self, image_paths: list = None, file_paths: list = None) -> dict:
        """Get statistics about the context being sent.

        Args:
            image_paths: List of image paths to be sent.
            file_paths: List of file paths to be sent.

        Returns:
            Dictionary with context size and media information.
        """
        image_paths = image_paths or []
        file_paths = file_paths or []

        system_prompt = self._build_system_prompt(
            image_count=len(image_paths),
            file_count=len(file_paths),
        )

        # Use improved token estimation
        token_details = estimate_tokens_detailed(system_prompt)
        media_tokens = estimate_media_tokens(
            image_count=len(image_paths),
            file_count=len(file_paths),
            resolution=self.media_resolution,
        )

        # Calculate media info
        media_info = []
        total_media_size = 0

        for path in image_paths:
            if os.path.exists(path):
                size = os.path.getsize(path)
                total_media_size += size
                media_info.append({
                    "type": "image",
                    "name": os.path.basename(path),
                    "size_kb": size // 1024,
                })

        for path in file_paths:
            if os.path.exists(path):
                size = os.path.getsize(path)
                total_media_size += size
                media_info.append({
                    "type": "file",
                    "name": os.path.basename(path),
                    "size_kb": size // 1024,
                })

        return {
            "system_prompt_length": len(system_prompt),
            "estimated_text_tokens": token_details["estimated_tokens"],
            "estimated_media_tokens": media_tokens,
            "total_estimated_tokens": token_details["estimated_tokens"] + media_tokens,
            "model_limit": get_model_token_limit(self.MODEL_NAME),
            "token_details": token_details,
            "media_resolution": self.media_resolution,
            "images_count": len(image_paths),
            "files_count": len(file_paths),
            "total_media_size_kb": total_media_size // 1024,
            "media_files": media_info,
            "has_conversation_memory": self.conversation_memory is not None,
            "conversation_turns": (
                len(self.conversation_memory.turns)
                if self.conversation_memory else 0
            ),
        }

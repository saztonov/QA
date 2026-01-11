"""Planner module for structured query planning using Gemini Flash."""

import json
import time
from typing import Optional, TYPE_CHECKING

from google import genai
from google.genai import types

from config import Config
from schemas import Plan, PlanDecision, PLAN_JSON_SCHEMA
from token_utils import (
    estimate_tokens,
    estimate_tokens_detailed,
    truncate_to_token_limit,
    truncate_context_smart,
    get_model_token_limit,
)
from api_utils import execute_with_retry

if TYPE_CHECKING:
    from document_parser import DocumentParser
    from conversation_memory import ConversationMemory
    from block_indexer import BlockIndex


PLANNER_SYSTEM_PROMPT = """Ты - планировщик запросов для системы анализа строительной документации.

## Твоя задача:
Проанализировать вопрос пользователя и определить, какие ресурсы нужны для ответа.

## Доступные решения (decision):

1. **ANSWER_FROM_TEXT** - Вопрос можно полностью ответить на основе текстового контекста документации.
   Используй когда: вопрос про общую информацию, содержание документа, текстовые описания.

2. **NEED_BLOCKS** - Для ответа нужно изучить графические блоки (чертежи, схемы, планы).
   Используй когда: вопрос про визуальные элементы, расположение, размеры, конструкции на чертежах.
   Указывай конкретные block_id из списка доступных блоков.

3. **NEED_ZOOM_ROI** - Нужно детально рассмотреть конкретную область на чертеже.
   Используй когда: нужна высокая детализация конкретного узла или области.
   Указывай block_id, координаты области (bbox_norm в диапазоне 0.0-1.0) и желаемый DPI.

4. **ASK_USER** - Вопрос неясен или требует уточнения.
   Используй когда: вопрос неоднозначный, слишком общий, или не хватает контекста.

## Правила:

- Всегда выбирай МИНИМАЛЬНО необходимое количество блоков (не больше 3-5).
- Приоритизируй блоки: high - критически важные, medium - полезные, low - дополнительные.
- В reasoning кратко объясни свой выбор (1-2 предложения).
- Если вопрос простой и ответ есть в тексте - выбирай ANSWER_FROM_TEXT.
- Для вопросов о противопожарных системах обычно нужны планы этажей.
- Для вопросов о конструкциях - разрезы и узлы.

## Доступная документация:

{document_context}

## Список доступных графических блоков:

{image_blocks_summary}

## Индекс блоков (детальные описания):

{block_index_summary}

## История диалога:

{conversation_context}

---

Проанализируй вопрос и верни JSON с планом действий.
"""


class Planner:
    """Plans query execution using Gemini Flash with structured outputs."""

    MODEL_NAME = "gemini-3-flash-preview"  # Fast model for planning

    def __init__(
        self,
        config: Config,
        parser: Optional["DocumentParser"] = None,
        conversation_memory: Optional["ConversationMemory"] = None,
        block_index: Optional["BlockIndex"] = None,
    ):
        """Initialize planner.

        Args:
            config: Application configuration with API key.
            parser: Optional document parser for context.
            conversation_memory: Optional conversation memory for context.
            block_index: Optional block index with detailed descriptions.
        """
        self.config = config
        self.parser = parser
        self.conversation_memory = conversation_memory
        self.block_index = block_index
        self.client = genai.Client(api_key=config.api_key)

    def set_parser(self, parser: "DocumentParser") -> None:
        """Set or update the document parser."""
        self.parser = parser

    def set_conversation_memory(self, memory: "ConversationMemory") -> None:
        """Set or update the conversation memory."""
        self.conversation_memory = memory

    def set_block_index(self, index: "BlockIndex") -> None:
        """Set or update the block index."""
        self.block_index = index

    def _build_system_prompt(self) -> str:
        """Build system prompt with document, block index, and conversation context."""
        # Get model token limit and calculate budget
        model_limit = get_model_token_limit(self.MODEL_NAME)
        # Reserve tokens for: response (2048) + user question (~500) + overhead
        available_context_tokens = model_limit - 3000

        # Document context
        if not self.parser:
            document_context = "Документ не загружен."
            image_blocks_summary = "Блоки недоступны."
        else:
            document_context = self.parser.get_document_context()
            image_blocks_summary = self.parser.get_image_blocks_summary()

        # Block index summary (detailed descriptions from indexer)
        if self.block_index and self.block_index.indexed_blocks > 0:
            block_index_summary = self.block_index.get_summary_for_planner()
        else:
            block_index_summary = "Индекс блоков не создан. Используй базовые описания из списка блоков выше."

        # Conversation context
        if self.conversation_memory:
            conversation_context = self.conversation_memory.get_context_for_model()
            if not conversation_context:
                conversation_context = "Новый диалог, история отсутствует."
        else:
            conversation_context = "Новый диалог, история отсутствует."

        # Calculate current token usage
        static_parts_tokens = estimate_tokens(
            image_blocks_summary + block_index_summary + PLANNER_SYSTEM_PROMPT
        )
        remaining_tokens = available_context_tokens - static_parts_tokens

        # Smart truncation: allocate 70% to document, 30% to conversation
        document_context, conversation_context = truncate_context_smart(
            document_context,
            conversation_context,
            max_total_tokens=remaining_tokens,
            doc_priority=0.7,
        )

        return PLANNER_SYSTEM_PROMPT.format(
            document_context=document_context,
            image_blocks_summary=image_blocks_summary,
            block_index_summary=block_index_summary,
            conversation_context=conversation_context,
        )

    def plan(self, question: str) -> Plan:
        """Create a plan for answering the question.

        Args:
            question: User's question to analyze.

        Returns:
            Plan object with decision and requested resources.

        Raises:
            ValueError: If planning fails or returns invalid response.
        """
        system_prompt = self._build_system_prompt()

        # Configure generation with JSON schema
        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=1.0,  # Fixed at 1.0 as per requirements
            top_p=0.95,
            max_output_tokens=2048,
            response_mime_type="application/json",
            response_schema=PLAN_JSON_SCHEMA,
        )

        user_prompt = f"Вопрос пользователя: {question}"

        try:
            # Execute with retry
            response_text = execute_with_retry(
                self.client, self.MODEL_NAME, user_prompt, gen_config
            )

            # Try to parse as JSON
            try:
                plan_dict = json.loads(response_text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON response from planner: {e}")

            # Validate and create Plan object
            plan = Plan.model_validate(plan_dict)

            # Validate block IDs if parser is available
            if self.parser and plan.requested_blocks:
                available_ids = set(self.parser.get_all_image_block_ids())
                valid_blocks = []
                for block in plan.requested_blocks:
                    if block.block_id in available_ids:
                        valid_blocks.append(block)
                    else:
                        print(f"Warning: Requested block {block.block_id} not in available blocks - removed from plan")
                plan.requested_blocks = valid_blocks

            # Validate ROI block IDs as well
            if self.parser and plan.requested_rois:
                available_ids = set(self.parser.get_all_image_block_ids())
                valid_rois = []
                for roi in plan.requested_rois:
                    if roi.block_id in available_ids:
                        valid_rois.append(roi)
                    else:
                        print(f"Warning: ROI block {roi.block_id} not available - removed from plan")
                plan.requested_rois = valid_rois

            return plan

        except Exception as e:
            # Return a safe fallback plan
            return Plan(
                decision=PlanDecision.ANSWER_FROM_TEXT,
                reasoning=f"Planning failed: {str(e)}. Falling back to text-based answer.",
                requested_blocks=[],
                requested_rois=[],
                user_requests=[]
            )

    def plan_with_raw_response(self, question: str) -> tuple[Plan, str, dict]:
        """Create a plan and return parsed Plan, raw response, and usage metadata.

        Useful for logging and debugging.

        Args:
            question: User's question to analyze.

        Returns:
            Tuple of (Plan object, raw JSON response string, usage dict).
            Usage dict contains full logging data including:
            - input_tokens, output_tokens, total_tokens, thoughts_tokens
            - duration_ms: execution time in milliseconds
            - system_prompt_full: complete system prompt
            - user_prompt_full: complete user prompt
            - model: model name
            - thought_text: extracted thinking text
        """
        system_prompt = self._build_system_prompt()

        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=1.0,  # Fixed at 1.0
            top_p=0.95,
            max_output_tokens=2048,
            response_mime_type="application/json",
            response_schema=PLAN_JSON_SCHEMA,
            # Enable thinking mode for better reasoning
            thinking_config=types.ThinkingConfig(
                include_thoughts=True,
                thinking_level="medium",  # Flash - balance of speed and quality
            ),
        )

        user_prompt = f"Вопрос пользователя: {question}"

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
            "model": self.MODEL_NAME,
            "thought_text": None,
            "response_raw": None,
        }

        # Start timing
        start_time = time.time()

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=user_prompt,
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

            # Extract thoughts from response
            thoughts_parts = []
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, 'thought') and part.thought:
                                thoughts_parts.append(part.text)

            if thoughts_parts:
                usage["thought_text"] = "\n\n".join(thoughts_parts)

            response_text = response.text.strip()
            usage["response_raw"] = response_text

            plan_dict = json.loads(response_text)
            plan = Plan.model_validate(plan_dict)

            return plan, response_text, usage

        except Exception as e:
            # Calculate duration even on error
            usage["duration_ms"] = (time.time() - start_time) * 1000
            usage["error"] = str(e)

            fallback_plan = Plan(
                decision=PlanDecision.ANSWER_FROM_TEXT,
                reasoning=f"Planning failed: {str(e)}",
                requested_blocks=[],
                requested_rois=[],
                user_requests=[]
            )
            fallback_json = fallback_plan.model_dump_json(indent=2)
            usage["response_raw"] = fallback_json
            return fallback_plan, fallback_json, usage

    def get_context_stats(self) -> dict:
        """Get statistics about the context being sent.

        Returns:
            Dictionary with context size information.
        """
        system_prompt = self._build_system_prompt()
        token_details = estimate_tokens_detailed(system_prompt)

        return {
            "system_prompt_length": len(system_prompt),
            "estimated_tokens": token_details["estimated_tokens"],
            "token_details": token_details,
            "model_limit": get_model_token_limit(self.MODEL_NAME),
            "has_document": self.parser is not None,
            "has_conversation_memory": self.conversation_memory is not None,
            "conversation_turns": (
                len(self.conversation_memory.turns)
                if self.conversation_memory else 0
            ),
            "has_summary": (
                bool(self.conversation_memory.summary)
                if self.conversation_memory else False
            ),
            "has_block_index": self.block_index is not None,
            "indexed_blocks": (
                self.block_index.indexed_blocks
                if self.block_index else 0
            ),
        }

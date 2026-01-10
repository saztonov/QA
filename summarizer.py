"""Summarizer module for compressing conversation history using Gemini Flash."""

import json
from typing import Optional

from google import genai
from google.genai import types

from config import Config
from conversation_memory import ConversationMemory, Turn


SUMMARIZER_SYSTEM_PROMPT = """You are a conversation summarizer for a document Q&A system.

Your task is to create a concise summary of the conversation history that captures:
1. Key questions the user asked
2. Important findings and answers
3. Any document blocks or sections that were referenced
4. The current focus/topic of discussion

Keep the summary:
- Under 500 words
- In bullet point format
- Focused on information useful for continuing the conversation
- In the same language as the conversation (Russian if the conversation is in Russian)

Output only the summary, no additional text or formatting.
"""


SUMMARIZER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Concise bullet-point summary of conversation history"
        },
        "key_topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Main topics discussed"
        },
        "referenced_blocks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Document block IDs that were referenced"
        }
    },
    "required": ["summary", "key_topics", "referenced_blocks"]
}


class Summarizer:
    """Summarizes conversation history using Gemini Flash model."""

    MODEL_NAME = "gemini-3-flash-preview"

    def __init__(self, config: Config):
        """Initialize summarizer.

        Args:
            config: Application configuration with API key.
        """
        self.config = config
        self.client = genai.Client(api_key=config.api_key)

    def summarize(
        self,
        previous_summary: str,
        turns_to_summarize: list[Turn],
    ) -> str:
        """Create or update conversation summary.

        Args:
            previous_summary: Existing summary to update (empty for new).
            turns_to_summarize: New turns to incorporate into summary.

        Returns:
            Updated summary text.
        """
        if not turns_to_summarize:
            return previous_summary

        # Build prompt
        prompt_parts = []

        if previous_summary:
            prompt_parts.append(f"Previous summary:\n{previous_summary}")

        prompt_parts.append("New conversation turns to incorporate:")
        for turn in turns_to_summarize:
            role = "User" if turn.role == "user" else "Assistant"
            prompt_parts.append(f"{role}: {turn.content}")

        prompt_parts.append(
            "\nCreate an updated summary that combines the previous summary "
            "with the new information. Keep it concise and in bullet format."
        )

        user_prompt = "\n\n".join(prompt_parts)

        # Configure generation
        gen_config = types.GenerateContentConfig(
            system_instruction=SUMMARIZER_SYSTEM_PROMPT,
            temperature=1.0,  # Fixed at 1.0 as requested
            top_p=0.95,
            max_output_tokens=1024,
            response_mime_type="application/json",
            response_schema=SUMMARIZER_JSON_SCHEMA,
        )

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=user_prompt,
                config=gen_config,
            )

            response_text = response.text.strip()
            result = json.loads(response_text)

            # Return just the summary text
            return result.get("summary", previous_summary)

        except Exception as e:
            # On error, return previous summary unchanged
            print(f"Summarization error: {e}")
            return previous_summary

    def summarize_with_details(
        self,
        previous_summary: str,
        turns_to_summarize: list[Turn],
    ) -> tuple[str, list[str], list[str]]:
        """Create summary with additional metadata.

        Args:
            previous_summary: Existing summary to update.
            turns_to_summarize: New turns to incorporate.

        Returns:
            Tuple of (summary, key_topics, referenced_blocks).
        """
        if not turns_to_summarize:
            return previous_summary, [], []

        prompt_parts = []

        if previous_summary:
            prompt_parts.append(f"Previous summary:\n{previous_summary}")

        prompt_parts.append("New conversation turns to incorporate:")
        for turn in turns_to_summarize:
            role = "User" if turn.role == "user" else "Assistant"
            prompt_parts.append(f"{role}: {turn.content}")

        prompt_parts.append(
            "\nCreate an updated summary that combines the previous summary "
            "with the new information. Include key topics and referenced document blocks."
        )

        user_prompt = "\n\n".join(prompt_parts)

        gen_config = types.GenerateContentConfig(
            system_instruction=SUMMARIZER_SYSTEM_PROMPT,
            temperature=1.0,
            top_p=0.95,
            max_output_tokens=1024,
            response_mime_type="application/json",
            response_schema=SUMMARIZER_JSON_SCHEMA,
        )

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=user_prompt,
                config=gen_config,
            )

            response_text = response.text.strip()
            result = json.loads(response_text)

            return (
                result.get("summary", previous_summary),
                result.get("key_topics", []),
                result.get("referenced_blocks", []),
            )

        except Exception as e:
            print(f"Summarization error: {e}")
            return previous_summary, [], []

    def update_memory_summary(self, memory: ConversationMemory) -> str:
        """Update summary in a ConversationMemory object.

        Args:
            memory: The conversation memory to update.

        Returns:
            The new summary text.
        """
        turns_to_summarize = memory.get_turns_for_summarization()

        if not turns_to_summarize:
            return memory.summary

        new_summary = self.summarize(
            previous_summary=memory.summary,
            turns_to_summarize=turns_to_summarize,
        )

        memory.update_summary(new_summary)
        return new_summary

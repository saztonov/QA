"""Gemini API client module.

This module provides a client for interacting with the Gemini API
using structured outputs (JSON Schema) for reliable parsing.
"""

import json
import os
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from config import Config
from schemas import ChatResponse, CHAT_RESPONSE_JSON_SCHEMA
from file_utils import create_file_part, create_image_part

if TYPE_CHECKING:
    from model_settings_widget import GenerationConfig


@dataclass
class ImageRequest:
    """Represents a request for an image from the model."""

    filename: str
    description: str = ""


@dataclass
class BlockRequest:
    """Represents a request for a document block from the model."""

    block_id: str
    block_type: str = "IMAGE"  # IMAGE or TEXT
    reason: str = ""


@dataclass
class ChatMessage:
    """Represents a chat message."""

    role: str  # "user" or "model"
    text: str
    images: list[str] = field(default_factory=list)  # List of image paths
    files: list[str] = field(default_factory=list)  # List of file paths


@dataclass
class ModelResponse:
    """Response from the model."""

    text: str
    thoughts: Optional[str] = None  # Model's thinking/reasoning
    needs_images: bool = False
    requested_images: list[ImageRequest] = field(default_factory=list)
    needs_blocks: bool = False
    requested_blocks: list[BlockRequest] = field(default_factory=list)
    is_final: bool = True


class GeminiClient:
    """Client for interacting with Gemini API using structured JSON Schema outputs."""

    def __init__(self, config: Config):
        """Initialize Gemini client.

        Args:
            config: Application configuration with API key.
        """
        self.config = config
        self.client = genai.Client(api_key=config.api_key)
        self.chat: Optional[genai.chats.Chat] = None
        self.current_model = config.default_model
        self.history: list[ChatMessage] = []
        self.system_prompt: Optional[str] = None
        self.generation_config: Optional["GenerationConfig"] = None

    def set_generation_config(self, gen_config: Optional["GenerationConfig"]) -> None:
        """Set the generation configuration."""
        self.generation_config = gen_config
        self.chat = None  # Reset chat to apply new config

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        """Set the system prompt for the chat."""
        self.system_prompt = prompt
        self.chat = None  # Reset chat to apply new system prompt

    def set_model(self, model_name: str) -> None:
        """Set the model to use."""
        if model_name in self.config.available_models:
            self.current_model = model_name
            self.chat = None  # Reset chat when model changes

    def _parse_structured_response(self, response_text: str) -> ChatResponse:
        """Parse a JSON response into ChatResponse.

        Args:
            response_text: The raw JSON text from the model.

        Returns:
            ChatResponse object with parsed data.
        """
        try:
            response_dict = json.loads(response_text)
            return ChatResponse.model_validate(response_dict)
        except (json.JSONDecodeError, Exception):
            # Fallback: treat the whole response as text
            return ChatResponse(
                response_text=response_text,
                needs_blocks=False,
                requested_blocks=[],
                needs_images=False,
                requested_images=[],
                is_complete=True,
            )

    def _convert_to_model_response(
        self,
        chat_response: ChatResponse,
        thoughts: Optional[str] = None,
    ) -> ModelResponse:
        """Convert ChatResponse to ModelResponse.

        Args:
            chat_response: The parsed ChatResponse object.
            thoughts: Optional thinking/reasoning from the model.

        Returns:
            ModelResponse object.
        """
        # Convert block requests
        requested_blocks = [
            BlockRequest(
                block_id=br.block_id,
                block_type=br.block_type,
                reason=br.reason,
            )
            for br in chat_response.requested_blocks
        ]

        # Convert image requests
        requested_images = [
            ImageRequest(
                filename=ir.filename,
                description=ir.description,
            )
            for ir in chat_response.requested_images
        ]

        is_final = not chat_response.needs_blocks and not chat_response.needs_images

        return ModelResponse(
            text=chat_response.response_text,
            thoughts=thoughts,
            needs_images=chat_response.needs_images,
            requested_images=requested_images,
            needs_blocks=chat_response.needs_blocks,
            requested_blocks=requested_blocks,
            is_final=is_final,
        )

    def start_new_chat(self) -> None:
        """Start a new chat session."""
        config_dict = {"model": self.current_model}

        # Build GenerateContentConfig with all settings
        gen_config_kwargs = {}

        if self.system_prompt:
            gen_config_kwargs["system_instruction"] = self.system_prompt

        if self.generation_config:
            gen_config_kwargs["temperature"] = self.generation_config.temperature
            gen_config_kwargs["top_p"] = self.generation_config.top_p
            gen_config_kwargs["top_k"] = self.generation_config.top_k
            gen_config_kwargs["max_output_tokens"] = self.generation_config.max_output_tokens
            gen_config_kwargs["candidate_count"] = self.generation_config.candidate_count

            # Add penalties if non-zero
            if self.generation_config.presence_penalty != 0.0:
                gen_config_kwargs["presence_penalty"] = self.generation_config.presence_penalty
            if self.generation_config.frequency_penalty != 0.0:
                gen_config_kwargs["frequency_penalty"] = self.generation_config.frequency_penalty

            # Set media resolution
            if self.generation_config.media_resolution:
                gen_config_kwargs["media_resolution"] = self.generation_config.media_resolution

        # Add JSON Schema for structured output
        gen_config_kwargs["response_mime_type"] = "application/json"
        gen_config_kwargs["response_schema"] = CHAT_RESPONSE_JSON_SCHEMA

        if gen_config_kwargs:
            config_dict["config"] = types.GenerateContentConfig(**gen_config_kwargs)

        self.chat = self.client.chats.create(**config_dict)
        self.history.clear()

    def _extract_thoughts_and_text(self, response) -> tuple[str, Optional[str]]:
        """Extract thoughts and text from model response."""
        thoughts_parts = []
        text_parts = []

        try:
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'thought') and part.thought:
                                thoughts_parts.append(part.text)
                            elif hasattr(part, 'text'):
                                text_parts.append(part.text)
        except Exception:
            pass

        # Fallback to response.text if no parts found
        if not text_parts:
            text_parts = [response.text] if hasattr(response, 'text') else []

        thoughts = "\n".join(thoughts_parts) if thoughts_parts else None
        text = "\n".join(text_parts)

        return text, thoughts

    def send_message(
        self,
        text: str,
        image_paths: Optional[list[str]] = None,
        file_paths: Optional[list[str]] = None,
    ) -> ModelResponse:
        """Send a message to the model.

        Args:
            text: The text message to send.
            image_paths: Optional list of image file paths.
            file_paths: Optional list of other file paths (PDFs, etc.).

        Returns:
            ModelResponse with the model's reply and any resource requests.
        """
        if self.chat is None:
            self.start_new_chat()

        # Build content list
        contents = []

        # Add images first
        if image_paths:
            for path in image_paths:
                if os.path.exists(path):
                    contents.append(create_image_part(path))

        # Add other files
        if file_paths:
            for path in file_paths:
                if os.path.exists(path):
                    contents.append(create_file_part(path))

        # Add text message
        contents.append(text)

        # Send to model
        response = self.chat.send_message(contents)

        # Extract thoughts and text from response
        response_text, thoughts = self._extract_thoughts_and_text(response)

        # Save to history
        self.history.append(ChatMessage(
            role="user",
            text=text,
            images=image_paths or [],
            files=file_paths or [],
        ))

        # Parse structured JSON response
        chat_response = self._parse_structured_response(response_text)
        self.history.append(ChatMessage(
            role="model",
            text=chat_response.response_text,
        ))
        return self._convert_to_model_response(chat_response, thoughts)

    def send_images_only(self, image_paths: list[str], context: str = "") -> ModelResponse:
        """Send only images (as a follow-up to model request).

        Args:
            image_paths: List of image file paths to send.
            context: Optional context message about the images.

        Returns:
            ModelResponse with the model's reply.
        """
        if self.chat is None:
            self.start_new_chat()

        contents = []

        for path in image_paths:
            if os.path.exists(path):
                contents.append(create_image_part(path))

        if context:
            contents.append(context)
        else:
            contents.append("Here are the requested images.")

        response = self.chat.send_message(contents)

        # Extract thoughts and text from response
        response_text, thoughts = self._extract_thoughts_and_text(response)

        # Save to history
        self.history.append(ChatMessage(
            role="user",
            text=context or "Provided requested images",
            images=image_paths,
        ))

        # Parse structured JSON response
        chat_response = self._parse_structured_response(response_text)
        self.history.append(ChatMessage(
            role="model",
            text=chat_response.response_text,
        ))
        return self._convert_to_model_response(chat_response, thoughts)

    def send_files_only(self, file_paths: list[str], context: str = "") -> ModelResponse:
        """Send only files (PDF, etc.) as a follow-up to model request.

        Args:
            file_paths: List of file paths to send.
            context: Optional context message about the files.

        Returns:
            ModelResponse with the model's reply.
        """
        if self.chat is None:
            self.start_new_chat()

        contents = []

        for path in file_paths:
            if os.path.exists(path):
                contents.append(create_file_part(path))

        if context:
            contents.append(context)
        else:
            contents.append("Вот запрошенные графические блоки.")

        response = self.chat.send_message(contents)

        # Extract thoughts and text from response
        response_text, thoughts = self._extract_thoughts_and_text(response)

        # Save to history
        self.history.append(ChatMessage(
            role="user",
            text=context or "Предоставлены запрошенные блоки",
            files=file_paths,
        ))

        # Parse structured JSON response
        chat_response = self._parse_structured_response(response_text)
        self.history.append(ChatMessage(
            role="model",
            text=chat_response.response_text,
        ))
        return self._convert_to_model_response(chat_response, thoughts)

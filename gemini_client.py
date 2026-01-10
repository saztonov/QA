"""Gemini API client module."""

import os
import re
from typing import Optional, Callable
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from config import Config, get_mime_type


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
    needs_images: bool = False
    requested_images: list[ImageRequest] = field(default_factory=list)
    needs_blocks: bool = False
    requested_blocks: list[BlockRequest] = field(default_factory=list)
    is_final: bool = True


class GeminiClient:
    """Client for interacting with Gemini API."""

    # Patterns to detect image requests from model
    IMAGE_REQUEST_PATTERNS = [
        r"(?:please\s+)?(?:provide|show|send|upload|share|attach)\s+(?:me\s+)?(?:the\s+)?(?:image|photo|picture|screenshot|file)s?\s*(?:of|for|named|called)?\s*[:\-]?\s*[\"']?([^\n\"']+)[\"']?",
        r"(?:I\s+)?need\s+(?:to\s+see\s+)?(?:the\s+)?(?:image|photo|picture|screenshot)s?\s*(?:of|for|named|called)?\s*[:\-]?\s*[\"']?([^\n\"']+)[\"']?",
        r"(?:can\s+you\s+)?(?:please\s+)?(?:show|send|provide)\s+[\"']?([^\n\"']+)[\"']?\s*(?:image|photo|picture)?",
        r"\[REQUEST_IMAGE:\s*([^\]]+)\]",
        r"\[НУЖНО_ИЗОБРАЖЕНИЕ:\s*([^\]]+)\]",
        r"мне\s+нужн[оа]\s+(?:изображение|картинка|фото)\s*[:\-]?\s*[\"']?([^\n\"']+)[\"']?",
        r"(?:пожалуйста\s+)?(?:предоставьте|покажите|пришлите|загрузите)\s+(?:изображение|картинку|фото)\s*[:\-]?\s*[\"']?([^\n\"']+)[\"']?",
    ]

    # Pattern to detect block requests from model
    BLOCK_REQUEST_PATTERN = re.compile(
        r"\[ЗАПРОС_БЛОКОВ\](.*?)\[/ЗАПРОС_БЛОКОВ\]",
        re.DOTALL
    )
    BLOCK_ID_PATTERN = re.compile(
        r"###\s*BLOCK\s*\[IMAGE\]:\s*([A-Z0-9\-]+)"
    )

    def __init__(self, config: Config):
        """Initialize Gemini client."""
        self.config = config
        self.client = genai.Client(api_key=config.api_key)
        self.chat: Optional[genai.chats.Chat] = None
        self.current_model = config.default_model
        self.history: list[ChatMessage] = []
        self.system_prompt: Optional[str] = None

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        """Set the system prompt for the chat."""
        self.system_prompt = prompt
        self.chat = None  # Reset chat to apply new system prompt

    def set_model(self, model_name: str) -> None:
        """Set the model to use."""
        if model_name in self.config.available_models:
            self.current_model = model_name
            self.chat = None  # Reset chat when model changes

    def start_new_chat(self) -> None:
        """Start a new chat session."""
        config_dict = {"model": self.current_model}
        if self.system_prompt:
            config_dict["config"] = types.GenerateContentConfig(
                system_instruction=self.system_prompt
            )
        self.chat = self.client.chats.create(**config_dict)
        self.history.clear()

    def _parse_block_requests(self, text: str) -> list[BlockRequest]:
        """Parse model response for block requests."""
        blocks = []

        # Find the block request section
        match = self.BLOCK_REQUEST_PATTERN.search(text)
        if match:
            block_section = match.group(1)
            # Find all block IDs in the section
            block_ids = self.BLOCK_ID_PATTERN.findall(block_section)
            for block_id in block_ids:
                blocks.append(BlockRequest(block_id=block_id.strip(), block_type="IMAGE"))

        return blocks

    def _check_for_block_requests(self, text: str) -> tuple[bool, list[BlockRequest]]:
        """Check if model is requesting document blocks."""
        blocks = self._parse_block_requests(text)
        return bool(blocks), blocks

    def _create_image_part(self, image_path: str) -> types.Part:
        """Create a Part object from an image file."""
        with open(image_path, "rb") as f:
            image_data = f.read()

        mime_type = get_mime_type(image_path)
        return types.Part.from_bytes(data=image_data, mime_type=mime_type)

    def _create_file_part(self, file_path: str) -> types.Part:
        """Create a Part object from a file."""
        with open(file_path, "rb") as f:
            file_data = f.read()

        mime_type = get_mime_type(file_path)
        return types.Part.from_bytes(data=file_data, mime_type=mime_type)

    def _parse_image_requests(self, text: str) -> list[ImageRequest]:
        """Parse model response for image requests."""
        requests = []
        for pattern in self.IMAGE_REQUEST_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                filename = match.strip()
                if filename and len(filename) < 200:  # Sanity check
                    requests.append(ImageRequest(filename=filename))
        return requests

    def _check_for_image_requests(self, text: str) -> tuple[bool, list[ImageRequest]]:
        """Check if model is requesting images."""
        # Keywords indicating image request
        request_keywords = [
            "provide image", "show image", "send image", "upload image",
            "need image", "need to see", "can you show", "please provide",
            "REQUEST_IMAGE", "НУЖНО_ИЗОБРАЖЕНИЕ",
            "нужно изображение", "нужна картинка", "покажите", "пришлите",
            "предоставьте изображение", "загрузите изображение",
        ]

        text_lower = text.lower()
        needs_images = any(kw.lower() in text_lower for kw in request_keywords)

        if needs_images:
            requested = self._parse_image_requests(text)
            return True, requested

        return False, []

    def send_message(
        self,
        text: str,
        image_paths: Optional[list[str]] = None,
        file_paths: Optional[list[str]] = None,
    ) -> ModelResponse:
        """Send a message to the model."""
        if self.chat is None:
            self.start_new_chat()

        # Build content list
        contents = []

        # Add images first
        if image_paths:
            for path in image_paths:
                if os.path.exists(path):
                    contents.append(self._create_image_part(path))

        # Add other files
        if file_paths:
            for path in file_paths:
                if os.path.exists(path):
                    contents.append(self._create_file_part(path))

        # Add text message
        contents.append(text)

        # Send to model
        response = self.chat.send_message(contents)
        response_text = response.text

        # Save to history
        self.history.append(ChatMessage(
            role="user",
            text=text,
            images=image_paths or [],
            files=file_paths or [],
        ))
        self.history.append(ChatMessage(
            role="model",
            text=response_text,
        ))

        # Check if model needs blocks (new format)
        needs_blocks, requested_blocks = self._check_for_block_requests(response_text)

        # Check if model needs more images (old format)
        needs_images, requested_images = self._check_for_image_requests(response_text)

        is_final = not needs_blocks and not needs_images

        return ModelResponse(
            text=response_text,
            needs_images=needs_images,
            requested_images=requested_images,
            needs_blocks=needs_blocks,
            requested_blocks=requested_blocks,
            is_final=is_final,
        )

    def send_images_only(self, image_paths: list[str], context: str = "") -> ModelResponse:
        """Send only images (as a follow-up to model request)."""
        if self.chat is None:
            self.start_new_chat()

        contents = []

        for path in image_paths:
            if os.path.exists(path):
                contents.append(self._create_image_part(path))

        if context:
            contents.append(context)
        else:
            contents.append("Here are the requested images.")

        response = self.chat.send_message(contents)
        response_text = response.text

        # Save to history
        self.history.append(ChatMessage(
            role="user",
            text=context or "Provided requested images",
            images=image_paths,
        ))
        self.history.append(ChatMessage(
            role="model",
            text=response_text,
        ))

        # Check if model needs blocks or images
        needs_blocks, requested_blocks = self._check_for_block_requests(response_text)
        needs_images, requested_images = self._check_for_image_requests(response_text)
        is_final = not needs_blocks and not needs_images

        return ModelResponse(
            text=response_text,
            needs_images=needs_images,
            requested_images=requested_images,
            needs_blocks=needs_blocks,
            requested_blocks=requested_blocks,
            is_final=is_final,
        )

    def send_files_only(self, file_paths: list[str], context: str = "") -> ModelResponse:
        """Send only files (PDF, etc.) as a follow-up to model request."""
        if self.chat is None:
            self.start_new_chat()

        contents = []

        for path in file_paths:
            if os.path.exists(path):
                contents.append(self._create_file_part(path))

        if context:
            contents.append(context)
        else:
            contents.append("Вот запрошенные графические блоки.")

        response = self.chat.send_message(contents)
        response_text = response.text

        # Save to history
        self.history.append(ChatMessage(
            role="user",
            text=context or "Предоставлены запрошенные блоки",
            files=file_paths,
        ))
        self.history.append(ChatMessage(
            role="model",
            text=response_text,
        ))

        # Check if model needs more blocks or images
        needs_blocks, requested_blocks = self._check_for_block_requests(response_text)
        needs_images, requested_images = self._check_for_image_requests(response_text)
        is_final = not needs_blocks and not needs_images

        return ModelResponse(
            text=response_text,
            needs_images=needs_images,
            requested_images=requested_images,
            needs_blocks=needs_blocks,
            requested_blocks=requested_blocks,
            is_final=is_final,
        )

    def get_history(self) -> list[ChatMessage]:
        """Get chat history."""
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear chat history and start fresh."""
        self.history.clear()
        self.chat = None

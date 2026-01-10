"""File utilities for creating Gemini API Part objects."""

from pathlib import Path
from typing import Union

from google.genai import types

from config import get_mime_type


def create_file_part(file_path: Union[str, Path]) -> types.Part:
    """Create a Part object from any file (PDF, image, etc.).

    Args:
        file_path: Path to the file.

    Returns:
        types.Part object ready for Gemini API.
    """
    file_path = Path(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    mime_type = get_mime_type(str(file_path))
    return types.Part.from_bytes(data=file_data, mime_type=mime_type)


def create_image_part(image_path: Union[str, Path]) -> types.Part:
    """Create a Part object from an image file.

    Alias for create_file_part, kept for semantic clarity.

    Args:
        image_path: Path to the image file.

    Returns:
        types.Part object ready for Gemini API.
    """
    return create_file_part(image_path)

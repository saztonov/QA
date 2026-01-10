"""Configuration module for Gemini Chat application."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / ".env")


# Project paths
PROJECT_ROOT = Path(__file__).parent
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
CROPS_DIR = DOCUMENTS_DIR / "crops"
DOCUMENT_MD_PATH = DOCUMENTS_DIR / "document.md"


@dataclass
class Config:
    """Application configuration."""

    api_key: str
    default_model: str = "gemini-2.0-flash"
    available_models: tuple = ("gemini-2.0-flash", "gemini-2.5-pro-preview-05-06")

    # Supported image extensions
    image_extensions: tuple = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

    # Supported document extensions
    document_extensions: tuple = (".pdf", ".txt", ".md")

    # Max file size in bytes (20MB)
    max_file_size: int = 20 * 1024 * 1024

    # Document paths
    documents_dir: Path = DOCUMENTS_DIR
    crops_dir: Path = CROPS_DIR
    document_md_path: Path = DOCUMENT_MD_PATH


def get_api_key() -> Optional[str]:
    """Get API key from environment variable."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def load_config() -> Config:
    """Load configuration from environment."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
        )
    return Config(api_key=api_key)


def get_mime_type(file_path: str) -> str:
    """Get MIME type for a file based on extension."""
    ext = os.path.splitext(file_path)[1].lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }
    return mime_types.get(ext, "application/octet-stream")

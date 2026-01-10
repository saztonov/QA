"""Image and file manager module."""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config import Config


@dataclass
class FileInfo:
    """Information about a file."""

    path: str
    name: str
    size: int
    is_image: bool


class ImageManager:
    """Manager for finding and handling images."""

    def __init__(self, config: Config):
        """Initialize image manager."""
        self.config = config
        self.search_directories: list[str] = []
        self.loaded_files: list[str] = []

    def add_search_directory(self, directory: str) -> bool:
        """Add a directory to search for images."""
        if os.path.isdir(directory):
            if directory not in self.search_directories:
                self.search_directories.append(directory)
            return True
        return False

    def remove_search_directory(self, directory: str) -> None:
        """Remove a directory from search list."""
        if directory in self.search_directories:
            self.search_directories.remove(directory)

    def get_search_directories(self) -> list[str]:
        """Get list of search directories."""
        return self.search_directories.copy()

    def is_image_file(self, file_path: str) -> bool:
        """Check if file is an image."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.config.image_extensions

    def is_supported_file(self, file_path: str) -> bool:
        """Check if file is supported (image or document)."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.config.image_extensions or ext in self.config.document_extensions

    def find_image(self, query: str) -> list[str]:
        """Find images matching query in search directories."""
        results = []
        query_lower = query.lower().strip()

        # Clean up query - remove common prefixes/suffixes
        clean_query = query_lower
        for prefix in ["image ", "file ", "photo ", "picture ", "the ", "a "]:
            if clean_query.startswith(prefix):
                clean_query = clean_query[len(prefix):]

        for directory in self.search_directories:
            results.extend(self._search_directory(directory, clean_query))

        return results

    def _search_directory(self, directory: str, query: str) -> list[str]:
        """Search a directory for matching images."""
        results = []

        try:
            for root, _, files in os.walk(directory):
                for filename in files:
                    if not self.is_image_file(filename):
                        continue

                    file_path = os.path.join(root, filename)
                    filename_lower = filename.lower()
                    name_without_ext = os.path.splitext(filename_lower)[0]

                    # Match by exact name, partial name, or query in filename
                    if (
                        query in filename_lower
                        or query in name_without_ext
                        or filename_lower.startswith(query)
                        or self._fuzzy_match(query, name_without_ext)
                    ):
                        results.append(file_path)

        except PermissionError:
            pass

        return results

    def _fuzzy_match(self, query: str, text: str) -> bool:
        """Simple fuzzy matching - all query words in text."""
        query_words = query.split()
        return all(word in text for word in query_words)

    def list_images_in_directory(self, directory: str) -> list[FileInfo]:
        """List all images in a directory."""
        images = []

        if not os.path.isdir(directory):
            return images

        try:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path) and self.is_image_file(filename):
                    stat = os.stat(file_path)
                    images.append(FileInfo(
                        path=file_path,
                        name=filename,
                        size=stat.st_size,
                        is_image=True,
                    ))
        except PermissionError:
            pass

        return images

    def add_loaded_file(self, file_path: str) -> bool:
        """Add a file to the loaded files list."""
        if os.path.exists(file_path) and self.is_supported_file(file_path):
            if file_path not in self.loaded_files:
                self.loaded_files.append(file_path)
            return True
        return False

    def remove_loaded_file(self, file_path: str) -> None:
        """Remove a file from loaded files list."""
        if file_path in self.loaded_files:
            self.loaded_files.remove(file_path)

    def get_loaded_files(self) -> list[str]:
        """Get list of loaded files."""
        return self.loaded_files.copy()

    def get_loaded_images(self) -> list[str]:
        """Get only loaded image files."""
        return [f for f in self.loaded_files if self.is_image_file(f)]

    def clear_loaded_files(self) -> None:
        """Clear all loaded files."""
        self.loaded_files.clear()

    def get_file_info(self, file_path: str) -> Optional[FileInfo]:
        """Get information about a file."""
        if not os.path.exists(file_path):
            return None

        stat = os.stat(file_path)
        return FileInfo(
            path=file_path,
            name=os.path.basename(file_path),
            size=stat.st_size,
            is_image=self.is_image_file(file_path),
        )

    def validate_file_size(self, file_path: str) -> bool:
        """Check if file size is within limits."""
        if not os.path.exists(file_path):
            return False

        stat = os.stat(file_path)
        return stat.st_size <= self.config.max_file_size

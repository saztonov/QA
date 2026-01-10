"""Block manager module for handling document blocks and crops."""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config import Config
from document_parser import DocumentParser, ImageBlock


@dataclass
class BlockFile:
    """Represents a block file from crops directory."""

    block_id: str
    file_path: Path
    exists: bool


class BlockManager:
    """Manager for finding and handling document blocks."""

    def __init__(self, config: Config, parser: DocumentParser):
        """Initialize block manager."""
        self.config = config
        self.parser = parser
        self.crops_dir = config.crops_dir
        self._block_cache: dict[str, BlockFile] = {}
        self._scan_crops_directory()

    def _scan_crops_directory(self) -> None:
        """Scan the crops directory and cache available blocks."""
        if not self.crops_dir.exists():
            return

        for file_path in self.crops_dir.iterdir():
            if file_path.suffix.lower() == ".pdf":
                block_id = file_path.stem  # e.g., "NWEK-9MHK-YHD"
                self._block_cache[block_id] = BlockFile(
                    block_id=block_id,
                    file_path=file_path,
                    exists=True,
                )

    def get_block_file(self, block_id: str) -> Optional[BlockFile]:
        """Get a block file by ID."""
        # Check cache first
        if block_id in self._block_cache:
            return self._block_cache[block_id]

        # Try to find the file
        file_path = self.crops_dir / f"{block_id}.pdf"
        if file_path.exists():
            block_file = BlockFile(
                block_id=block_id,
                file_path=file_path,
                exists=True,
            )
            self._block_cache[block_id] = block_file
            return block_file

        return None

    def get_block_files_for_ids(self, block_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Get file paths for a list of block IDs.

        Returns:
            Tuple of (found_paths, not_found_ids)
        """
        found_paths = []
        not_found_ids = []

        for block_id in block_ids:
            block_file = self.get_block_file(block_id)
            if block_file and block_file.exists:
                found_paths.append(str(block_file.file_path))
            else:
                not_found_ids.append(block_id)

        return found_paths, not_found_ids

    def get_available_block_ids(self) -> list[str]:
        """Get list of all available block IDs in crops directory."""
        return list(self._block_cache.keys())

    def is_block_available(self, block_id: str) -> bool:
        """Check if a block file is available."""
        block_file = self.get_block_file(block_id)
        return block_file is not None and block_file.exists

    def get_block_info(self, block_id: str) -> Optional[ImageBlock]:
        """Get block metadata from document parser."""
        return self.parser.get_image_block(block_id)

    def get_block_description(self, block_id: str) -> str:
        """Get a human-readable description of a block."""
        block = self.get_block_info(block_id)
        if block:
            desc = f"Блок {block_id}"
            if block.block_type:
                desc += f" (Тип: {block.block_type})"
            if block.short_description:
                desc += f": {block.short_description}"
            return desc
        return f"Блок {block_id}"

    def validate_block_ids(self, block_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Validate block IDs against available blocks.

        Returns:
            Tuple of (valid_ids, invalid_ids)
        """
        valid_ids = []
        invalid_ids = []

        for block_id in block_ids:
            if self.is_block_available(block_id):
                valid_ids.append(block_id)
            else:
                invalid_ids.append(block_id)

        return valid_ids, invalid_ids

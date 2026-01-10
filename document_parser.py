"""Document parser module for parsing document.md structure."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ImageBlock:
    """Represents a graphical block from document.md."""

    block_id: str
    block_type: str  # e.g., "План этажа", "Разрез", "Легенда"
    axes: str  # e.g., "1-8/А-Ж"
    short_description: str
    description: str
    text_on_drawing: str
    entities: list[str] = field(default_factory=list)
    linked_block_id: Optional[str] = None  # Referenced block (→ID)
    page_number: Optional[int] = None
    raw_content: str = ""


@dataclass
class TextBlock:
    """Represents a text block from document.md."""

    block_id: str
    content: str
    linked_block_id: Optional[str] = None
    page_number: Optional[int] = None


@dataclass
class DocumentData:
    """Parsed document data."""

    title: str
    stamp: str
    text_blocks: dict[str, TextBlock] = field(default_factory=dict)
    image_blocks: dict[str, ImageBlock] = field(default_factory=dict)
    raw_content: str = ""


class DocumentParser:
    """Parser for document.md files."""

    # Regex patterns
    BLOCK_IMAGE_PATTERN = re.compile(
        r"### BLOCK \[IMAGE\]: ([A-Z0-9\-]+)\n(.*?)(?=### BLOCK|\Z)",
        re.DOTALL
    )
    BLOCK_TEXT_PATTERN = re.compile(
        r"### BLOCK \[TEXT\]: ([A-Z0-9\-]+)\n(.*?)(?=### BLOCK|\Z)",
        re.DOTALL
    )
    PAGE_PATTERN = re.compile(r"## СТРАНИЦА (\d+)")
    LINK_PATTERN = re.compile(r"→([A-Z0-9\-]+)")

    def __init__(self, document_path: Path):
        """Initialize parser with document path."""
        self.document_path = document_path
        self._document_data: Optional[DocumentData] = None

    def parse(self) -> DocumentData:
        """Parse the document and return structured data."""
        if self._document_data is not None:
            return self._document_data

        content = self.document_path.read_text(encoding="utf-8")

        # Extract title and stamp from header
        title = self._extract_title(content)
        stamp = self._extract_stamp(content)

        # Parse blocks
        text_blocks = self._parse_text_blocks(content)
        image_blocks = self._parse_image_blocks(content)

        self._document_data = DocumentData(
            title=title,
            stamp=stamp,
            text_blocks=text_blocks,
            image_blocks=image_blocks,
            raw_content=content,
        )

        return self._document_data

    def _extract_title(self, content: str) -> str:
        """Extract document title from header."""
        match = re.search(r"^# (.+)$", content, re.MULTILINE)
        return match.group(1) if match else ""

    def _extract_stamp(self, content: str) -> str:
        """Extract stamp information."""
        match = re.search(r"\*\*Штамп:\*\* (.+?)(?=\n\n|\n---)", content, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _get_page_for_position(self, content: str, position: int) -> Optional[int]:
        """Get page number for a given position in content."""
        pages = list(self.PAGE_PATTERN.finditer(content))
        current_page = None
        for page_match in pages:
            if page_match.start() <= position:
                current_page = int(page_match.group(1))
            else:
                break
        return current_page

    def _parse_text_blocks(self, content: str) -> dict[str, TextBlock]:
        """Parse all text blocks."""
        blocks = {}

        for match in self.BLOCK_TEXT_PATTERN.finditer(content):
            block_id = match.group(1)
            block_content = match.group(2).strip()

            # Check for linked block
            link_match = self.LINK_PATTERN.search(block_content)
            linked_id = link_match.group(1) if link_match else None

            # Remove link reference from content
            if linked_id:
                block_content = self.LINK_PATTERN.sub("", block_content).strip()

            page = self._get_page_for_position(content, match.start())

            blocks[block_id] = TextBlock(
                block_id=block_id,
                content=block_content,
                linked_block_id=linked_id,
                page_number=page,
            )

        return blocks

    def _parse_image_blocks(self, content: str) -> dict[str, ImageBlock]:
        """Parse all image blocks."""
        blocks = {}

        for match in self.BLOCK_IMAGE_PATTERN.finditer(content):
            block_id = match.group(1)
            block_content = match.group(2).strip()

            # Check for linked block
            link_match = self.LINK_PATTERN.search(block_content)
            linked_id = link_match.group(1) if link_match else None

            # Parse block metadata
            block_type = self._extract_field(block_content, r"\*\*\[ИЗОБРАЖЕНИЕ\]\*\* \| Тип: ([^\|]+)")
            axes = self._extract_field(block_content, r"\| Оси: ([^\n]+)")
            short_desc = self._extract_field(block_content, r"\*\*Краткое описание:\*\* ([^\n]+)")
            description = self._extract_field(block_content, r"\*\*Описание:\*\* ([^\n]+)")
            text_on_drawing = self._extract_field(block_content, r"\*\*Текст на чертеже:\*\* ([^\n]+)")
            entities_str = self._extract_field(block_content, r"\*\*Сущности:\*\* ([^\n]+)")

            entities = [e.strip() for e in entities_str.split(",")] if entities_str else []
            page = self._get_page_for_position(content, match.start())

            blocks[block_id] = ImageBlock(
                block_id=block_id,
                block_type=block_type.strip() if block_type else "",
                axes=axes.strip() if axes else "",
                short_description=short_desc.strip() if short_desc else "",
                description=description.strip() if description else "",
                text_on_drawing=text_on_drawing.strip() if text_on_drawing else "",
                entities=entities,
                linked_block_id=linked_id,
                page_number=page,
                raw_content=block_content,
            )

        return blocks

    def _extract_field(self, content: str, pattern: str) -> str:
        """Extract a field from block content using regex."""
        match = re.search(pattern, content)
        return match.group(1) if match else ""

    def get_image_block(self, block_id: str) -> Optional[ImageBlock]:
        """Get an image block by ID."""
        data = self.parse()
        return data.image_blocks.get(block_id)

    def get_text_block(self, block_id: str) -> Optional[TextBlock]:
        """Get a text block by ID."""
        data = self.parse()
        return data.text_blocks.get(block_id)

    def get_all_image_block_ids(self) -> list[str]:
        """Get all image block IDs."""
        data = self.parse()
        return list(data.image_blocks.keys())

    def get_all_text_block_ids(self) -> list[str]:
        """Get all text block IDs."""
        data = self.parse()
        return list(data.text_blocks.keys())

    def get_image_blocks_summary(self) -> str:
        """Get a summary of all image blocks for the system prompt."""
        data = self.parse()
        lines = ["Доступные графические блоки:"]

        for block_id, block in data.image_blocks.items():
            block_info = f"- ### BLOCK [IMAGE]: {block_id}"
            if block.block_type:
                block_info += f" | Тип: {block.block_type}"
            if block.axes:
                block_info += f" | Оси: {block.axes}"
            if block.short_description:
                block_info += f"\n  {block.short_description}"
            lines.append(block_info)

        return "\n".join(lines)

    def get_document_context(self) -> str:
        """Get full document context for the system prompt."""
        data = self.parse()
        return data.raw_content

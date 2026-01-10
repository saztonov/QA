"""Block indexer module for generating descriptions of document blocks using Flash."""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from google import genai
from google.genai import types

from config import Config
from file_utils import create_file_part


# Schema for block description
BLOCK_DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "block_id": {
            "type": "string",
            "description": "ID of the block being described"
        },
        "title": {
            "type": "string",
            "description": "Short descriptive title of what's on this drawing/document (in Russian)"
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Keywords describing the content (5-10 keywords in Russian)"
        },
        "discipline": {
            "type": "string",
            "enum": [
                "architecture",
                "structural",
                "hvac",
                "electrical",
                "plumbing",
                "fire_safety",
                "landscape",
                "general",
                "other"
            ],
            "description": "Engineering discipline of this drawing"
        },
        "what_is_on_drawing": {
            "type": "string",
            "description": "Detailed description of what is shown on this drawing (2-3 sentences in Russian)"
        },
        "floor_or_section": {
            "type": "string",
            "description": "Floor number, section, or area if identifiable (e.g., 'Этаж 1', 'Разрез А-А', 'Кровля')"
        },
        "scale": {
            "type": "string",
            "description": "Drawing scale if visible (e.g., '1:100', '1:50')"
        }
    },
    "required": ["block_id", "title", "keywords", "discipline", "what_is_on_drawing"]
}

# Schema for batch response
BATCH_DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "descriptions": {
            "type": "array",
            "items": BLOCK_DESCRIPTION_SCHEMA,
            "description": "List of block descriptions"
        }
    },
    "required": ["descriptions"]
}


INDEXER_SYSTEM_PROMPT = """Ты - эксперт по анализу строительной документации и чертежей.

## Твоя задача:
Проанализировать предоставленные графические блоки (PDF-файлы чертежей) и создать структурированное описание каждого.

## Правила:
1. **title**: Краткое название чертежа (например: "План 1 этажа", "Разрез 1-1", "Схема пожаротушения")
2. **keywords**: 5-10 ключевых слов для поиска (на русском)
3. **discipline**: Выбери одну из категорий:
   - architecture: архитектурные решения, планы, фасады
   - structural: конструкции, фундаменты, несущие элементы
   - hvac: отопление, вентиляция, кондиционирование
   - electrical: электрика, освещение, слаботочные системы
   - plumbing: водоснабжение, канализация
   - fire_safety: противопожарные системы, эвакуация, АУПТ, СОУЭ
   - landscape: благоустройство, озеленение
   - general: общие данные, спецификации, ведомости
   - other: прочее

4. **what_is_on_drawing**: Подробно опиши что изображено (2-3 предложения)
5. **floor_or_section**: Укажи этаж/разрез/зону если видно
6. **scale**: Укажи масштаб если виден на чертеже

## Важно:
- Пиши на русском языке
- Будь точен в описаниях
- Если что-то не видно или неразборчиво - укажи это
"""


@dataclass
class BlockDescription:
    """Description of a single document block."""

    block_id: str
    title: str
    keywords: list[str]
    discipline: str
    what_is_on_drawing: str
    floor_or_section: str = ""
    scale: str = ""

    # Metadata
    indexed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    file_path: str = ""
    file_size_kb: int = 0


@dataclass
class BlockIndex:
    """Index of all block descriptions."""

    blocks: dict[str, BlockDescription] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0"
    total_blocks: int = 0
    indexed_blocks: int = 0
    failed_blocks: list[str] = field(default_factory=list)

    def add_block(self, desc: BlockDescription) -> None:
        """Add a block description to the index."""
        self.blocks[desc.block_id] = desc
        self.indexed_blocks = len(self.blocks)
        self.updated_at = datetime.now().isoformat()

    def get_block(self, block_id: str) -> Optional[BlockDescription]:
        """Get block description by ID."""
        return self.blocks.get(block_id)

    def get_blocks_by_discipline(self, discipline: str) -> list[BlockDescription]:
        """Get all blocks of a specific discipline."""
        return [b for b in self.blocks.values() if b.discipline == discipline]

    def search_by_keywords(self, keywords: list[str]) -> list[BlockDescription]:
        """Search blocks by keywords."""
        results = []
        keywords_lower = [k.lower() for k in keywords]
        for block in self.blocks.values():
            block_keywords = [k.lower() for k in block.keywords]
            if any(kw in block_keywords or any(kw in bk for bk in block_keywords)
                   for kw in keywords_lower):
                results.append(block)
        return results

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_blocks": self.total_blocks,
            "indexed_blocks": self.indexed_blocks,
            "failed_blocks": self.failed_blocks,
            "blocks": {
                block_id: asdict(desc)
                for block_id, desc in self.blocks.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlockIndex":
        """Create BlockIndex from dictionary."""
        index = cls(
            version=data.get("version", "1.0"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            total_blocks=data.get("total_blocks", 0),
            indexed_blocks=data.get("indexed_blocks", 0),
            failed_blocks=data.get("failed_blocks", []),
        )

        for block_id, block_data in data.get("blocks", {}).items():
            desc = BlockDescription(
                block_id=block_data.get("block_id", block_id),
                title=block_data.get("title", ""),
                keywords=block_data.get("keywords", []),
                discipline=block_data.get("discipline", "other"),
                what_is_on_drawing=block_data.get("what_is_on_drawing", ""),
                floor_or_section=block_data.get("floor_or_section", ""),
                scale=block_data.get("scale", ""),
                indexed_at=block_data.get("indexed_at", ""),
                file_path=block_data.get("file_path", ""),
                file_size_kb=block_data.get("file_size_kb", 0),
            )
            index.blocks[block_id] = desc

        return index

    def get_summary_for_planner(self) -> str:
        """Generate a summary string for use in planner prompts."""
        if not self.blocks:
            return "Индекс блоков пуст."

        lines = [f"Индексировано блоков: {self.indexed_blocks}\n"]

        # Group by discipline
        by_discipline: dict[str, list[BlockDescription]] = {}
        for block in self.blocks.values():
            disc = block.discipline
            if disc not in by_discipline:
                by_discipline[disc] = []
            by_discipline[disc].append(block)

        discipline_names = {
            "architecture": "Архитектура",
            "structural": "Конструкции",
            "hvac": "ОВиК",
            "electrical": "Электрика",
            "plumbing": "Водоснабжение",
            "fire_safety": "Пожарная безопасность",
            "landscape": "Благоустройство",
            "general": "Общие данные",
            "other": "Прочее",
        }

        for disc, blocks in sorted(by_discipline.items()):
            disc_name = discipline_names.get(disc, disc)
            lines.append(f"\n### {disc_name} ({len(blocks)} блоков):")
            for block in blocks[:10]:  # Limit to 10 per discipline
                keywords_str = ", ".join(block.keywords[:5])
                lines.append(
                    f"- **{block.block_id}**: {block.title}"
                    f" [{keywords_str}]"
                )
            if len(blocks) > 10:
                lines.append(f"  ... и ещё {len(blocks) - 10} блоков")

        return "\n".join(lines)


class BlockIndexer:
    """Indexes document blocks using Gemini Flash model."""

    MODEL_NAME = "gemini-3-flash-preview"
    BATCH_SIZE = 2  # Number of blocks per request

    def __init__(self, config: Config):
        """Initialize indexer.

        Args:
            config: Application configuration with API key.
        """
        self.config = config
        self.client = genai.Client(api_key=config.api_key)

        # Progress callbacks
        self.on_progress: Optional[Callable[[int, int, str], None]] = None
        self.on_error: Optional[Callable[[str, str], None]] = None
        self.on_complete: Optional[Callable[[BlockIndex], None]] = None

    def _extract_block_id(self, file_path: Path) -> str:
        """Extract block ID from file path."""
        # Assuming format: BLOCK-ID.pdf or similar
        return file_path.stem

    def _index_batch(
        self,
        batch: list[tuple[str, Path]]
    ) -> list[BlockDescription]:
        """Index a batch of blocks.

        Args:
            batch: List of (block_id, file_path) tuples.

        Returns:
            List of BlockDescription objects.
        """
        if not batch:
            return []

        # Build content with all PDFs in batch
        contents = []
        block_ids = []

        for block_id, file_path in batch:
            block_ids.append(block_id)
            contents.append(create_file_part(file_path))

        # Add prompt
        if len(batch) == 1:
            prompt = f"Опиши этот графический блок. Block ID: {block_ids[0]}"
        else:
            ids_str = ", ".join(block_ids)
            prompt = f"Опиши каждый из этих графических блоков. Block IDs: {ids_str}"

        contents.append(prompt)

        # Configure generation
        gen_config = types.GenerateContentConfig(
            system_instruction=INDEXER_SYSTEM_PROMPT,
            temperature=1.0,
            top_p=0.95,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=BATCH_DESCRIPTION_SCHEMA if len(batch) > 1 else BLOCK_DESCRIPTION_SCHEMA,
        )

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=contents,
                config=gen_config,
            )

            response_text = response.text.strip()
            result = json.loads(response_text)

            descriptions = []

            if len(batch) == 1:
                # Single block response
                desc = BlockDescription(
                    block_id=result.get("block_id", block_ids[0]),
                    title=result.get("title", ""),
                    keywords=result.get("keywords", []),
                    discipline=result.get("discipline", "other"),
                    what_is_on_drawing=result.get("what_is_on_drawing", ""),
                    floor_or_section=result.get("floor_or_section", ""),
                    scale=result.get("scale", ""),
                    file_path=str(batch[0][1]),
                    file_size_kb=batch[0][1].stat().st_size // 1024,
                )
                descriptions.append(desc)
            else:
                # Batch response
                for item in result.get("descriptions", []):
                    block_id = item.get("block_id", "")
                    # Find matching file path
                    file_path = None
                    for bid, fpath in batch:
                        if bid == block_id:
                            file_path = fpath
                            break

                    desc = BlockDescription(
                        block_id=block_id,
                        title=item.get("title", ""),
                        keywords=item.get("keywords", []),
                        discipline=item.get("discipline", "other"),
                        what_is_on_drawing=item.get("what_is_on_drawing", ""),
                        floor_or_section=item.get("floor_or_section", ""),
                        scale=item.get("scale", ""),
                        file_path=str(file_path) if file_path else "",
                        file_size_kb=file_path.stat().st_size // 1024 if file_path else 0,
                    )
                    descriptions.append(desc)

            return descriptions

        except Exception as e:
            if self.on_error:
                ids_str = ", ".join(block_ids)
                self.on_error(ids_str, str(e))
            return []

    def index_directory(
        self,
        crops_dir: Path,
        output_path: Optional[Path] = None,
        skip_existing: bool = True,
    ) -> BlockIndex:
        """Index all PDF blocks in a directory.

        Args:
            crops_dir: Directory containing PDF blocks.
            output_path: Path to save the index JSON file.
            skip_existing: Skip blocks already in existing index.

        Returns:
            BlockIndex with all block descriptions.
        """
        # Load existing index if available
        index = BlockIndex()
        if output_path and output_path.exists() and skip_existing:
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    index = BlockIndex.from_dict(json.load(f))
            except Exception:
                pass

        # Find all PDF files
        pdf_files = list(crops_dir.glob("*.pdf"))
        index.total_blocks = len(pdf_files)

        if not pdf_files:
            if self.on_complete:
                self.on_complete(index)
            return index

        # Prepare blocks to index
        blocks_to_index = []
        for pdf_path in pdf_files:
            block_id = self._extract_block_id(pdf_path)
            if skip_existing and block_id in index.blocks:
                continue
            blocks_to_index.append((block_id, pdf_path))

        if not blocks_to_index:
            if self.on_progress:
                self.on_progress(index.indexed_blocks, index.total_blocks, "Already indexed")
            if self.on_complete:
                self.on_complete(index)
            return index

        # Process in batches
        total_to_process = len(blocks_to_index)
        processed = 0

        for i in range(0, len(blocks_to_index), self.BATCH_SIZE):
            batch = blocks_to_index[i:i + self.BATCH_SIZE]
            batch_ids = [b[0] for b in batch]

            if self.on_progress:
                self.on_progress(
                    processed + len(index.blocks),
                    index.total_blocks,
                    f"Indexing: {', '.join(batch_ids)}"
                )

            descriptions = self._index_batch(batch)

            for desc in descriptions:
                index.add_block(desc)

            # Track failed blocks
            indexed_ids = {d.block_id for d in descriptions}
            for block_id, _ in batch:
                if block_id not in indexed_ids:
                    if block_id not in index.failed_blocks:
                        index.failed_blocks.append(block_id)

            processed += len(batch)

            # Save intermediate progress
            if output_path:
                self._save_index(index, output_path)

        # Final save
        if output_path:
            self._save_index(index, output_path)

        if self.on_progress:
            self.on_progress(
                index.indexed_blocks,
                index.total_blocks,
                "Complete"
            )

        if self.on_complete:
            self.on_complete(index)

        return index

    def _save_index(self, index: BlockIndex, output_path: Path) -> None:
        """Save index to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(index.to_dict(), f, indent=2, ensure_ascii=False)

    def index_single_block(self, block_id: str, file_path: Path) -> Optional[BlockDescription]:
        """Index a single block.

        Args:
            block_id: ID of the block.
            file_path: Path to the PDF file.

        Returns:
            BlockDescription or None if failed.
        """
        descriptions = self._index_batch([(block_id, file_path)])
        return descriptions[0] if descriptions else None


def load_block_index(path: Path) -> Optional[BlockIndex]:
    """Load block index from JSON file.

    Args:
        path: Path to the index JSON file.

    Returns:
        BlockIndex or None if file doesn't exist.
    """
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return BlockIndex.from_dict(json.load(f))
    except Exception:
        return None

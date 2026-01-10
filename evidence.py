"""Evidence Manager for rendering PDF pages and cropping regions of interest.

This module provides LRU-cached rendering of PDF pages to PNG images
with support for region-of-interest cropping. Key features:

- LRU cache with configurable size limit (default 500MB)
- Version-aware caching (invalidates on PDF file changes)
- Fallback to full page when crop fails
- Automatic cleanup of old cache files
"""

import hashlib
import json
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import fitz  # PyMuPDF
from PIL import Image

from schemas import BBoxNorm, RequestedROI


# Default cache size limit (500 MB)
DEFAULT_CACHE_SIZE_LIMIT_MB = 500


@dataclass
class RenderedEvidence:
    """Represents a rendered piece of evidence."""

    block_id: str
    page: int
    dpi: int
    png_path: Path
    is_crop: bool = False
    bbox_norm: Optional[BBoxNorm] = None
    crop_path: Optional[Path] = None
    is_fallback: bool = False  # True if crop failed and full page was used


@dataclass
class CacheEntry:
    """Metadata for a cached file."""

    path: Path
    size_bytes: int
    created_at: float
    source_mtime: float  # mtime of source PDF for version tracking
    last_accessed: float = field(default_factory=time.time)


class EvidenceManager:
    """Manages rendering of PDF pages and cropping regions of interest.

    Features:
    - LRU cache with size limit to prevent disk overflow
    - Version tracking: cache is invalidated when source PDF changes
    - Graceful fallback: if crop fails, returns full page instead
    - Automatic cleanup of least recently used files
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_cache_size_mb: int = DEFAULT_CACHE_SIZE_LIMIT_MB,
    ):
        """Initialize EvidenceManager.

        Args:
            cache_dir: Directory for caching rendered images.
                      Defaults to ./cache/evidence/
            max_cache_size_mb: Maximum cache size in megabytes (default 500MB).
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "cache" / "evidence"

        self.cache_dir = cache_dir
        self.renders_dir = cache_dir / "renders"
        self.crops_dir = cache_dir / "crops"
        self.max_cache_size_bytes = max_cache_size_mb * 1024 * 1024

        # Ensure cache directories exist
        self.renders_dir.mkdir(parents=True, exist_ok=True)
        self.crops_dir.mkdir(parents=True, exist_ok=True)

        # LRU cache: OrderedDict maintains insertion/access order
        # Key: (block_id, page, dpi, source_mtime) -> CacheEntry
        self._render_cache: OrderedDict[tuple, CacheEntry] = OrderedDict()
        self._crop_cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # Track total cache size
        self._current_cache_size = 0

        # Load existing cache metadata
        self._load_existing_cache()

    def _load_existing_cache(self) -> None:
        """Scan cache directories and load existing files into memory cache."""
        # Load renders
        for png_file in self.renders_dir.glob("*.png"):
            try:
                stat = png_file.stat()
                # Parse cache key from filename
                # Format: {block_id}_p{page}_d{dpi}_v{mtime}.png
                parts = png_file.stem.split("_")
                if len(parts) >= 4:
                    entry = CacheEntry(
                        path=png_file,
                        size_bytes=stat.st_size,
                        created_at=stat.st_ctime,
                        source_mtime=0,  # Unknown for existing files
                        last_accessed=stat.st_atime,
                    )
                    self._current_cache_size += stat.st_size
            except (OSError, ValueError):
                pass

        # Load crops
        for png_file in self.crops_dir.glob("*.png"):
            try:
                stat = png_file.stat()
                crop_key = png_file.stem
                self._crop_cache[crop_key] = CacheEntry(
                    path=png_file,
                    size_bytes=stat.st_size,
                    created_at=stat.st_ctime,
                    source_mtime=0,
                    last_accessed=stat.st_atime,
                )
                self._current_cache_size += stat.st_size
            except OSError:
                pass

    def _get_source_mtime(self, pdf_path: Path) -> float:
        """Get modification time of source PDF for version tracking."""
        try:
            return pdf_path.stat().st_mtime
        except OSError:
            return 0.0

    def _evict_lru_files(self, needed_bytes: int = 0) -> None:
        """Evict least recently used files to make room.

        Args:
            needed_bytes: Additional bytes needed (evict until we have this much free).
        """
        target_size = self.max_cache_size_bytes - needed_bytes

        # Evict from crop cache first (usually smaller)
        while self._current_cache_size > target_size and self._crop_cache:
            # Pop oldest entry (first item in OrderedDict)
            key, entry = self._crop_cache.popitem(last=False)
            try:
                if entry.path.exists():
                    entry.path.unlink()
                    self._current_cache_size -= entry.size_bytes
            except OSError:
                pass

        # Then evict from render cache
        while self._current_cache_size > target_size and self._render_cache:
            key, entry = self._render_cache.popitem(last=False)
            try:
                if entry.path.exists():
                    entry.path.unlink()
                    self._current_cache_size -= entry.size_bytes
            except OSError:
                pass

    def _touch_cache_entry(self, cache: OrderedDict, key) -> None:
        """Mark cache entry as recently used (move to end)."""
        if key in cache:
            cache.move_to_end(key)

    def _get_cache_key(self, block_id: str, page: int, dpi: int) -> str:
        """Generate a unique cache key for a render."""
        return f"{block_id}_p{page}_d{dpi}"

    def _get_versioned_cache_key(
        self, block_id: str, page: int, dpi: int, source_mtime: float
    ) -> str:
        """Generate a version-aware cache key for a render."""
        mtime_hash = hashlib.md5(str(source_mtime).encode()).hexdigest()[:8]
        return f"{block_id}_p{page}_d{dpi}_v{mtime_hash}"

    def _get_crop_key(self, block_id: str, page: int, bbox: BBoxNorm, dpi: int) -> str:
        """Generate a unique cache key for a crop."""
        bbox_str = f"{bbox.x0:.4f}_{bbox.y0:.4f}_{bbox.x1:.4f}_{bbox.y1:.4f}"
        return f"{block_id}_p{page}_d{dpi}_crop_{bbox_str}"

    def render_pdf_page_to_png(
        self,
        pdf_path: Union[str, Path],
        block_id: str,
        page: int = 0,
        dpi: int = 150
    ) -> Path:
        """Render a PDF page to PNG image.

        Args:
            pdf_path: Path to the PDF file.
            block_id: Block ID for caching purposes.
            page: Page number (0-indexed).
            dpi: Resolution for rendering (default 150, max 600).

        Returns:
            Path to the rendered PNG file.

        Raises:
            FileNotFoundError: If PDF file doesn't exist.
            ValueError: If page number is out of range.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # Clamp DPI to reasonable range
        dpi = max(72, min(600, dpi))

        # Get source file modification time for versioning
        source_mtime = self._get_source_mtime(pdf_path)

        # Check cache with version awareness
        cache_key = (block_id, page, dpi, source_mtime)
        if cache_key in self._render_cache:
            entry = self._render_cache[cache_key]
            if entry.path.exists():
                # Touch entry to mark as recently used
                self._touch_cache_entry(self._render_cache, cache_key)
                entry.last_accessed = time.time()
                return entry.path

        # Generate versioned output filename
        cache_name = self._get_versioned_cache_key(block_id, page, dpi, source_mtime)
        png_path = self.renders_dir / f"{cache_name}.png"

        # Check if file already exists on disk (from previous session)
        if png_path.exists():
            stat = png_path.stat()
            entry = CacheEntry(
                path=png_path,
                size_bytes=stat.st_size,
                created_at=stat.st_ctime,
                source_mtime=source_mtime,
                last_accessed=time.time(),
            )
            self._render_cache[cache_key] = entry
            self._current_cache_size += stat.st_size
            return png_path

        # Render the page
        doc = fitz.open(pdf_path)
        try:
            if page >= len(doc):
                raise ValueError(f"Page {page} out of range. PDF has {len(doc)} pages.")

            pdf_page = doc[page]

            # Calculate zoom factor based on DPI (PDF default is 72 DPI)
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            # Render to pixmap
            pixmap = pdf_page.get_pixmap(matrix=matrix, alpha=False)

            # Check if we need to evict old files
            estimated_size = pixmap.width * pixmap.height * 3  # RGB, ~3 bytes/pixel
            if self._current_cache_size + estimated_size > self.max_cache_size_bytes:
                self._evict_lru_files(needed_bytes=estimated_size)

            # Save as PNG
            pixmap.save(str(png_path))

        finally:
            doc.close()

        # Update cache with new entry
        stat = png_path.stat()
        entry = CacheEntry(
            path=png_path,
            size_bytes=stat.st_size,
            created_at=time.time(),
            source_mtime=source_mtime,
            last_accessed=time.time(),
        )
        self._render_cache[cache_key] = entry
        self._current_cache_size += stat.st_size

        return png_path

    def crop_png(
        self,
        png_path: Union[str, Path],
        bbox_norm: BBoxNorm,
        block_id: str,
        page: int = 0,
        dpi: int = 150
    ) -> Path:
        """Crop a region from a PNG image using normalized coordinates.

        Args:
            png_path: Path to the source PNG file.
            bbox_norm: Normalized bounding box (0.0-1.0 coordinates).
            block_id: Block ID for cache naming.
            page: Page number for cache naming.
            dpi: DPI for cache naming.

        Returns:
            Path to the cropped PNG file.

        Raises:
            FileNotFoundError: If source PNG doesn't exist.
            ValueError: If bbox coordinates are invalid.
        """
        png_path = Path(png_path)
        if not png_path.exists():
            raise FileNotFoundError(f"PNG file not found: {png_path}")

        # Validate bbox (with tolerance for floating point errors)
        x0, y0, x1, y1 = bbox_norm.x0, bbox_norm.y0, bbox_norm.x1, bbox_norm.y1

        # Clamp values to valid range
        x0 = max(0.0, min(1.0, x0))
        y0 = max(0.0, min(1.0, y0))
        x1 = max(0.0, min(1.0, x1))
        y1 = max(0.0, min(1.0, y1))

        # Ensure x0 < x1 and y0 < y1
        if x0 >= x1:
            x0, x1 = 0.0, 1.0  # Fallback to full width
        if y0 >= y1:
            y0, y1 = 0.0, 1.0  # Fallback to full height

        # Update bbox_norm with corrected values
        corrected_bbox = BBoxNorm(x0=x0, y0=y0, x1=x1, y1=y1)

        # Generate crop filename
        crop_name = self._get_crop_key(block_id, page, corrected_bbox, dpi)
        crop_path = self.crops_dir / f"{crop_name}.png"

        # Check LRU cache
        if crop_name in self._crop_cache:
            entry = self._crop_cache[crop_name]
            if entry.path.exists():
                self._touch_cache_entry(self._crop_cache, crop_name)
                entry.last_accessed = time.time()
                return entry.path

        # Check if crop already exists on disk
        if crop_path.exists():
            stat = crop_path.stat()
            entry = CacheEntry(
                path=crop_path,
                size_bytes=stat.st_size,
                created_at=stat.st_ctime,
                source_mtime=0,
                last_accessed=time.time(),
            )
            self._crop_cache[crop_name] = entry
            self._current_cache_size += stat.st_size
            return crop_path

        # Open image and crop
        with Image.open(png_path) as img:
            width, height = img.size

            # Convert normalized coordinates to pixels
            left = int(x0 * width)
            top = int(y0 * height)
            right = int(x1 * width)
            bottom = int(y1 * height)

            # Ensure minimum crop size (at least 10x10 pixels)
            if right - left < 10:
                right = min(left + 10, width)
            if bottom - top < 10:
                bottom = min(top + 10, height)

            # Check if we need to evict old files
            estimated_size = (right - left) * (bottom - top) * 3
            if self._current_cache_size + estimated_size > self.max_cache_size_bytes:
                self._evict_lru_files(needed_bytes=estimated_size)

            # Crop and save
            cropped = img.crop((left, top, right, bottom))
            cropped.save(crop_path, "PNG")

        # Update LRU cache
        stat = crop_path.stat()
        entry = CacheEntry(
            path=crop_path,
            size_bytes=stat.st_size,
            created_at=time.time(),
            source_mtime=0,
            last_accessed=time.time(),
        )
        self._crop_cache[crop_name] = entry
        self._current_cache_size += stat.st_size

        return crop_path

    def render_and_crop_roi(
        self,
        roi: RequestedROI,
        pdf_path: Union[str, Path],
        fallback_to_full_page: bool = True,
    ) -> RenderedEvidence:
        """Render a PDF page and crop the requested ROI.

        Args:
            roi: The requested region of interest.
            pdf_path: Path to the PDF file.
            fallback_to_full_page: If True, return full page if crop fails.

        Returns:
            RenderedEvidence with paths to both full render and crop.
            If crop fails and fallback_to_full_page=True, crop_path will
            point to the full page and is_fallback will be True.
        """
        is_fallback = False
        crop_path = None

        # First render the full page
        try:
            png_path = self.render_pdf_page_to_png(
                pdf_path=pdf_path,
                block_id=roi.block_id,
                page=roi.page - 1,  # ROI page is 1-indexed, render expects 0-indexed
                dpi=roi.dpi
            )
        except Exception as e:
            raise RuntimeError(f"Failed to render page for block {roi.block_id}: {e}")

        # Then crop the ROI
        try:
            crop_path = self.crop_png(
                png_path=png_path,
                bbox_norm=roi.bbox_norm,
                block_id=roi.block_id,
                page=roi.page - 1,
                dpi=roi.dpi
            )
        except Exception as e:
            print(f"Warning: Crop failed for block {roi.block_id}: {e}")
            if fallback_to_full_page:
                # Fallback: use full page instead of crop
                crop_path = png_path
                is_fallback = True
            else:
                raise

        return RenderedEvidence(
            block_id=roi.block_id,
            page=roi.page - 1,
            dpi=roi.dpi,
            png_path=png_path,
            is_crop=True,
            bbox_norm=roi.bbox_norm,
            crop_path=crop_path,
            is_fallback=is_fallback,
        )

    def gather_evidence_for_rois(
        self,
        rois: list[RequestedROI],
        block_paths: dict[str, Path],
        include_full_page: bool = False
    ) -> tuple[list[Path], list[str]]:
        """Gather all evidence images for a list of ROIs.

        Args:
            rois: List of requested ROIs.
            block_paths: Mapping of block_id to PDF file paths.
            include_full_page: If True, include full page renders along with crops.

        Returns:
            Tuple of (evidence_paths, warnings):
            - evidence_paths: List of paths to evidence images
            - warnings: List of warning messages for failed operations
        """
        evidence_paths: list[Path] = []
        warnings: list[str] = []
        seen_crops: set[str] = set()

        for roi in rois:
            if roi.block_id not in block_paths:
                warnings.append(f"Block {roi.block_id} not found in available paths")
                continue

            pdf_path = block_paths[roi.block_id]

            try:
                evidence = self.render_and_crop_roi(roi, pdf_path)

                # Add full page if requested
                if include_full_page and evidence.png_path not in evidence_paths:
                    evidence_paths.append(evidence.png_path)

                # Add crop (avoid duplicates)
                crop_key = str(evidence.crop_path)
                if crop_key not in seen_crops:
                    seen_crops.add(crop_key)
                    evidence_paths.append(evidence.crop_path)

                # Note if fallback was used
                if evidence.is_fallback:
                    warnings.append(
                        f"Block {roi.block_id}: crop failed, using full page"
                    )

            except Exception as e:
                warnings.append(f"Failed to render ROI for block {roi.block_id}: {e}")

        return evidence_paths, warnings

    def clear_cache(self) -> int:
        """Clear all cached renders and crops.

        Returns:
            Number of files deleted.
        """
        deleted = 0

        for cache_subdir in [self.renders_dir, self.crops_dir]:
            for file in cache_subdir.glob("*.png"):
                try:
                    file.unlink()
                    deleted += 1
                except OSError:
                    pass

        self._render_cache.clear()
        self._crop_cache.clear()
        self._current_cache_size = 0
        return deleted

    def cleanup_old_versions(self, keep_latest_only: bool = True) -> int:
        """Remove old version files from cache.

        Args:
            keep_latest_only: If True, keep only the most recent version
                             of each block/page/dpi combination.

        Returns:
            Number of files deleted.
        """
        deleted = 0

        # Group files by base key (without version hash)
        from collections import defaultdict
        file_groups: dict[str, list[Path]] = defaultdict(list)

        for png_file in self.renders_dir.glob("*.png"):
            # Extract base key (remove version hash)
            parts = png_file.stem.rsplit("_v", 1)
            if len(parts) == 2:
                base_key = parts[0]
                file_groups[base_key].append(png_file)

        # For each group, keep only the newest file
        for base_key, files in file_groups.items():
            if len(files) <= 1:
                continue

            # Sort by modification time, newest first
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

            # Delete all but the newest
            for old_file in files[1:]:
                try:
                    size = old_file.stat().st_size
                    old_file.unlink()
                    deleted += 1
                    self._current_cache_size -= size
                except OSError:
                    pass

        return deleted

    def get_cache_stats(self) -> dict:
        """Get statistics about the cache.

        Returns:
            Dictionary with cache statistics.
        """
        render_files = list(self.renders_dir.glob("*.png"))
        crop_files = list(self.crops_dir.glob("*.png"))

        render_size = sum(f.stat().st_size for f in render_files if f.exists())
        crop_size = sum(f.stat().st_size for f in crop_files if f.exists())
        total_size = render_size + crop_size

        return {
            "renders_count": len(render_files),
            "renders_size_mb": round(render_size / (1024 * 1024), 2),
            "crops_count": len(crop_files),
            "crops_size_mb": round(crop_size / (1024 * 1024), 2),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_size_mb": self.max_cache_size_bytes / (1024 * 1024),
            "usage_percent": round(100 * total_size / self.max_cache_size_bytes, 1),
            "memory_render_entries": len(self._render_cache),
            "memory_crop_entries": len(self._crop_cache),
        }

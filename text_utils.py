"""Text utilities for string manipulation and truncation."""

from typing import Optional


def truncate_text(
    text: Optional[str],
    max_length: int,
    suffix: str = "...",
) -> Optional[str]:
    """Truncate text to maximum length with suffix.

    Args:
        text: Text to truncate. Can be None.
        max_length: Maximum length before truncation.
        suffix: Suffix to append when truncated.

    Returns:
        Original text if within limit or None, otherwise truncated with suffix.
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length] + suffix


def truncate_for_log(text: Optional[str], max_length: int = 500) -> Optional[str]:
    """Truncate text for logging purposes.

    Args:
        text: Text to truncate.
        max_length: Maximum length (default 500).

    Returns:
        Truncated text suitable for logging.
    """
    return truncate_text(text, max_length, "...")

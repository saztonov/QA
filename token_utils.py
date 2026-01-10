"""Token estimation and context truncation utilities.

Provides more accurate token estimation than simple character division,
with support for mixed Russian/English text and smart truncation.
"""

import re
from typing import Optional

import tiktoken

# Initialize tiktoken encoder (cl100k_base is used by GPT-4 and similar models)
_encoder: Optional[tiktoken.Encoding] = None


def _get_encoder() -> tiktoken.Encoding:
    """Get or create tiktoken encoder (singleton)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken.

    Args:
        text: Input text to count tokens for.

    Returns:
        Exact token count.
    """
    if not text:
        return 0
    encoder = _get_encoder()
    return len(encoder.encode(text))


# Token estimation constants based on empirical testing
# Russian text: ~2.0-2.5 chars per token (Cyrillic characters are more token-dense)
# English text: ~4.0 chars per token
# Mixed/code: ~3.0 chars per token
CHARS_PER_TOKEN_RUSSIAN = 2.2
CHARS_PER_TOKEN_ENGLISH = 4.0
CHARS_PER_TOKEN_MIXED = 3.0

# Model context limits (conservative estimates leaving room for response)
MODEL_LIMITS = {
    "gemini-3-flash-preview": 1_000_000,  # 1M context
    "gemini-3-pro-preview": 2_000_000,    # 2M context
}

# Default limits for unknown models
DEFAULT_INPUT_LIMIT = 100_000


def detect_language_ratio(text: str) -> tuple[float, float]:
    """Detect ratio of Russian (Cyrillic) vs Latin characters.

    Args:
        text: Input text to analyze.

    Returns:
        Tuple of (cyrillic_ratio, latin_ratio) where each is 0.0-1.0
    """
    if not text:
        return 0.0, 0.0

    # Count character types
    cyrillic_count = len(re.findall(r'[а-яА-ЯёЁ]', text))
    latin_count = len(re.findall(r'[a-zA-Z]', text))

    total_letters = cyrillic_count + latin_count
    if total_letters == 0:
        return 0.0, 0.0

    return cyrillic_count / total_letters, latin_count / total_letters


def estimate_tokens(text: str) -> int:
    """Estimate token count for text with language-aware calculation.

    Uses different character-per-token ratios based on detected language.
    More accurate than simple len(text) // 3 or // 4.

    Args:
        text: Input text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    cyrillic_ratio, latin_ratio = detect_language_ratio(text)

    # Calculate weighted chars-per-token based on language mix
    if cyrillic_ratio > 0.7:
        # Predominantly Russian
        chars_per_token = CHARS_PER_TOKEN_RUSSIAN
    elif latin_ratio > 0.7:
        # Predominantly English
        chars_per_token = CHARS_PER_TOKEN_ENGLISH
    else:
        # Mixed content
        chars_per_token = CHARS_PER_TOKEN_MIXED

    # Account for special tokens (newlines, punctuation add overhead)
    newline_count = text.count('\n')
    special_overhead = newline_count * 0.5  # Each newline adds ~0.5 tokens

    base_tokens = len(text) / chars_per_token
    return int(base_tokens + special_overhead)


def estimate_tokens_detailed(text: str) -> dict:
    """Get detailed token estimation with breakdown.

    Args:
        text: Input text to analyze.

    Returns:
        Dictionary with token estimate and breakdown.
    """
    if not text:
        return {
            "estimated_tokens": 0,
            "char_count": 0,
            "cyrillic_ratio": 0.0,
            "latin_ratio": 0.0,
            "chars_per_token_used": 0,
        }

    cyrillic_ratio, latin_ratio = detect_language_ratio(text)

    if cyrillic_ratio > 0.7:
        chars_per_token = CHARS_PER_TOKEN_RUSSIAN
    elif latin_ratio > 0.7:
        chars_per_token = CHARS_PER_TOKEN_ENGLISH
    else:
        chars_per_token = CHARS_PER_TOKEN_MIXED

    return {
        "estimated_tokens": estimate_tokens(text),
        "char_count": len(text),
        "cyrillic_ratio": round(cyrillic_ratio, 2),
        "latin_ratio": round(latin_ratio, 2),
        "chars_per_token_used": chars_per_token,
    }


def get_model_token_limit(model_name: str) -> int:
    """Get input token limit for a model.

    Args:
        model_name: Name of the Gemini model.

    Returns:
        Maximum input token count for the model.
    """
    return MODEL_LIMITS.get(model_name, DEFAULT_INPUT_LIMIT)


def truncate_to_token_limit(
    text: str,
    max_tokens: int,
    preserve_end: bool = False,
    truncation_message: str = "\n... (текст сокращён)",
) -> str:
    """Truncate text to fit within token limit.

    Args:
        text: Text to truncate.
        max_tokens: Maximum tokens allowed.
        preserve_end: If True, preserve end of text instead of beginning.
        truncation_message: Message to append when truncating.

    Returns:
        Truncated text within token limit.
    """
    current_tokens = estimate_tokens(text)

    if current_tokens <= max_tokens:
        return text

    # Estimate how many characters we can keep
    cyrillic_ratio, latin_ratio = detect_language_ratio(text)

    if cyrillic_ratio > 0.7:
        chars_per_token = CHARS_PER_TOKEN_RUSSIAN
    elif latin_ratio > 0.7:
        chars_per_token = CHARS_PER_TOKEN_ENGLISH
    else:
        chars_per_token = CHARS_PER_TOKEN_MIXED

    # Leave room for truncation message
    message_tokens = estimate_tokens(truncation_message)
    available_tokens = max_tokens - message_tokens
    target_chars = int(available_tokens * chars_per_token)

    if preserve_end:
        truncated = text[-target_chars:]
        return truncation_message + truncated
    else:
        truncated = text[:target_chars]
        return truncated + truncation_message


def truncate_context_smart(
    document_context: str,
    conversation_context: str,
    max_total_tokens: int,
    doc_priority: float = 0.7,
) -> tuple[str, str]:
    """Smart truncation of document and conversation context.

    Prioritizes recent conversation while keeping document context.

    Args:
        document_context: The document text.
        conversation_context: The conversation history.
        max_total_tokens: Maximum combined tokens.
        doc_priority: Ratio of tokens to allocate to document (0.0-1.0).

    Returns:
        Tuple of (truncated_document, truncated_conversation).
    """
    doc_tokens = estimate_tokens(document_context)
    conv_tokens = estimate_tokens(conversation_context)
    total = doc_tokens + conv_tokens

    if total <= max_total_tokens:
        return document_context, conversation_context

    # Allocate tokens based on priority
    doc_max = int(max_total_tokens * doc_priority)
    conv_max = max_total_tokens - doc_max

    # If conversation is small, give more to document
    if conv_tokens < conv_max:
        doc_max = max_total_tokens - conv_tokens

    # Truncate if needed
    truncated_doc = truncate_to_token_limit(
        document_context,
        doc_max,
        preserve_end=False,  # Keep beginning of document
    )

    truncated_conv = truncate_to_token_limit(
        conversation_context,
        conv_max,
        preserve_end=True,  # Keep recent messages
    )

    return truncated_doc, truncated_conv


def calculate_remaining_budget(
    system_prompt_tokens: int,
    media_tokens: int,
    model_name: str,
    response_reserve: int = 8192,
) -> int:
    """Calculate remaining token budget for user content.

    Args:
        system_prompt_tokens: Tokens used by system prompt.
        media_tokens: Estimated tokens for images/files.
        model_name: Model to use.
        response_reserve: Tokens to reserve for response.

    Returns:
        Available tokens for additional content.
    """
    model_limit = get_model_token_limit(model_name)
    used = system_prompt_tokens + media_tokens + response_reserve
    return max(0, model_limit - used)


def estimate_media_tokens(
    image_count: int = 0,
    file_count: int = 0,
    resolution: str = "MEDIA_RESOLUTION_MEDIUM",
) -> int:
    """Estimate tokens used by media files.

    Based on Gemini's media processing:
    - Images: ~258 tokens at low res, ~516 at medium, ~1024+ at high
    - PDFs: ~100 tokens per page (rough estimate)

    Args:
        image_count: Number of images.
        file_count: Number of PDF files (assuming ~5 pages each).
        resolution: Media resolution setting.

    Returns:
        Estimated token count for media.
    """
    # Image token estimates by resolution
    resolution_tokens = {
        "MEDIA_RESOLUTION_LOW": 258,
        "MEDIA_RESOLUTION_MEDIUM": 516,
        "MEDIA_RESOLUTION_HIGH": 1024,
    }

    tokens_per_image = resolution_tokens.get(resolution, 516)
    image_tokens = image_count * tokens_per_image

    # PDF estimate: ~100 tokens per page, assume 5 pages average
    pdf_tokens = file_count * 500

    return image_tokens + pdf_tokens


def format_token_stats(stats: dict) -> str:
    """Format token statistics for display.

    Args:
        stats: Dictionary with token statistics.

    Returns:
        Formatted string for UI display.
    """
    lines = []

    if "estimated_tokens" in stats:
        lines.append(f"Estimated tokens: {stats['estimated_tokens']:,}")

    if "char_count" in stats:
        lines.append(f"Characters: {stats['char_count']:,}")

    if "cyrillic_ratio" in stats:
        ru_pct = int(stats['cyrillic_ratio'] * 100)
        en_pct = int(stats.get('latin_ratio', 0) * 100)
        lines.append(f"Language: {ru_pct}% RU, {en_pct}% EN")

    return " | ".join(lines)

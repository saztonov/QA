"""API utilities for Gemini client operations."""

import time
from typing import Callable, Optional, Any

from google import genai
from google.genai import types


# Retry configuration constants
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # Base delay in seconds
RETRY_DELAY_MULTIPLIER = 2.0  # Exponential backoff multiplier


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        delay_base: float = RETRY_DELAY_BASE,
        delay_multiplier: float = RETRY_DELAY_MULTIPLIER,
    ):
        self.max_retries = max_retries
        self.delay_base = delay_base
        self.delay_multiplier = delay_multiplier


def execute_with_retry(
    client: genai.Client,
    model: str,
    contents: Any,
    config: types.GenerateContentConfig,
    retry_config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> str:
    """Execute Gemini API call with exponential backoff retry.

    Args:
        client: Gemini client instance.
        model: Model name to use.
        contents: Content to send (string or list).
        config: Generation configuration.
        retry_config: Optional custom retry configuration.
        on_retry: Optional callback for retry events (attempt, error, delay).

    Returns:
        Response text from the API.

    Raises:
        Exception: If all retries fail, raises the last error.
    """
    retry_config = retry_config or RetryConfig()
    last_error = None

    for attempt in range(retry_config.max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response.text.strip()

        except Exception as e:
            last_error = e
            if attempt < retry_config.max_retries - 1:
                delay = retry_config.delay_base * (
                    retry_config.delay_multiplier ** attempt
                )
                if on_retry:
                    on_retry(attempt, e, delay)
                else:
                    print(
                        f"API error (attempt {attempt + 1}/{retry_config.max_retries}): {e}"
                    )
                    print(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)

    raise last_error

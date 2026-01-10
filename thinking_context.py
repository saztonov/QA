"""Thought signatures context management for multi-turn conversations.

This module manages thought signatures from Gemini API responses to maintain
reasoning context across multiple conversation turns. Without signatures,
the model "forgets" its reasoning between requests.

See: https://ai.google.dev/gemini-api/docs/thought-signatures
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ThinkingContext:
    """Stores thought signatures for conversation continuity.

    Thought signatures are encrypted representations of the model's reasoning
    process. They must be passed back to the API in subsequent requests to
    maintain context continuity.
    """

    signatures: List[Dict[str, Any]] = field(default_factory=list)
    thoughts_history: List[str] = field(default_factory=list)

    def add_from_response(self, response) -> Optional[str]:
        """Extract and store signature from response.

        Args:
            response: The Gemini API response object.

        Returns:
            The thought text if found, None otherwise.
        """
        thought_text = None

        try:
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            # Extract thought signature
                            if hasattr(part, 'thought_signature') and part.thought_signature:
                                self.signatures.append({
                                    "signature": part.thought_signature,
                                    "turn_id": len(self.signatures)
                                })

                            # Extract thought text
                            if hasattr(part, 'thought') and part.thought:
                                thought_text = part.text
                                self.thoughts_history.append(thought_text)
        except Exception:
            pass

        return thought_text

    def add_signature(self, signature: str) -> None:
        """Add a thought signature directly.

        Args:
            signature: The thought signature string.
        """
        if signature:
            self.signatures.append({
                "signature": signature,
                "turn_id": len(self.signatures)
            })

    def get_latest_signature(self) -> Optional[str]:
        """Get the most recent thought signature.

        Returns:
            The latest signature string or None.
        """
        if self.signatures:
            return self.signatures[-1].get("signature")
        return None

    def get_all_signatures(self) -> List[str]:
        """Get all stored signatures.

        Returns:
            List of signature strings.
        """
        return [s.get("signature") for s in self.signatures if s.get("signature")]

    def build_contents_with_history(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]] = None
    ) -> List[Any]:
        """Build contents list with conversation history and signatures.

        Args:
            user_message: The current user message.
            conversation_history: Optional previous conversation turns.

        Returns:
            Contents list ready for API request.
        """
        contents = []

        # Add conversation history with signatures
        if conversation_history:
            for i, turn in enumerate(conversation_history):
                turn_content = {
                    "role": turn.get("role", "user"),
                    "parts": turn.get("parts", [])
                }

                # Add signature if available for model responses
                if turn.get("role") == "model" and i < len(self.signatures):
                    sig = self.signatures[i].get("signature")
                    if sig:
                        # Include signature in the parts
                        turn_content["parts"] = [
                            {"thought_signature": sig}
                        ] + turn_content["parts"]

                contents.append(turn_content)

        # Add current user message
        contents.append(user_message)

        return contents

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the thinking context.

        Returns:
            Dictionary with context statistics.
        """
        return {
            "signatures_count": len(self.signatures),
            "thoughts_count": len(self.thoughts_history),
            "total_thoughts_length": sum(len(t) for t in self.thoughts_history),
            "has_signatures": len(self.signatures) > 0,
        }

    def clear(self) -> None:
        """Clear all signatures and thoughts (new conversation)."""
        self.signatures.clear()
        self.thoughts_history.clear()

    def __len__(self) -> int:
        """Return number of stored signatures."""
        return len(self.signatures)

    def __bool__(self) -> bool:
        """Return True if any signatures are stored."""
        return len(self.signatures) > 0

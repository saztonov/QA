"""Pydantic schemas for structured outputs from Gemini API."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PlanDecision(str, Enum):
    """Decision types for the planning step."""

    ANSWER_FROM_TEXT = "ANSWER_FROM_TEXT"  # Can answer from text context alone
    NEED_BLOCKS = "NEED_BLOCKS"  # Need to load graphical blocks
    NEED_ZOOM_ROI = "NEED_ZOOM_ROI"  # Need zoomed region of interest
    ASK_USER = "ASK_USER"  # Need clarification from user


class BlockPriority(str, Enum):
    """Priority levels for requested blocks."""

    HIGH = "high"  # Critical for answering
    MEDIUM = "medium"  # Helpful but not critical
    LOW = "low"  # Nice to have


class RequestedBlock(BaseModel):
    """A request for a specific document block."""

    block_id: str = Field(
        description="ID of the block to request (e.g., 'NWEK-9MHK-YHD')"
    )
    priority: BlockPriority = Field(
        default=BlockPriority.MEDIUM,
        description="Priority of this block for answering the question"
    )
    reason: str = Field(
        description="Why this block is needed to answer the question"
    )


class BBoxNorm(BaseModel):
    """Normalized bounding box coordinates (0.0 to 1.0)."""

    x0: float = Field(ge=0.0, le=1.0, description="Left edge (0.0-1.0)")
    y0: float = Field(ge=0.0, le=1.0, description="Top edge (0.0-1.0)")
    x1: float = Field(ge=0.0, le=1.0, description="Right edge (0.0-1.0)")
    y1: float = Field(ge=0.0, le=1.0, description="Bottom edge (0.0-1.0)")


class RequestedROI(BaseModel):
    """A request for a zoomed region of interest."""

    block_id: str = Field(
        description="ID of the block containing the ROI"
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number within the block (1-indexed)"
    )
    bbox_norm: BBoxNorm = Field(
        description="Normalized bounding box for the region of interest"
    )
    dpi: int = Field(
        default=150,
        ge=72,
        le=600,
        description="DPI for rendering the ROI (72-600)"
    )
    reason: str = Field(
        description="Why this specific region needs closer examination"
    )


class UserRequestKind(str, Enum):
    """Types of clarification requests to the user."""

    CLARIFY_QUESTION = "clarify_question"  # Question is ambiguous
    CHOOSE_OPTION = "choose_option"  # Multiple interpretations possible
    PROVIDE_CONTEXT = "provide_context"  # Need additional context
    CONFIRM_SCOPE = "confirm_scope"  # Confirm the scope of analysis


class UserRequest(BaseModel):
    """A request for clarification from the user."""

    kind: UserRequestKind = Field(
        description="Type of clarification needed"
    )
    text: str = Field(
        description="The question or request to show to the user"
    )


class Plan(BaseModel):
    """Planning response from the model - determines how to proceed with the query."""

    decision: PlanDecision = Field(
        description="The decision on how to proceed with answering"
    )
    reasoning: str = Field(
        description="Brief explanation of why this decision was made"
    )
    requested_blocks: list[RequestedBlock] = Field(
        default_factory=list,
        description="List of blocks to request (if decision is NEED_BLOCKS)"
    )
    requested_rois: list[RequestedROI] = Field(
        default_factory=list,
        description="List of ROIs to render (if decision is NEED_ZOOM_ROI)"
    )
    user_requests: list[UserRequest] = Field(
        default_factory=list,
        description="List of clarifications needed (if decision is ASK_USER)"
    )

    def get_block_ids(self) -> list[str]:
        """Get list of all requested block IDs."""
        return [block.block_id for block in self.requested_blocks]

    def get_high_priority_blocks(self) -> list[RequestedBlock]:
        """Get only high priority blocks."""
        return [b for b in self.requested_blocks if b.priority == BlockPriority.HIGH]


# =============================================================================
# Answer Schema (Pro model response)
# =============================================================================

class CitationKind(str, Enum):
    """Types of citations in the answer."""

    TEXT_BLOCK = "text_block"  # Reference to a text block
    IMAGE_BLOCK = "image_block"  # Reference to an image/drawing block


class Citation(BaseModel):
    """A citation referencing a source in the document."""

    kind: CitationKind = Field(
        description="Type of the cited block"
    )
    id: str = Field(
        description="Block ID being cited"
    )
    page: Optional[int] = Field(
        default=None,
        description="Page number where the citation appears"
    )
    note: str = Field(
        default="",
        description="Brief note about what this citation supports"
    )


class FollowupBlock(BaseModel):
    """A followup request for additional block."""

    block_id: str = Field(
        description="ID of the block needed"
    )
    reason: str = Field(
        description="Why this block is needed for a more complete answer"
    )


class FollowupROI(BaseModel):
    """A followup request for a specific ROI."""

    block_id: str = Field(
        description="ID of the block containing the ROI"
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (1-indexed)"
    )
    bbox_norm: BBoxNorm = Field(
        description="Normalized bounding box for the ROI"
    )
    dpi: int = Field(
        default=200,
        ge=72,
        le=600,
        description="DPI for rendering"
    )
    reason: str = Field(
        description="Why this ROI needs examination"
    )


class Answer(BaseModel):
    """Structured answer from the Pro model."""

    answer_markdown: str = Field(
        description="The complete answer in Markdown format"
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="List of citations supporting the answer"
    )
    needs_more_evidence: bool = Field(
        default=False,
        description="Whether additional evidence is needed for a complete answer"
    )
    followup_blocks: list[FollowupBlock] = Field(
        default_factory=list,
        description="Additional blocks needed if needs_more_evidence is true"
    )
    followup_rois: list[FollowupROI] = Field(
        default_factory=list,
        description="Additional ROIs needed if needs_more_evidence is true"
    )
    confidence: str = Field(
        default="medium",
        description="Confidence level: high, medium, or low"
    )

    def has_followup_requests(self) -> bool:
        """Check if there are any followup requests."""
        return bool(self.followup_blocks or self.followup_rois)

    def get_followup_block_ids(self) -> list[str]:
        """Get list of followup block IDs."""
        return [b.block_id for b in self.followup_blocks]


# JSON Schema for Answer (Pro model)
ANSWER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_markdown": {
            "type": "string",
            "description": "The complete answer in Markdown format"
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["text_block", "image_block"],
                        "description": "Type of cited block"
                    },
                    "id": {
                        "type": "string",
                        "description": "Block ID being cited"
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number"
                    },
                    "note": {
                        "type": "string",
                        "description": "Brief note about the citation"
                    }
                },
                "required": ["kind", "id", "note"]
            },
            "description": "Citations supporting the answer"
        },
        "needs_more_evidence": {
            "type": "boolean",
            "description": "Whether more evidence is needed"
        },
        "followup_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "Block ID needed"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this block is needed"
                    }
                },
                "required": ["block_id", "reason"]
            },
            "description": "Additional blocks needed"
        },
        "followup_rois": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "Block ID containing the ROI"
                    },
                    "page": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Page number (1-indexed)"
                    },
                    "bbox_norm": {
                        "type": "object",
                        "properties": {
                            "x0": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "y0": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "x1": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "y1": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                        },
                        "required": ["x0", "y0", "x1", "y1"]
                    },
                    "dpi": {
                        "type": "integer",
                        "minimum": 72,
                        "maximum": 600
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this ROI is needed"
                    }
                },
                "required": ["block_id", "page", "bbox_norm", "dpi", "reason"]
            },
            "description": "Additional ROIs needed"
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence level of the answer"
        }
    },
    "required": ["answer_markdown", "citations", "needs_more_evidence", "followup_blocks", "followup_rois", "confidence"]
}


# =============================================================================
# Chat Response Schema (for GeminiClient structured outputs)
# =============================================================================

class ChatBlockRequest(BaseModel):
    """A request for a specific document block in chat mode."""

    block_id: str = Field(
        description="ID of the block to request (e.g., 'NWEK-9MHK-YHD')"
    )
    block_type: str = Field(
        default="IMAGE",
        description="Type of block: IMAGE or TEXT"
    )
    reason: str = Field(
        default="",
        description="Why this block is needed"
    )


class ChatImageRequest(BaseModel):
    """A request for a specific image in chat mode."""

    filename: str = Field(
        description="Name or description of the requested image"
    )
    description: str = Field(
        default="",
        description="Additional context about what is needed"
    )


class ChatResponse(BaseModel):
    """Structured response from the model in chat mode.

    This schema replaces regex-based parsing of model responses.
    """

    response_text: str = Field(
        description="The main response text to show to the user"
    )
    needs_blocks: bool = Field(
        default=False,
        description="Whether the model needs document blocks to continue"
    )
    requested_blocks: list[ChatBlockRequest] = Field(
        default_factory=list,
        description="List of blocks needed if needs_blocks is true"
    )
    needs_images: bool = Field(
        default=False,
        description="Whether the model needs images to continue"
    )
    requested_images: list[ChatImageRequest] = Field(
        default_factory=list,
        description="List of images needed if needs_images is true"
    )
    is_complete: bool = Field(
        default=True,
        description="Whether this response fully answers the question"
    )


# JSON Schema for ChatResponse (used by GeminiClient)
CHAT_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "response_text": {
            "type": "string",
            "description": "The main response text to show to the user"
        },
        "needs_blocks": {
            "type": "boolean",
            "description": "Whether document blocks are needed"
        },
        "requested_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "ID of the block to request"
                    },
                    "block_type": {
                        "type": "string",
                        "enum": ["IMAGE", "TEXT"],
                        "description": "Type of block"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this block is needed"
                    }
                },
                "required": ["block_id"]
            },
            "description": "List of blocks needed"
        },
        "needs_images": {
            "type": "boolean",
            "description": "Whether images are needed"
        },
        "requested_images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the requested image"
                    },
                    "description": {
                        "type": "string",
                        "description": "Additional context"
                    }
                },
                "required": ["filename"]
            },
            "description": "List of images needed"
        },
        "is_complete": {
            "type": "boolean",
            "description": "Whether the response fully answers the question"
        }
    },
    "required": ["response_text", "needs_blocks", "requested_blocks", "needs_images", "requested_images", "is_complete"]
}


# JSON Schema for Google Generative AI SDK
# This can be used with response_schema parameter
PLAN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["ANSWER_FROM_TEXT", "NEED_BLOCKS", "NEED_ZOOM_ROI", "ASK_USER"],
            "description": "The decision on how to proceed with answering"
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of why this decision was made"
        },
        "requested_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "ID of the block to request"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority of this block"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this block is needed"
                    }
                },
                "required": ["block_id", "priority", "reason"]
            },
            "description": "List of blocks to request"
        },
        "requested_rois": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "ID of the block containing the ROI"
                    },
                    "page": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Page number (1-indexed)"
                    },
                    "bbox_norm": {
                        "type": "object",
                        "properties": {
                            "x0": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "y0": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "x1": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "y1": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                        },
                        "required": ["x0", "y0", "x1", "y1"],
                        "description": "Normalized bounding box"
                    },
                    "dpi": {
                        "type": "integer",
                        "minimum": 72,
                        "maximum": 600,
                        "description": "DPI for rendering"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this ROI needs examination"
                    }
                },
                "required": ["block_id", "page", "bbox_norm", "dpi", "reason"]
            },
            "description": "List of ROIs to render"
        },
        "user_requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["clarify_question", "choose_option", "provide_context", "confirm_scope"],
                        "description": "Type of clarification"
                    },
                    "text": {
                        "type": "string",
                        "description": "The question to show to user"
                    }
                },
                "required": ["kind", "text"]
            },
            "description": "List of clarifications needed"
        }
    },
    "required": ["decision", "reasoning", "requested_blocks", "requested_rois", "user_requests"]
}

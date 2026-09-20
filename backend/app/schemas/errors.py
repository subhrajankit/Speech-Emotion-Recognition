"""
Standardized error schema for VoiceSense AI.
Provides consistent error response structure across all REST and WebSocket boundaries.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Dict[str, Any] = Field(default_factory=dict, description="Optional diagnostic details")


class ErrorResponse(BaseModel):
    error: ErrorDetail


def create_error_payload(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Helper to generate standardized error dictionary."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {}
        }
    }

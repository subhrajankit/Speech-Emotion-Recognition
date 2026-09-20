"""Backend Pydantic schemas package."""
from .errors import ErrorDetail, ErrorResponse, create_error_payload
from .speech import SpeechResult
from .prediction import PredictionResponse

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "create_error_payload",
    "SpeechResult",
    "PredictionResponse",
]

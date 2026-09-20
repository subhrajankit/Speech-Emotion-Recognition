"""
Prediction API router for VoiceSense AI.
Handles POST /api/predict sharing the identical service pipeline as /api/speech/upload,
returning PredictionResponse with an optional assistant block.
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form

from backend.app.schemas.prediction import PredictionResponse
from backend.app.api.speech import process_audio_upload

router = APIRouter(prefix="/api", tags=["prediction"])


@router.post("/predict", response_model=PredictionResponse)
async def predict_speech(
    file: UploadFile = File(..., description="Audio recording file"),
    language_hint: Optional[str] = Form(default=None, description="Optional ISO 639-1 language code hint"),
    include_assistant: bool = Form(default=False, description="Whether to include downstream assistant response block")
) -> PredictionResponse:
    """
    Performs speech perception and returns SpeechResult with an optional assistant block.
    Shares the exact same in-memory decode and speech_service call as /api/speech/upload.
    """
    speech_result = await process_audio_upload(file=file, language_hint=language_hint)

    # In Phase 2, assistant is None (or stub if requested); ready for future LLM phases
    assistant_block = None
    if include_assistant:
        assistant_block = {
            "status": "not_configured",
            "message": "Assistant LLM reasoning is not configured in Phase 2."
        }

    return PredictionResponse(
        **speech_result.model_dump(),
        assistant=assistant_block
    )

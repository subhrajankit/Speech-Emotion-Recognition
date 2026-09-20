"""
Speech upload API router for VoiceSense AI.
Handles POST /api/speech/upload with in-memory decoding and zero disk persistence.
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

from ai.inference.types import SpeechResult
from backend.app.core.config import settings
from backend.app.schemas.errors import create_error_payload
from backend.app.services.speech_service import speech_service

router = APIRouter(prefix="/api/speech", tags=["speech"])


async def process_audio_upload(
    file: UploadFile,
    language_hint: Optional[str] = None
) -> SpeechResult:
    """
    Shared handler for processing audio file uploads.
    Validates content type and size limits, decodes strictly in RAM,
    and invokes the non-blocking SpeechService.
    """
    # 1. Content-Type validation
    content_type = (file.content_type or "").lower().strip()
    filename = (file.filename or "").lower()

    is_valid_type = (
        content_type in settings.ALLOWED_AUDIO_MIME_TYPES
        or any(filename.endswith(ext) for ext in (".wav", ".mp3", ".ogg", ".flac", ".webm", ".m4a"))
    )

    if not is_valid_type or content_type == "text/plain":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=create_error_payload(
                code="INVALID_CONTENT_TYPE",
                message=f"Unsupported media type '{file.content_type}'. Expected valid audio media.",
                details={"allowed_mime_types": settings.ALLOWED_AUDIO_MIME_TYPES}
            )
        )

    # 2. Read in-memory bytes
    audio_bytes = await file.read()

    # 3. Size limit check
    if len(audio_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=create_error_payload(
                code="FILE_TOO_LARGE",
                message=f"Uploaded audio ({len(audio_bytes)} bytes) exceeds limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes.",
                details={"max_size_bytes": settings.MAX_UPLOAD_SIZE_BYTES, "received_bytes": len(audio_bytes)}
            )
        )

    # 4. Empty file check
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_payload(
                code="EMPTY_AUDIO",
                message="Uploaded audio file contains 0 bytes.",
                details={"file_name": file.filename}
            )
        )

    # 5. Audio container check for RIFF/WAV files
    if audio_bytes.startswith(b"RIFF") or filename.endswith(".wav"):
        import io
        import soundfile as sf
        try:
            with io.BytesIO(audio_bytes) as bio:
                sf.read(bio)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=create_error_payload(
                    code="DECODE_ERROR",
                    message=f"Corrupted or invalid WAV audio data: {e}",
                    details={"error": str(e)}
                )
            )

    # 6. In-memory transcription
    try:
        result = await speech_service.transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            sample_rate=16000,
            language_hint=language_hint
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_payload(
                code="DECODE_ERROR",
                message=f"Audio decoding failed: {e}",
                details={"error": str(e)}
            )
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_payload(
                code="INFERENCE_ERROR",
                message=f"Speech inference failed: {e}",
                details={"error": str(e)}
            )
        )


@router.post("/upload", response_model=SpeechResult)
async def upload_speech(
    file: UploadFile = File(..., description="Audio recording file (WAV, MP3, FLAC, OGG)"),
    language_hint: Optional[str] = Form(default=None, description="Optional ISO 639-1 language code hint")
) -> SpeechResult:
    """
    Decodes audio in memory and returns SpeechResult.
    Stores zero audio on disk.
    """
    return await process_audio_upload(file=file, language_hint=language_hint)

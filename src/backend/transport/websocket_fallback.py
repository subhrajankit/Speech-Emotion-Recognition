import json
import logging
import uuid
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from ..audio.vad import VADSpeechSegmenter
from ..config import settings
from ..models.manager import model_manager
from ..pipeline import VoicePipeline
from ..security import (
    AuthenticationError,
    verify_access_token,
    rate_limiter,
    AudioDurationLimitExceeded,
    UtteranceRateLimitExceeded,
)

logger = logging.getLogger("senseai.transport.websocket")

async def websocket_voice_endpoint(websocket: WebSocket, pipeline: Optional[VoicePipeline] = None):
    """
    WebSocket endpoint accepting continuous raw PCM 16kHz mono audio chunks.
    Runs Silero VAD on each frame and triggers processing only once a full speech
    segment (speech-start to speech-end-with-silence-timeout) is detected.

    Enforces JWT authentication handshake and session rate limits (Phase 11).
    Acts as the primary reliable fallback transport when WebTransport is unavailable.
    """
    # 1. JWT Authentication Handshake Check
    token = websocket.query_params.get("token")
    if settings.REQUIRE_AUTH:
        if not token:
            logger.warning("Rejecting WebSocket connection: missing 'token' query parameter.")
            await websocket.close(code=1008, reason="Authentication required: token missing")
            return
        try:
            claims = verify_access_token(token)
            session_id = claims.get("sub", f"auth_{uuid.uuid4().hex[:8]}")
        except AuthenticationError as e:
            logger.warning(f"Rejecting WebSocket connection due to invalid token: {e}")
            await websocket.close(code=1008, reason=f"Authentication failed: {e}")
            return
    else:
        if token:
            try:
                claims = verify_access_token(token)
                session_id = claims.get("sub", f"auth_{uuid.uuid4().hex[:8]}")
            except Exception:
                session_id = f"sess_{uuid.uuid4().hex[:8]}"
        else:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

    await websocket.accept()

    conversation_id = f"conv_{session_id}"
    session_llm_provider = websocket.query_params.get("llm_provider")
    logger.info(f"Client authenticated and connected to /ws/voice with conversation_id='{conversation_id}' (llm_provider={session_llm_provider}).")

    if pipeline is None:
        pipeline = VoicePipeline()

    if not model_manager.initialized:
        model_manager.initialize()

    segmenter = VADSpeechSegmenter(
        vad=model_manager.vad,
        silence_timeout_ms=settings.SILENCE_TIMEOUT_MS,
        speech_threshold=settings.VAD_THRESHOLD
    )

    async def _execute_and_respond(audio_bytes: bytes):
        # Enforce rate limit (max utterances per minute per session)
        try:
            rate_limiter.record_utterance(session_id)
        except UtteranceRateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded for session '{session_id}': {e}")
            await websocket.send_json({
                "type": "error",
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": str(e),
                "conversation_id": conversation_id
            })
            return

        duration_sec = len(audio_bytes) / 32000.0
        logger.info(f"Processing VAD-segmented utterance of {duration_sec:.2f}s ({len(audio_bytes)} bytes)...")
        await websocket.send_json({"type": "status", "stage": "processing", "conversation_id": conversation_id})

        first_audio_chunk = None

        async for event_type, payload in pipeline.stream_utterance(audio_bytes, conversation_id=conversation_id, llm_provider=session_llm_provider):
            if event_type == "metadata":
                await websocket.send_json({
                    "type": "llm_start",
                    "conversation_id": conversation_id,
                    "transcript": payload.get("transcript"),
                    "context": payload.get("context"),
                    "intent": payload.get("intent"),
                    "emotion": payload.get("emotion"),
                    "llm_provider": payload.get("llm_provider")
                })
            elif event_type == "sentence":
                chunk_idx = payload.get("index", 0)
                sentence_text = payload.get("text", "")
                wav_chunk = payload.get("audio_bytes")
                chunk_latencies = payload.get("latencies", {})
                if first_audio_chunk is None and wav_chunk:
                    first_audio_chunk = wav_chunk

                # 1. Notify client that a sentence is ready
                await websocket.send_json({
                    "type": "sentence_start",
                    "conversation_id": conversation_id,
                    "index": chunk_idx,
                    "text": sentence_text,
                    "latencies": chunk_latencies
                })

                # 2. Stream binary audio frame for this sentence
                if wav_chunk:
                    await websocket.send_bytes(wav_chunk)

                # 3. Mark sentence transmission complete
                await websocket.send_json({
                    "type": "sentence_end",
                    "conversation_id": conversation_id,
                    "index": chunk_idx
                })

            elif event_type == "complete":
                # Final streaming turn completion event
                await websocket.send_json({
                    "type": "turn_complete",
                    "conversation_id": conversation_id,
                    "transcript": payload.get("transcript"),
                    "response_text": payload.get("response_text"),
                    "latencies": payload.get("latencies"),
                    "context": payload.get("context"),
                    "intent": payload.get("intent"),
                    "emotion": payload.get("emotion"),
                    "llm_provider": payload.get("llm_provider")
                })

                # Backward compatibility with existing tests / clients
                await websocket.send_json({
                    "type": "result",
                    "conversation_id": conversation_id,
                    "transcript": payload.get("transcript"),
                    "response_text": payload.get("response_text"),
                    "latencies": payload.get("latencies"),
                    "context": payload.get("context"),
                    "intent": payload.get("intent"),
                    "emotion": payload.get("emotion"),
                    "llm_provider": payload.get("llm_provider")
                })
                await websocket.send_json({"type": "playback_ready"})

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                # Validate accumulated audio against maximum duration cap
                if segmenter.in_speech:
                    try:
                        rate_limiter.validate_audio_chunk(len(segmenter.speech_buffer))
                    except AudioDurationLimitExceeded as e:
                        logger.warning(f"Audio duration cap exceeded for session '{session_id}': {e}")
                        segmenter.reset()
                        await websocket.send_json({
                            "type": "error",
                            "error_code": "AUDIO_DURATION_LIMIT_EXCEEDED",
                            "message": str(e),
                            "conversation_id": conversation_id
                        })
                        continue

                # Stream chunk to VAD segmenter
                completed_utterance = segmenter.process_chunk(message["bytes"])
                if completed_utterance:
                    await _execute_and_respond(completed_utterance)

            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                except Exception:
                    data = {"action": message["text"]}

                if "conversation_id" in data and data["conversation_id"]:
                    conversation_id = data["conversation_id"]

                action = data.get("action") or data.get("type")

                if action == "ping":
                    await websocket.send_json({"type": "pong", "conversation_id": conversation_id})

                elif action == "reset":
                    segmenter.reset()
                    await websocket.send_json({"type": "status", "message": "VAD segmenter reset."})

                elif action in ("end-of-utterance", "end_of_utterance"):
                    # Manual flush if client forces end-of-utterance
                    manual_utterance = segmenter.flush()
                    if manual_utterance:
                        await _execute_and_respond(manual_utterance)
                    else:
                        await websocket.send_json({
                            "type": "warning",
                            "message": "Empty audio buffer: no speech detected before end_of_utterance."
                        })

                elif action in ("set_llm_provider", "set-llm-provider"):
                    new_provider = data.get("provider", "local")
                    session_llm_provider = new_provider
                    logger.info(f"Session '{session_id}' switched LLM provider to '{new_provider}'.")
                    await websocket.send_json({
                        "type": "status",
                        "message": f"LLM provider set to '{new_provider}'.",
                        "llm_provider": new_provider
                    })

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from /ws/voice (conversation_id='{conversation_id}').")
    except Exception as e:
        logger.error(f"Unexpected error in /ws/voice connection: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        segmenter.reset()

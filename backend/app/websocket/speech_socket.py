"""
WebSocket speech streaming endpoint for VoiceSense AI.
Implements WebSocket protocol v1 with server-side VAD segmentation,
non-blocking inference, per-connection buffer limits, keepalives, and auth gating.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ai.preprocessing.vad import SileroVAD, VADSpeechSegmenter
from backend.app.core.config import settings
from backend.app.core.security import verify_access_token, AuthenticationError
from backend.app.services.speech_service import speech_service
from backend.app.services.llm_service import (
    llm_service,
    LLMError,
    LLMUnavailable,
    LLMTimeout,
    LLMResponseError,
)
from backend.app.services.prompt_builder import PromptBuilder
from backend.app.services.rag_service import rag_service

logger = logging.getLogger("voicesense.websocket")

router = APIRouter(tags=["websocket"])

RESERVED_MESSAGE_TYPES = {
    "llm_delta",
    "llm_done",
    "tts_chunk",
    "tts_done",
    "status",
    "rag_sources",
}


async def safe_send_json(websocket: WebSocket, data: Dict[str, Any]) -> bool:
    """Sends JSON to client safely, suppressing disconnect exceptions."""
    try:
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def handle_llm_turn(
    websocket: WebSocket,
    transcript: str,
    emotion: Optional[str],
    language: Optional[str],
    conversation_history: List[Dict[str, str]],
):
    """
    Invokes LLM reasoning strictly AFTER speech_result has been sent.
    Streams llm_delta tokens and emits llm_done upon completion.
    On failure, emits {"type": "error", "code": "llm_unavailable", "message": ...}
    and keeps the socket open.
    Supports clean cancellation via asyncio.CancelledError when a new 'start'
    or client disconnect occurs.
    """
    transcript_clean = transcript.strip() if transcript else ""
    if not transcript_clean:
        return

    # Phase 7: Intent-Gated RAG (Normal conversation never touches FAISS)
    rag_turn = await rag_service.process_turn(transcript_clean)
    if rag_turn.intent.intent == "knowledge_query":
        if rag_turn.retrieval_performed and rag_turn.cited_docs:
            await safe_send_json(websocket, {
                "type": "rag_sources",
                "sources": rag_turn.cited_docs,
            })
        elif not rag_turn.retrieval_performed or not rag_turn.chunks:
            await safe_send_json(websocket, {
                "type": "status",
                "status": "rag_fallback",
                "message": "Knowledge base index unavailable or no relevant chunks found; falling back to direct chat.",
            })

    messages = PromptBuilder.build_chat_messages(
        transcript=transcript_clean,
        conversation_history=conversation_history,
        emotion=emotion,
        language=language,
        grounded_context=rag_turn.grounded_context,
        cited_docs=rag_turn.cited_docs,
    )

    full_response_parts: List[str] = []
    try:
        stream = await llm_service.generate(
            messages=messages,
            emotion=emotion,
            language=language,
            stream=True,
        )
        async for delta in stream:
            if delta:
                full_response_parts.append(delta)
                sent = await safe_send_json(websocket, {
                    "type": "llm_delta",
                    "delta": delta,
                })
                if not sent:
                    return

        full_text = "".join(full_response_parts).strip()
        await safe_send_json(websocket, {
            "type": "llm_done",
            "text": full_text,
            "sources": rag_turn.cited_docs if (rag_turn.retrieval_performed and rag_turn.cited_docs) else [],
        })

        # Update in-memory conversation history
        conversation_history.append({"role": "user", "content": transcript_clean})
        if full_text:
            conversation_history.append({"role": "assistant", "content": full_text})

    except asyncio.CancelledError:
        logger.info("In-flight LLM stream cancelled (barge-in / disconnect).")
        raise
    except (LLMUnavailable, LLMTimeout, LLMResponseError, LLMError) as e:
        logger.warning(f"LLM generation failed: {e}")
        await safe_send_json(websocket, {
            "type": "error",
            "code": "llm_unavailable",
            "message": str(e),
        })
    except Exception as e:
        logger.error(f"Unexpected error in LLM turn: {e}")
        await safe_send_json(websocket, {
            "type": "error",
            "code": "llm_unavailable",
            "message": f"LLM error: {e}",
        })


@router.websocket("/ws/speech")
async def speech_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket voice endpoint:
    Client -> server:
      {"type":"start","sample_rate":16000,"encoding":"pcm_s16le","language_hint":null}
      binary frames of PCM16 mono audio
      {"type":"stop"}
    Server -> client:
      {"type":"ready"}
      {"type":"vad","state":"speech_start"|"speech_end"}
      {"type":"speech_result", ...SpeechResult}
      {"type":"error","code":"...","message":"..."}
    """
    # 1. Auth gating if AUTH_REQUIRED is enabled
    if settings.AUTH_REQUIRED:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication required: missing token query parameter"
            )
            return

        try:
            verify_access_token(token)
        except AuthenticationError as e:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=f"Authentication failed: {e}"
            )
            return

    await websocket.accept()

    # Per-connection session state
    is_started = False
    sample_rate = 16000
    encoding = "pcm_s16le"
    language_hint: Optional[str] = None
    conversation_history: List[Dict[str, str]] = []
    active_llm_task: Optional[asyncio.Task] = None

    async def cancel_active_llm():
        nonlocal active_llm_task
        if active_llm_task and not active_llm_task.done():
            active_llm_task.cancel()
            try:
                await active_llm_task
            except (asyncio.CancelledError, Exception):
                pass
            active_llm_task = None

    vad = SileroVAD(threshold=settings.VAD_THRESHOLD, mock=settings.MOCK_MODELS)
    segmenter = VADSpeechSegmenter(
        vad=vad,
        silence_timeout_ms=700,
        speech_threshold=settings.VAD_THRESHOLD,
        sample_rate=sample_rate,
        pre_padding_ms=250
    )

    total_accumulated_bytes = 0
    was_in_speech = False

    try:
        while True:
            message = await websocket.receive()
            msg_type = message.get("type")

            # Handle text JSON control messages
            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "code": "INVALID_JSON",
                        "message": "Malformed JSON payload"
                    })
                    continue

                action = payload.get("type")

                # Keepalive ping
                if action == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                # Start streaming session (cancels any in-flight LLM stream)
                if action == "start":
                    await cancel_active_llm()
                    sample_rate = int(payload.get("sample_rate", 16000))
                    encoding = payload.get("encoding", "pcm_s16le")
                    language_hint = payload.get("language_hint")

                    segmenter.sample_rate = sample_rate
                    segmenter.reset()
                    total_accumulated_bytes = 0
                    is_started = True
                    was_in_speech = False

                    await websocket.send_json({"type": "ready"})
                    continue

                # Stop streaming session / flush current speech
                if action == "stop":
                    if not is_started:
                        continue

                    flushed_audio = segmenter.flush()
                    if was_in_speech:
                        await safe_send_json(websocket, {
                            "type": "vad",
                            "state": "speech_end"
                        })
                        was_in_speech = False

                    if flushed_audio and len(flushed_audio) >= 1024:
                        try:
                            speech_res = await speech_service.transcribe_pcm16_bytes(
                                pcm_bytes=flushed_audio,
                                sample_rate=sample_rate,
                                language_hint=language_hint
                            )
                            await safe_send_json(websocket, {
                                "type": "speech_result",
                                **speech_res.model_dump()
                            })
                            await cancel_active_llm()
                            active_llm_task = asyncio.create_task(
                                handle_llm_turn(
                                    websocket=websocket,
                                    transcript=speech_res.transcript,
                                    emotion=speech_res.emotion,
                                    language=speech_res.language,
                                    conversation_history=conversation_history,
                                )
                            )
                        except Exception as e:
                            logger.error(f"Inference error during stop flush: {e}")
                            await safe_send_json(websocket, {
                                "type": "error",
                                "code": "INFERENCE_ERROR",
                                "message": str(e)
                            })

                    is_started = False
                    total_accumulated_bytes = 0
                    continue

                # Ignore reserved or unknown control message types safely
                if action in RESERVED_MESSAGE_TYPES or action is not None:
                    logger.debug(f"Ignoring message type: '{action}'")
                    continue

            # Handle binary PCM16 audio frames
            elif "bytes" in message and message["bytes"]:
                chunk = message["bytes"]

                if not is_started:
                    # Auto-start or request start frame
                    await websocket.send_json({
                        "type": "error",
                        "code": "NOT_STARTED",
                        "message": "Stream must be initiated with a 'start' control frame before sending audio"
                    })
                    continue

                # Enforce per-connection buffer limits
                total_accumulated_bytes += len(chunk)
                if total_accumulated_bytes > settings.WS_MAX_BUFFER_BYTES:
                    await websocket.send_json({
                        "type": "error",
                        "code": "BUFFER_OVERFLOW",
                        "message": f"Connection buffer limit ({settings.WS_MAX_BUFFER_BYTES} bytes) exceeded."
                    })
                    segmenter.reset()
                    total_accumulated_bytes = 0
                    was_in_speech = False
                    continue

                # Process chunk through VAD segmenter
                completed_utterance = segmenter.process_chunk(chunk)

                # Emit VAD state transitions
                if segmenter.in_speech and not was_in_speech:
                    was_in_speech = True
                    await websocket.send_json({
                        "type": "vad",
                        "state": "speech_start"
                    })

                if completed_utterance is not None:
                    # Silence timeout reached: speech ended
                    if was_in_speech:
                        await websocket.send_json({
                            "type": "vad",
                            "state": "speech_end"
                        })
                        was_in_speech = False

                    total_accumulated_bytes = 0

                    # Run inference off the event loop
                    try:
                        speech_res = await speech_service.transcribe_pcm16_bytes(
                            pcm_bytes=completed_utterance,
                            sample_rate=sample_rate,
                            language_hint=language_hint
                        )
                        await websocket.send_json({
                            "type": "speech_result",
                            **speech_res.model_dump()
                        })
                        await cancel_active_llm()
                        active_llm_task = asyncio.create_task(
                            handle_llm_turn(
                                websocket=websocket,
                                transcript=speech_res.transcript,
                                emotion=speech_res.emotion,
                                language=speech_res.language,
                                conversation_history=conversation_history,
                            )
                        )
                    except Exception as e:
                        logger.error(f"Inference error on completed utterance: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "code": "INFERENCE_ERROR",
                            "message": str(e)
                        })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected cleanly.")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {e}")
    finally:
        # Clean up per-connection state and cancel in-flight LLM stream
        await cancel_active_llm()
        segmenter.reset()

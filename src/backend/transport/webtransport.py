import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable
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

logger = logging.getLogger("senseai.transport.webtransport")

class StreamTypes:
    STREAM_A_AUDIO = "stream_a_audio"          # Client -> Server: 16kHz PCM16 audio chunks
    STREAM_B_CONTROL = "stream_b_control"      # Bidirectional: JSON control messages
    STREAM_C_TRANSCRIPT = "stream_c_transcript"# Server -> Client: Text deltas & metadata
    STREAM_D_TTS = "stream_d_tts"              # Server -> Client: Binary WAV audio frames
    DATAGRAM = "datagram"                      # Bidirectional: Low-priority emotion & telemetry

class WebTransportSession:
    """
    Encapsulates a WebTransport (HTTP/3 over QUIC) session with multi-stream separation:
    - Stream A (Client -> Server): Continuous raw PCM 16kHz mono audio
    - Stream B (Bidirectional): Control commands (ping, pong, reset, end-of-utterance)
    - Stream C (Server -> Client): Real-time transcripts, sentence events, turn completion
    - Stream D (Server -> Client): Pipelined binary WAV audio chunks
    - Datagrams: Unreliable, low-overhead affective telemetry (valence, arousal, primary emotion)

    Enforces JWT authentication and session rate limits (Phase 11).
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        token: Optional[str] = None,
        pipeline: Optional[VoicePipeline] = None,
        on_stream_c_send: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_stream_d_send: Optional[Callable[[bytes], Awaitable[None]]] = None,
        on_datagram_send: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ):
        # 1. JWT Authentication Handshake Check
        if settings.REQUIRE_AUTH:
            if not token:
                raise AuthenticationError("WebTransport authentication required: token missing")
            claims = verify_access_token(token)
            self.session_id = claims.get("sub", session_id or f"wt_{uuid.uuid4().hex[:8]}")
        else:
            if token:
                try:
                    claims = verify_access_token(token)
                    self.session_id = claims.get("sub", session_id or f"wt_{uuid.uuid4().hex[:8]}")
                except Exception:
                    self.session_id = session_id or f"wt_{uuid.uuid4().hex[:8]}"
            else:
                self.session_id = session_id or f"wt_{uuid.uuid4().hex[:8]}"

        self.conversation_id = f"conv_{self.session_id}"
        self.pipeline = pipeline or VoicePipeline()
        self.is_active = True

        # Callback delegates for physical/mock transport writers
        self._on_stream_c_send = on_stream_c_send
        self._on_stream_d_send = on_stream_d_send
        self._on_datagram_send = on_datagram_send

        if not model_manager.initialized:
            model_manager.initialize()

        self.segmenter = VADSpeechSegmenter(
            vad=model_manager.vad,
            silence_timeout_ms=settings.SILENCE_TIMEOUT_MS,
            speech_threshold=settings.VAD_THRESHOLD
        )

        logger.info(f"WebTransportSession '{self.session_id}' created with conversation_id='{self.conversation_id}'.")

    async def handle_stream_a_audio(self, audio_chunk: bytes) -> Optional[Dict[str, Any]]:
        """
        Receives continuous raw PCM 16kHz mono chunks from Stream A.
        Feeds Silero VAD segmenter. Triggers pipeline when an utterance is complete.
        Enforces maximum utterance duration and utterances/minute rate limits.
        """
        if not self.is_active:
            return None

        # Check accumulated audio in segmenter
        if self.segmenter.in_speech:
            try:
                rate_limiter.validate_audio_chunk(len(self.segmenter.speech_buffer))
            except AudioDurationLimitExceeded as e:
                logger.warning(f"Audio duration cap exceeded in WebTransportSession '{self.session_id}': {e}")
                self.segmenter.reset()
                await self.send_transcript_event({
                    "type": "error",
                    "error_code": "AUDIO_DURATION_LIMIT_EXCEEDED",
                    "message": str(e),
                    "session_id": self.session_id,
                    "conversation_id": self.conversation_id
                })
                return {"status": "error", "reason": "duration_limit_exceeded"}

        completed_utterance = self.segmenter.process_chunk(audio_chunk)
        if completed_utterance:
            try:
                rate_limiter.record_utterance(self.session_id)
            except UtteranceRateLimitExceeded as e:
                logger.warning(f"Utterance rate limit exceeded in WebTransportSession '{self.session_id}': {e}")
                await self.send_transcript_event({
                    "type": "error",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": str(e),
                    "session_id": self.session_id,
                    "conversation_id": self.conversation_id
                })
                return {"status": "error", "reason": "rate_limit_exceeded"}

            await self._process_utterance(completed_utterance)
            return {"status": "dispatched", "length": len(completed_utterance)}
        return {"status": "buffering"}

    async def handle_stream_b_control(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles bidirectional control frame from Stream B.
        Supports: 'ping', 'reset', 'end-of-utterance'.
        """
        action = command_data.get("action") or command_data.get("type")

        if action == "ping":
            return {"type": "pong", "session_id": self.session_id, "conversation_id": self.conversation_id}

        elif action == "reset":
            self.segmenter.reset()
            return {"type": "status", "message": "VAD segmenter reset."}

        elif action in ("end-of-utterance", "end_of_utterance"):
            manual_utterance = self.segmenter.flush()
            if manual_utterance:
                await self._process_utterance(manual_utterance)
                return {"type": "status", "message": "Flushed and processing."}
            else:
                return {
                    "type": "warning",
                    "message": "Empty audio buffer: no speech detected before end_of_utterance."
                }

        return {"type": "error", "message": f"Unknown control action: {action}"}

    async def handle_datagram(self, datagram_payload: bytes) -> Optional[Dict[str, Any]]:
        """
        Handles incoming datagram frame (e.g. client heartbeats, client-side volume metrics).
        """
        try:
            data = json.loads(datagram_payload.decode("utf-8"))
            logger.debug(f"[WebTransport Datagram In] {data}")
            return {"status": "received", "data": data}
        except Exception as e:
            logger.warning(f"Failed to parse datagram: {e}")
            return None

    async def send_transcript_event(self, payload: Dict[str, Any]):
        """
        Pushes transcript / metadata event over Stream C.
        """
        if self._on_stream_c_send:
            await self._on_stream_c_send(payload)

    async def send_tts_audio_frame(self, audio_bytes: bytes):
        """
        Pushes binary WAV audio chunk over Stream D.
        """
        if self._on_stream_d_send:
            await self._on_stream_d_send(audio_bytes)

    async def send_emotion_datagram(self, emotion: Dict[str, Any], latencies: Optional[Dict[str, Any]] = None):
        """
        Pushes low-overhead emotion & latency telemetry over unreliable Datagram channel.
        """
        payload = {
            "type": "emotion_update",
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "emotion": emotion,
            "latencies": latencies or {}
        }
        if self._on_datagram_send:
            await self._on_datagram_send(payload)

    async def _process_utterance(self, audio_bytes: bytes):
        """
        Executes streaming voice pipeline and routes events to dedicated streams:
        - Transcript, sentence text, completions -> Stream C
        - Binary WAV frames -> Stream D
        - Emotion updates -> Datagrams
        """
        duration_sec = len(audio_bytes) / 32000.0
        logger.info(f"[WebTransport] Processing utterance of {duration_sec:.2f}s ({len(audio_bytes)} bytes)...")

        # Notify Stream C of processing status
        await self.send_transcript_event({
            "type": "status",
            "stage": "processing",
            "conversation_id": self.conversation_id
        })

        async for event_type, payload in self.pipeline.stream_utterance(
            audio_bytes, conversation_id=self.conversation_id
        ):
            if event_type == "metadata":
                # Stream C: LLM start + initial transcript
                await self.send_transcript_event({
                    "type": "llm_start",
                    "conversation_id": self.conversation_id,
                    "transcript": payload.get("transcript"),
                    "context": payload.get("context"),
                    "intent": payload.get("intent"),
                    "emotion": payload.get("emotion")
                })
                # Datagram: Fast path emotion telemetry
                if payload.get("emotion"):
                    await self.send_emotion_datagram(payload["emotion"])

            elif event_type == "sentence":
                chunk_idx = payload.get("index", 0)
                sentence_text = payload.get("text", "")
                wav_chunk = payload.get("audio_bytes")
                chunk_latencies = payload.get("latencies", {})

                # 1. Stream C: sentence announcement
                await self.send_transcript_event({
                    "type": "sentence_start",
                    "conversation_id": self.conversation_id,
                    "index": chunk_idx,
                    "text": sentence_text,
                    "latencies": chunk_latencies
                })

                # 2. Stream D: binary audio frame
                if wav_chunk:
                    await self.send_tts_audio_frame(wav_chunk)

                # 3. Stream C: sentence completion marker
                await self.send_transcript_event({
                    "type": "sentence_end",
                    "conversation_id": self.conversation_id,
                    "index": chunk_idx
                })

            elif event_type == "complete":
                # Stream C: Final turn completion
                await self.send_transcript_event({
                    "type": "turn_complete",
                    "conversation_id": self.conversation_id,
                    "transcript": payload.get("transcript"),
                    "response_text": payload.get("response_text"),
                    "latencies": payload.get("latencies"),
                    "context": payload.get("context"),
                    "intent": payload.get("intent"),
                    "emotion": payload.get("emotion")
                })

                # Datagram: Final latency & emotion telemetry
                if payload.get("emotion"):
                    await self.send_emotion_datagram(payload["emotion"], payload.get("latencies"))

    def close(self):
        self.is_active = False
        self.segmenter.reset()
        logger.info(f"WebTransportSession '{self.session_id}' closed.")


class WebTransportManager:
    """
    Manages active WebTransport sessions and provides stream demuxing.
    """
    def __init__(self):
        self.sessions: Dict[str, WebTransportSession] = {}

    def create_session(
        self,
        session_id: Optional[str] = None,
        token: Optional[str] = None,
        pipeline: Optional[VoicePipeline] = None,
        on_stream_c_send: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_stream_d_send: Optional[Callable[[bytes], Awaitable[None]]] = None,
        on_datagram_send: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> WebTransportSession:
        session = WebTransportSession(
            session_id=session_id,
            token=token,
            pipeline=pipeline,
            on_stream_c_send=on_stream_c_send,
            on_stream_d_send=on_stream_d_send,
            on_datagram_send=on_datagram_send,
        )
        self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[WebTransportSession]:
        return self.sessions.get(session_id)

    def remove_session(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if session:
            session.close()

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "webtransport": True,
            "websocket": True,
            "protocols": ["webtransport", "websocket"],
            "streams": {
                "stream_a": "mic_audio_pcm16_mono_16khz (client -> server)",
                "stream_b": "control_json (bidirectional)",
                "stream_c": "transcript_json (server -> client)",
                "stream_d": "tts_audio_wav (server -> client)"
            },
            "datagrams": {
                "supported": True,
                "purpose": "low_priority_emotion_and_telemetry"
            },
            "quic_version": "v1 (RFC 9000)",
            "http3_version": "RFC 9114"
        }

# Global singleton manager
webtransport_manager = WebTransportManager()

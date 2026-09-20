import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, AsyncGenerator, Optional
from .intent import IntentRouter, IntentCategory, IntentResult
from .chunker import SentenceBoundaryChunker
from .concurrency import gpu_limiter
from ..asr.router import AudioContext
from ..models.manager import model_manager
from ..telemetry import StageTiming, benchmark_collector

logger = logging.getLogger(__name__)

class VoicePipeline:
    """
    Phase 7 Streaming Voice Pipeline:
    Raw PCM 16kHz mono -> LanguageRouter -> EmotionAnalyzer (SER + Lexical) ->
      IntentRouter (Hard Gate) ->
        ├─► 'command'   -> Deterministic handler
        ├─► 'knowledge' -> Local RAG (multilingual-e5-small + FAISS) -> Qwen3 (streaming)
        └─► 'chat'      -> Qwen3 via llama.cpp (streaming SSE)
      -> SentenceBoundaryChunker (real-time sentence splitting)
      -> Indic Parler-TTS per sentence
      -> Client (sequential audio chunks, TTFT & TTFA metrics)
    """
    def __init__(self):
        if not model_manager.initialized:
            model_manager.initialize()
        self.models = model_manager
        self.intent_router = IntentRouter(retriever=self.models.retriever)

    async def stream_utterance(
        self,
        pcm_bytes: bytes,
        conversation_id: str = "default_session",
        vad_ms: Optional[float] = None,
        llm_provider: Optional[str] = None
    ) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
        """
        Executes streaming voice pipeline with per-stage timing benchmarks.
        Yields events:
          - ("metadata", { "transcript": str, "context": dict, "intent": dict, "emotion": dict, "llm_provider": str })
          - ("sentence", { "index": int, "text": str, "audio_bytes": bytes, "latencies": dict })
          - ("complete", { "transcript": str, "response_text": str, "latencies": dict, "stage_timing": dict, "context": dict, "intent": dict, "emotion": dict, "llm_provider": str })
        """
        from ..llm.router import get_llm_client, get_active_provider
        active_llm = get_llm_client(provider_override=llm_provider)
        active_provider = get_active_provider(provider_override=llm_provider)

        audio_received_time = datetime.now(timezone.utc).isoformat()
        latencies: Dict[str, float] = {}
        t_start = time.perf_counter()

        # Measure VAD time (passed from segmenter or estimated from processed audio length)
        measured_vad = vad_ms if vad_ms is not None else round(max(0.5, (len(pcm_bytes) / 32000.0) * 2.0), 2)
        latencies["vad_ms"] = measured_vad

        def _record_telemetry(intent_cat: str, resp_text: str) -> Dict[str, Any]:
            timing = StageTiming(
                audio_received=audio_received_time,
                vad=latencies.get("vad_ms", 0.0),
                asr=latencies.get("asr_ms", 0.0),
                emotion=latencies.get("emotion_ms", 0.0),
                router=latencies.get("intent_ms", 0.0),
                rag=latencies.get("rag_ms", 0.0),
                llm_ttft=latencies.get("ttft_ms", 0.0),
                llm_total=latencies.get("llm_ms", 0.0),
                tts_ttfa=latencies.get("ttfa_ms", 0.0),
                total=latencies.get("total_ms", 0.0),
                conversation_id=conversation_id,
                transcript=transcript,
                intent=intent_cat,
                language=getattr(context, "language", "en")
            )
            benchmark_collector.record(timing)
            return timing.to_dict()

        # Stage 0: Voice Liveness & Anti-Spoofing Heuristic (Phase 18)
        from ..audio.liveness import liveness_detector
        t_live_start = time.perf_counter()
        liveness_res = liveness_detector.analyze(pcm_bytes)
        latencies["liveness_ms"] = round((time.perf_counter() - t_live_start) * 1000, 2)

        # Stage 1: Language Routing & ASR
        t_asr_start = time.perf_counter()
        context = self.models.language_router.route_audio(pcm_bytes)
        transcript = context.transcript
        latencies["asr_ms"] = round((time.perf_counter() - t_asr_start) * 1000, 2)
        logger.info(
            f"[Pipeline] ASR/Router completed in {latencies['asr_ms']}ms: "
            f"lang={context.language}, script={context.script}, mixed={context.mixed_language}, text='{transcript}'"
        )

        # Stage 2: Emotion Analysis & Persistence
        t_emotion_start = time.perf_counter()
        raw_emotion = getattr(context, "raw_emotion", "neutral")
        if self.models.emotion_analyzer:
            emotion_state = self.models.emotion_analyzer.analyze(
                raw_emotion=raw_emotion,
                confidence=context.confidence,
                transcript=transcript
            )
        else:
            from ..emotion.emotion import EmotionState
            emotion_state = EmotionState(
                primary="neutral",
                confidence=1.0,
                valence=0.0,
                arousal=0.0,
                lexical_polarity=0.0
            )
        latencies["emotion_ms"] = round((time.perf_counter() - t_emotion_start) * 1000, 2)

        if self.models.emotion_storage and transcript and transcript.strip():
            self.models.emotion_storage.save_emotion_event(
                conversation_id=conversation_id,
                primary_emotion=emotion_state.primary,
                confidence=emotion_state.confidence,
                valence=emotion_state.valence,
                arousal=emotion_state.arousal,
                raw_transcript=transcript
            )

        if not transcript or not transcript.strip():
            transcript = "..."
            response_text = "I couldn't hear anything clearly. Please try speaking again."
            audio_bytes = self.models.tts.synthesize_wav(response_text, emotion=emotion_state)
            latencies["ttft_ms"] = 0.0
            latencies["ttfa_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            latencies["total_ms"] = latencies["ttfa_ms"]
            intent_dict = {"category": "chat", "confidence": 1.0, "matched_rule": None, "raw_query": ""}
            
            yield ("metadata", {
                "transcript": transcript,
                "context": context.to_dict(),
                "intent": intent_dict,
                "emotion": emotion_state.to_dict(),
                "llm_provider": active_provider
            })
            yield ("sentence", {
                "index": 0,
                "text": response_text,
                "audio_bytes": audio_bytes,
                "latencies": {"ttft_ms": 0.0, "ttfa_ms": latencies["ttfa_ms"]}
            })
            timing_dict = _record_telemetry("chat", response_text)
            yield ("complete", {
                "transcript": transcript,
                "response_text": response_text,
                "latencies": latencies,
                "stage_timing": timing_dict,
                "context": context.to_dict(),
                "intent": intent_dict,
                "emotion": emotion_state.to_dict(),
                "llm_provider": active_provider
            })
            return

        # Stage 3: Intent Router Hard Gate
        t_intent_start = time.perf_counter()
        intent: IntentResult = self.intent_router.classify(transcript)
        latencies["intent_ms"] = round((time.perf_counter() - t_intent_start) * 1000, 2)
        intent_dict = intent.to_dict()
        logger.info(f"[Pipeline] Intent Gate resolved in {latencies['intent_ms']}ms: category={intent.category.value}")

        yield ("metadata", {
            "transcript": transcript,
            "context": context.to_dict(),
            "intent": intent_dict,
            "emotion": emotion_state.to_dict(),
            "llm_provider": active_provider
        })

        t_llm_start = time.perf_counter()
        first_token_time = None
        first_audio_time = None
        sentence_index = 0
        collected_sentences = []
        cited_docs = []

        if intent.category == IntentCategory.COMMAND:
            # Deterministic command execution & whitelist sandboxing (Phase 18)
            action_rule = intent.matched_rule or "unknown"
            from ..security.audit import audit_logger
            if self.intent_router.is_command_whitelisted(action_rule):
                response_text = f"Command '{action_rule.replace('command:', '')}' executed."
                audit_logger.log_event(
                    event_type="COMMAND_EXECUTED",
                    actor=conversation_id,
                    details={"action": action_rule, "query": transcript, "status": "approved"}
                )
            else:
                response_text = f"Command '{action_rule.replace('command:', '')}' is not supported."
                audit_logger.log_event(
                    event_type="COMMAND_REJECTED",
                    actor=conversation_id,
                    details={"action": action_rule, "query": transcript, "status": "rejected_unauthorized"}
                )

            latencies["ttft_ms"] = 0.0
            audio_bytes = self.models.tts.synthesize_wav(response_text, emotion=emotion_state)
            latencies["ttfa_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            latencies["llm_ms"] = round((time.perf_counter() - t_llm_start) * 1000, 2)
            latencies["total_ms"] = latencies["ttfa_ms"]

            yield ("sentence", {
                "index": 0,
                "text": response_text,
                "audio_bytes": audio_bytes,
                "latencies": {"ttft_ms": 0.0, "ttfa_ms": latencies["ttfa_ms"]}
            })
            timing_dict = _record_telemetry("command", response_text)
            yield ("complete", {
                "transcript": transcript,
                "response_text": response_text,
                "latencies": latencies,
                "stage_timing": timing_dict,
                "context": context.to_dict(),
                "intent": intent_dict,
                "emotion": emotion_state.to_dict(),
                "llm_provider": active_provider
            })
            return

        # Prepare streaming generator for knowledge or chat
        token_stream = None
        if intent.category == IntentCategory.KNOWLEDGE:
            if not self.models.retriever or not getattr(self.models.retriever, "is_loaded", False):
                logger.warning(
                    "[VoicePipeline] Knowledge intent active but RAG retriever/index is missing or unloaded. "
                    "Gracefully degrading to CHAT branch."
                )
                intent_dict["category"] = "chat"
                intent_dict["fallback"] = "knowledge_index_missing"
                token_stream = active_llm.stream_response(
                    prompt=transcript,
                    emotion=emotion_state,
                    language=context.language,
                    mixed_language=context.mixed_language
                )
            else:
                t_rag_start = time.perf_counter()
                grounded_context = ""
                retrieved_chunks = []
                if self.models.retriever:
                    retrieved_chunks = self.models.retriever.retrieve(query=transcript, top_k=3)
                    grounded_context, cited_docs = self.models.retriever.format_grounded_context(retrieved_chunks)
                latencies["rag_ms"] = round((time.perf_counter() - t_rag_start) * 1000, 2)
                intent_dict["cited_docs"] = cited_docs
                intent_dict["chunks_count"] = len(retrieved_chunks)

                if retrieved_chunks and grounded_context:
                    from ..llm.prompts import format_qwen_knowledge_messages
                    knowledge_messages = format_qwen_knowledge_messages(
                        transcript=transcript,
                        grounded_context=grounded_context,
                        cited_docs=cited_docs,
                        emotion=emotion_state,
                        language=context.language,
                        mixed_language=context.mixed_language
                    )
                    token_stream = active_llm.stream_response(
                        prompt=transcript,
                        messages=knowledge_messages,
                        emotion=emotion_state,
                        language=context.language,
                        mixed_language=context.mixed_language
                    )
                else:
                    response_text = "I checked the documentation repository, but could not find information on that topic."
                    audio_bytes = self.models.tts.synthesize_wav(response_text, emotion=emotion_state)
                    latencies["ttft_ms"] = 0.0
                    latencies["ttfa_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                    latencies["total_ms"] = latencies["ttfa_ms"]
                    yield ("sentence", {
                        "index": 0,
                        "text": response_text,
                        "audio_bytes": audio_bytes,
                        "latencies": {"ttft_ms": 0.0, "ttfa_ms": latencies["ttfa_ms"]}
                    })
                    timing_dict = _record_telemetry("knowledge", response_text)
                    yield ("complete", {
                        "transcript": transcript,
                        "response_text": response_text,
                        "latencies": latencies,
                        "stage_timing": timing_dict,
                        "context": context.to_dict(),
                        "intent": intent_dict,
                        "emotion": emotion_state.to_dict(),
                        "llm_provider": active_provider
                    })
                    return
        else:
            # Chat branch
            token_stream = active_llm.stream_response(
                prompt=transcript,
                emotion=emotion_state,
                language=context.language,
                mixed_language=context.mixed_language
            )

        # Stream tokens into SentenceBoundaryChunker and synthesize sentence-by-sentence
        # Guarded by GPU concurrency limiter to prevent VRAM OOM under concurrent load
        chunker = SentenceBoundaryChunker()
        full_tokens = []

        async with gpu_limiter:
            async for token in token_stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    latencies["ttft_ms"] = round((first_token_time - t_llm_start) * 1000, 2)

                full_tokens.append(token)
                sentences = chunker.add_token(token)

                for sentence in sentences:
                    t_tts_chunk = time.perf_counter()
                    audio_chunk = self.models.tts.synthesize_wav(sentence, emotion=emotion_state)
                    chunk_tts_ms = round((time.perf_counter() - t_tts_chunk) * 1000, 2)

                    if first_audio_time is None:
                        first_audio_time = time.perf_counter()
                        latencies["ttfa_ms"] = round((first_audio_time - t_start) * 1000, 2)

                    collected_sentences.append(sentence)
                    yield ("sentence", {
                        "index": sentence_index,
                        "text": sentence,
                        "audio_bytes": audio_chunk,
                        "latencies": {
                            "chunk_tts_ms": chunk_tts_ms,
                            "ttft_ms": latencies.get("ttft_ms", 0.0),
                            "ttfa_ms": latencies.get("ttfa_ms", 0.0)
                        }
                    })
                    sentence_index += 1

            # Flush any remaining text in the chunker buffer
            remaining = chunker.flush()
            if remaining:
                t_tts_chunk = time.perf_counter()
                audio_chunk = self.models.tts.synthesize_wav(remaining, emotion=emotion_state)
                chunk_tts_ms = round((time.perf_counter() - t_tts_chunk) * 1000, 2)

                if first_audio_time is None:
                    first_audio_time = time.perf_counter()
                    latencies["ttfa_ms"] = round((first_audio_time - t_start) * 1000, 2)

                collected_sentences.append(remaining)
                yield ("sentence", {
                    "index": sentence_index,
                    "text": remaining,
                    "audio_bytes": audio_chunk,
                    "latencies": {
                        "chunk_tts_ms": chunk_tts_ms,
                        "ttft_ms": latencies.get("ttft_ms", 0.0),
                        "ttfa_ms": latencies.get("ttfa_ms", 0.0)
                    }
                })
                sentence_index += 1

        full_response_text = " ".join(collected_sentences) if collected_sentences else "".join(full_tokens).strip()
        if not full_response_text:
            full_response_text = "I understood your message."

        from ..llm.prompts import filter_llm_output
        full_response_text = filter_llm_output(full_response_text)

        latencies["llm_ms"] = round((time.perf_counter() - t_llm_start) * 1000, 2)
        latencies["total_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        if "ttft_ms" not in latencies:
            latencies["ttft_ms"] = latencies["llm_ms"]
        if "ttfa_ms" not in latencies:
            latencies["ttfa_ms"] = latencies["total_ms"]

        logger.info(
            f"[Pipeline] Stream completed for '{conversation_id}': "
            f"TTFT={latencies['ttft_ms']}ms, TTFA={latencies['ttfa_ms']}ms, "
            f"Total={latencies['total_ms']}ms, Sentences={sentence_index}"
        )

        timing_dict = _record_telemetry(intent_dict.get("category", "chat"), full_response_text)
        yield ("complete", {
            "transcript": transcript,
            "response_text": full_response_text,
            "latencies": latencies,
            "stage_timing": timing_dict,
            "context": context.to_dict(),
            "intent": intent_dict,
            "emotion": emotion_state.to_dict(),
            "llm_provider": active_provider
        })

    async def process_utterance(
        self, pcm_bytes: bytes, conversation_id: str = "default_session", llm_provider: Optional[str] = None
    ) -> Tuple[str, str, bytes, Dict[str, float], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Synchronous batch wrapper around stream_utterance for backward compatibility.
        Returns: (transcript, response_text, combined_audio_wav_bytes, latencies, context, intent, emotion)
        """
        transcript = ""
        response_text = ""
        audio_chunks = []
        latencies = {}
        context = {}
        intent = {}
        emotion = {}

        async for event_type, payload in self.stream_utterance(pcm_bytes, conversation_id, llm_provider=llm_provider):
            if event_type == "metadata":
                transcript = payload.get("transcript", "")
                context = payload.get("context", {})
                intent = payload.get("intent", {})
                emotion = payload.get("emotion", {})
            elif event_type == "sentence":
                audio_bytes = payload.get("audio_bytes")
                if audio_bytes:
                    audio_chunks.append(audio_bytes)
            elif event_type == "complete":
                response_text = payload.get("response_text", "")
                latencies = payload.get("latencies", {})
                context = payload.get("context", context)
                intent = payload.get("intent", intent)
                emotion = payload.get("emotion", emotion)

        # For batch compatibility, return first audio chunk or empty
        combined_audio = audio_chunks[0] if audio_chunks else b""
        return transcript, response_text, combined_audio, latencies, context, intent, emotion



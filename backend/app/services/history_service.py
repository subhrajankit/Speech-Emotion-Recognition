"""
History & Persistence Service for VoiceSense AI.
Handles non-blocking, asynchronous recording of voice turns, transcripts,
emotion results, and model versions off the event loop.

Guarantees:
1. Zero raw audio persistence invariant: raw audio chunks are NEVER stored.
2. Privacy policy compliance: if STORE_TRANSCRIPTS=False, transcript text is redacted.
3. Fault isolation: database errors are logged and swallowed; the speech path never breaks.
4. Anonymous isolation: if user_id is None, persistence is completely bypassed.
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db_session
from backend.app.models.session import Session as DBSession
from backend.app.models.model_version import ModelVersion
from backend.app.models.prediction import Prediction
from backend.app.models.transcript import Transcript
from backend.app.models.emotion import EmotionResult
from backend.app.models.message import Message

logger = logging.getLogger("voicesense.history")


class HistoryService:
    """Manages conversational session history and turn persistence."""

    def __init__(self):
        self._model_version_cache: Dict[str, str] = {}

    def get_or_create_model_version(
        self,
        db: Session,
        engine_name: str,
        model_id: str,
        pinned_revision: Optional[str] = None,
        decoder_type: Optional[str] = None,
    ) -> str:
        """
        Retrieves existing model_versions ID or inserts a new row.
        Cached in-memory to prevent redundant queries.
        """
        cache_key = f"{engine_name}:{model_id}:{pinned_revision}:{decoder_type}"
        if cache_key in self._model_version_cache:
            cached_id = self._model_version_cache[cache_key]
            # Ensure cached model_version exists in this DB session (handles multi-database environments & test isolation)
            if db.query(ModelVersion).filter(ModelVersion.id == cached_id).first():
                return cached_id

        mv = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.engine_name == engine_name,
                ModelVersion.model_id == model_id,
                ModelVersion.pinned_revision == pinned_revision,
                ModelVersion.decoder_type == decoder_type,
            )
            .first()
        )

        if not mv:
            mv = ModelVersion(
                id=str(uuid.uuid4()),
                engine_name=engine_name,
                model_id=model_id,
                pinned_revision=pinned_revision,
                decoder_type=decoder_type,
            )
            db.add(mv)
            db.flush()

        self._model_version_cache[cache_key] = mv.id
        return mv.id

    def persist_turn_sync(
        self,
        session_id: str,
        user_id: Optional[str],
        speech_result_data: Dict[str, Any],
        llm_response_text: Optional[str] = None,
        rag_sources: Optional[List[Dict[str, Any]]] = None,
        audio_duration_ms: Optional[float] = None,
    ) -> Optional[str]:
        """
        Synchronous persistence worker executed in a threadpool worker.
        """
        # Anonymous users: do not persist anything
        if not user_id:
            logger.debug(f"[HistoryService] Skipping persistence for anonymous session {session_id}")
            return None

        with get_db_session() as db:
            # 1. Ensure Session exists and belongs to user_id
            db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
            now = datetime.now(timezone.utc)
            lang = speech_result_data.get("language")

            # Ownership guard: never append turns to a session owned by a
            # different user. session.user_id is immutable after creation, so
            # this check inside the same transaction is race-safe.
            if db_session and db_session.user_id != user_id:
                logger.warning(
                    f"[HistoryService] Rejecting persistence for session {session_id}: "
                    "session is owned by a different user."
                )
                return None

            if not db_session:
                db_session = DBSession(
                    id=session_id,
                    user_id=user_id,
                    primary_language=lang,
                    created_at=now,
                    updated_at=now,
                )
                db.add(db_session)
                db.flush()
            else:
                db_session.updated_at = now
                if lang and not db_session.primary_language:
                    db_session.primary_language = lang

            # 2. Resolve ModelVersion
            raw_model_str = speech_result_data.get("model_version", "sensevoice")
            engine_name = "sensevoice" if "sensevoice" in raw_model_str.lower() else "indicconformer"
            model_id = (
                settings.SENSEVOICE_MODEL_DIR
                if engine_name == "sensevoice"
                else settings.INDICCONFORMER_MODEL_DIR
            )
            pinned_rev = (
                settings.INDICCONFORMER_REVISION
                if engine_name == "indicconformer"
                else None
            )
            decoder = (
                settings.INDICCONFORMER_DECODER_TYPE
                if engine_name == "indicconformer"
                else "funasr"
            )

            model_version_id = self.get_or_create_model_version(
                db=db,
                engine_name=engine_name,
                model_id=model_id,
                pinned_revision=pinned_rev,
                decoder_type=decoder,
            )

            # 3. Create Prediction row
            proc_time = speech_result_data.get("processing_time_ms")
            conf = speech_result_data.get("confidence")
            pred = Prediction(
                id=str(uuid.uuid4()),
                session_id=session_id,
                model_version_id=model_version_id,
                audio_duration_ms=audio_duration_ms,
                processing_time_ms=proc_time,
                confidence=conf,
                created_at=now,
            )
            db.add(pred)
            db.flush()

            # 4. Create Transcript row (Respect STORE_TRANSCRIPTS privacy setting)
            raw_text = speech_result_data.get("transcript", "")
            stored_text = raw_text if settings.STORE_TRANSCRIPTS else "[REDACTED_BY_POLICY]"
            transcript = Transcript(
                id=str(uuid.uuid4()),
                prediction_id=pred.id,
                session_id=session_id,
                text=stored_text,
                language=speech_result_data.get("language", "unknown"),
                script=speech_result_data.get("script"),
                mixed_language=speech_result_data.get("mixed_language"),
                audio_events=speech_result_data.get("audio_events"),
                created_at=now,
            )
            db.add(transcript)

            # 5. Create EmotionResult row only when a real emotion label exists.
            # confidence/valence/arousal stay NULL until genuine model scores are
            # available — never fabricate constants or lookup-table approximations.
            primary_emo = speech_result_data.get("emotion")
            if primary_emo:
                raw_tags = (speech_result_data.get("debug") or {}).get("raw_tags") or (speech_result_data.get("debug") or {}).get("emotion_raw_label")
                conf_val = speech_result_data.get("confidence")
                emotion = EmotionResult(
                    id=str(uuid.uuid4()),
                    prediction_id=pred.id,
                    session_id=session_id,
                    primary_emotion=primary_emo,
                    confidence=conf_val if isinstance(conf_val, (int, float)) else None,
                    valence=None,
                    arousal=None,
                    raw_tags=raw_tags,
                    created_at=now,
                )
                db.add(emotion)

            # 6. Create Message rows (user utterance & assistant response)
            if stored_text:
                user_msg = Message(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    prediction_id=pred.id,
                    role="user",
                    text=stored_text,
                    sources=None,
                    created_at=now,
                )
                db.add(user_msg)

            if llm_response_text:
                assistant_msg = Message(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    prediction_id=pred.id,
                    role="assistant",
                    text=llm_response_text,
                    sources=rag_sources,
                    created_at=now,
                )
                db.add(assistant_msg)

            db.commit()
            logger.info(f"[HistoryService] Successfully persisted turn for session {session_id} (prediction {pred.id})")
            return pred.id

    async def record_voice_turn(
        self,
        session_id: str,
        user_id: Optional[str],
        speech_result_data: Dict[str, Any],
        llm_response_text: Optional[str] = None,
        rag_sources: Optional[List[Dict[str, Any]]] = None,
        audio_duration_ms: Optional[float] = None,
    ):
        """
        Non-blocking async persistence dispatcher.
        Executes sync persistence off the event loop and swallows any failure.
        """
        if not user_id:
            return

        try:
            await asyncio.to_thread(
                self.persist_turn_sync,
                session_id=session_id,
                user_id=user_id,
                speech_result_data=speech_result_data,
                llm_response_text=llm_response_text,
                rag_sources=rag_sources,
                audio_duration_ms=audio_duration_ms,
            )
        except Exception as e:
            # Fault isolation guarantee: DB downtime must NEVER break speech turns
            logger.error(f"[HistoryService] Persistence failed for session {session_id}: {e}", exc_info=True)


history_service = HistoryService()

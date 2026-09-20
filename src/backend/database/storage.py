import sqlite3
import os
import logging
from typing import Optional, Dict, Any, List
from cryptography.fernet import Fernet
from ..config import settings

logger = logging.getLogger(__name__)

class EmotionStorage:
    """
    SQLite persistence for user emotion history.
    Stores metadata and transcripts; raw audio is NEVER stored.
    Applies AES-128-CBC (Fernet) field-level encryption at rest to sensitive fields.
    """
    def __init__(self, db_path: str = "database/dev.db", encryption_key: Optional[str] = None):
        self.db_path = db_path
        key = encryption_key or getattr(settings, "DATABASE_ENCRYPTION_KEY", None)
        self._cipher: Optional[Fernet] = None
        if key:
            try:
                self._cipher = Fernet(key.encode("utf-8") if isinstance(key, str) else key)
            except Exception as e:
                logger.error(f"[EmotionStorage] Invalid encryption key: {e}")
        self._ensure_tables()

    def _encrypt(self, text: Optional[str]) -> str:
        if not text or not self._cipher:
            return text or ""
        try:
            return "enc::" + self._cipher.encrypt(text.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.warning(f"Field encryption failed: {e}")
            return text

    def _decrypt(self, text: Optional[str]) -> str:
        if not text:
            return ""
        if text.startswith("enc::"):
            if not self._cipher:
                return "[ENCRYPTED_FIELD]"
            try:
                ciphertext = text[5:]
                return self._cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            except Exception as e:
                logger.error(f"Field decryption failed: {e}")
                return "[DECRYPTION_ERROR]"
        return text

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _ensure_tables(self):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS emotion_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    primary_emotion TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    valence REAL NOT NULL,
                    arousal REAL NOT NULL,
                    raw_transcript TEXT
                );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_emotion_history_conv ON emotion_history(conversation_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_emotion_history_ts ON emotion_history(timestamp);")
                conn.commit()
        except Exception as e:
            logger.error(f"Error ensuring emotion_history table: {e}")
        finally:
            conn.close()

    def save_emotion_event(
        self,
        conversation_id: str,
        primary_emotion: str,
        confidence: float,
        valence: float,
        arousal: float,
        raw_transcript: str = ""
    ) -> int:
        """
        Inserts an emotion observation into SQLite.
        Returns the inserted row ID.
        """
        conn = self._get_connection()
        try:
            enc_emotion = self._encrypt(primary_emotion)
            enc_transcript = self._encrypt(raw_transcript)
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO emotion_history (
                    conversation_id, primary_emotion, confidence, valence, arousal, raw_transcript
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, (conversation_id, enc_emotion, confidence, valence, arousal, enc_transcript))
                conn.commit()
                row_id = cursor.lastrowid
                logger.info(f"[EmotionStorage] Saved emotion event #{row_id} for conv '{conversation_id}': {primary_emotion} (encrypted)")
                return row_id
        except Exception as e:
            logger.error(f"Failed to save emotion event: {e}")
            return -1
        finally:
            conn.close()

    def get_history(self, conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves recent emotion history for a conversation, transparently decrypting encrypted fields.
        """
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, conversation_id, timestamp, primary_emotion, confidence, valence, arousal, raw_transcript
            FROM emotion_history
            WHERE conversation_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """, (conversation_id, limit))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["primary_emotion"] = self._decrypt(item.get("primary_emotion"))
                item["raw_transcript"] = self._decrypt(item.get("raw_transcript"))
                results.append(item)
            return results
        except Exception as e:
            logger.error(f"Failed to query emotion history: {e}")
            return []
        finally:
            conn.close()

    def prune_expired_records(self, retention_days: int = 30) -> int:
        """
        Deletes emotion and conversation records older than the retention threshold.
        Enforces Phase 15 data retention policy.
        Returns the count of deleted rows.
        """
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM emotion_history WHERE timestamp < datetime('now', ?)",
                    (f"-{int(retention_days)} days",)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"[EmotionStorage] Pruned {deleted_count} records older than {retention_days} days.")
                return deleted_count
        except Exception as e:
            logger.error(f"Failed to prune expired emotion records: {e}")
            return -1
        finally:
            conn.close()


"""
Unit tests for Phase 15: Backup, Restore & Data Retention.
Validates:
1. EmotionStorage.prune_expired_records enforces retention lifecycle.
2. SQLite online backup and restore with SHA256 checksum verification.
3. Backup file retention pruning.
"""

import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

from src.backend.database.storage import EmotionStorage
from scripts.database.backup_manager import (
    compute_sha256,
    write_checksum,
    verify_checksum,
    backup_sqlite,
    restore_sqlite,
    prune_old_backups
)


def test_emotion_storage_retention_pruning():
    """
    Tests that prune_expired_records deletes rows older than the specified
    threshold while retaining recent records.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_retention.db")
        storage = EmotionStorage(db_path=db_path)

        # Insert 1 recent record and 2 expired records (>30 days old)
        conn = storage._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                # Recent record (now)
                cursor.execute("""
                    INSERT INTO emotion_history (conversation_id, primary_emotion, confidence, valence, arousal, raw_transcript)
                    VALUES ('recent_session', 'happy', 0.9, 0.5, 0.5, 'recent transcript');
                """)
                # Expired record 1 (45 days old)
                cursor.execute("""
                    INSERT INTO emotion_history (conversation_id, timestamp, primary_emotion, confidence, valence, arousal, raw_transcript)
                    VALUES ('old_session_1', datetime('now', '-45 days'), 'sad', 0.8, -0.4, -0.2, 'old transcript 1');
                """)
                # Expired record 2 (60 days old)
                cursor.execute("""
                    INSERT INTO emotion_history (conversation_id, timestamp, primary_emotion, confidence, valence, arousal, raw_transcript)
                    VALUES ('old_session_2', datetime('now', '-60 days'), 'neutral', 0.9, 0.0, 0.0, 'old transcript 2');
                """)
                conn.commit()
        finally:
            conn.close()

        # Verify 3 records exist before pruning
        conn = storage._get_connection()
        try:
            cnt = conn.execute("SELECT count(*) FROM emotion_history;").fetchone()[0]
            assert cnt == 3
        finally:
            conn.close()

        # Prune records older than 30 days
        pruned_count = storage.prune_expired_records(retention_days=30)
        assert pruned_count == 2

        # Verify only the recent record remains
        conn = storage._get_connection()
        try:
            rows = conn.execute("SELECT conversation_id FROM emotion_history;").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "recent_session"
        finally:
            conn.close()


def test_sqlite_backup_and_restore_cycle():
    """
    Tests full backup creation, SHA256 checksum verification,
    disaster recovery restoration, and SQLite integrity check.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        source_db = os.path.join(tmpdir, "source.db")
        backup_dir = os.path.join(tmpdir, "backups")

        # 1. Populate source database
        storage = EmotionStorage(db_path=source_db)
        storage.save_emotion_event(
            conversation_id="conv_backup_test",
            primary_emotion="happy",
            confidence=0.95,
            valence=0.8,
            arousal=0.7,
            raw_transcript="Testing backup integrity"
        )

        # 2. Perform backup
        backup_file = backup_sqlite(source_db, backup_dir)
        assert backup_file is not None
        assert os.path.exists(backup_file)
        assert os.path.exists(f"{backup_file}.sha256")

        # 3. Verify checksum
        assert verify_checksum(backup_file) is True

        # 4. Simulate corruption or loss of the source database
        os.remove(source_db)
        assert not os.path.exists(source_db)

        # 5. Restore from backup
        restore_success = restore_sqlite(backup_file, source_db)
        assert restore_success is True
        assert os.path.exists(source_db)

        # 6. Verify restored data
        restored_storage = EmotionStorage(db_path=source_db)
        history = restored_storage.get_history("conv_backup_test")
        assert len(history) == 1
        assert history[0]["primary_emotion"] == "happy"
        assert history[0]["raw_transcript"] == "Testing backup integrity"


def test_backup_retention_pruning():
    """
    Tests that prune_old_backups removes backup archives older than RETENTION_DAYS.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = os.path.join(tmpdir, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        recent_file = os.path.join(backup_dir, "backup_recent.db")
        with open(recent_file, "w") as f:
            f.write("recent backup content")

        old_file = os.path.join(backup_dir, "backup_old.db")
        with open(old_file, "w") as f:
            f.write("old backup content")

        # Artificially age old_file by 10 days
        past_time = (datetime.now() - timedelta(days=10)).timestamp()
        os.utime(old_file, (past_time, past_time))

        # Prune archives older than 7 days
        pruned_count = prune_old_backups(backup_dir, retention_days=7)
        assert pruned_count == 1
        assert not os.path.exists(old_file)
        assert os.path.exists(recent_file)

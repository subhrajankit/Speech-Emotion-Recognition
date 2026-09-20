import sqlite3
import os
import sys

def migrate(db_path: str = "database/dev.db"):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emotion_history_conv ON emotion_history(conversation_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emotion_history_ts ON emotion_history(timestamp);")

    conn.commit()
    conn.close()
    print(f"Migration 001_create_emotion_history applied to {db_path}.")

if __name__ == "__main__":
    db_target = sys.argv[1] if len(sys.argv) > 1 else "database/dev.db"
    migrate(db_target)

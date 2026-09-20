-- Database Schema: emotion_history table
-- Stores user emotional trajectories across conversational turns.
-- Strict privacy rule: RAW AUDIO IS NEVER PERSISTED. Only metadata and transcripts.

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

CREATE INDEX IF NOT EXISTS idx_emotion_history_conv ON emotion_history(conversation_id);
CREATE INDEX IF NOT EXISTS idx_emotion_history_ts ON emotion_history(timestamp);

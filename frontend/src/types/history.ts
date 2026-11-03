/**
 * VoiceSense AI — Conversation History Types
 * Corresponds to Phase 9 backend schemas (backend/app/schemas/history.py).
 */

export interface HistoryItem {
  id: string;
  timestamp: number;
  transcript: string;
  language: string;
  emotion: string | null;
  confidence: number | null;
  processing_time_ms: number;
  audioEvents?: string[];
  assistantText?: string;
  segmentIndex?: number;
}

export interface ModelVersionInfo {
  id: string;
  engine_name: string;
  model_id: string;
  pinned_revision?: string | null;
  decoder_type?: string | null;
}

export interface TranscriptRecord {
  id: string;
  text: string;
  language: string;
  script?: string | null;
  mixed_language: boolean;
  audio_events?: string[] | null;
  created_at: string;
}

export interface EmotionRecord {
  id: string;
  primary_emotion: string;
  confidence: number;
  valence: number;
  arousal: number;
  raw_tags?: string[] | null;
  created_at: string;
}

export interface PredictionRecord {
  id: string;
  audio_duration_ms?: number | null;
  processing_time_ms?: number | null;
  confidence?: number | null;
  model_version?: ModelVersionInfo | null;
  transcript?: TranscriptRecord | null;
  emotion_result?: EmotionRecord | null;
  created_at: string;
}

export interface MessageRecord {
  id: string;
  role: 'user' | 'assistant' | string;
  text: string;
  sources?: any;
  prediction_id?: string | null;
  created_at: string;
}

export interface SessionSummary {
  id: string;
  primary_language?: string | null;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

export interface SessionDetail {
  id: string;
  primary_language?: string | null;
  created_at: string;
  updated_at: string;
  predictions: PredictionRecord[];
  messages: MessageRecord[];
}

export interface DeleteHistoryResponse {
  deleted: boolean;
  purged_sessions_count: number;
  message: string;
}

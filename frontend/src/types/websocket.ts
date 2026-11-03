/**
 * VoiceSense AI — WebSocket Protocol v1 Types
 * Matches docs/api/websocket.md specification.
 */

export type WebSocketConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error';

// --- Client -> Server Messages ---

export interface StartMessage {
  type: 'start';
  sample_rate?: number;
  encoding?: string;
  language_hint?: string | null;
  auth_token?: string | null;
  session_id?: string | null;
}

export interface StopMessage {
  type: 'stop';
}

export interface PingMessage {
  type: 'ping';
}

export type ClientMessage = StartMessage | StopMessage | PingMessage;

// --- Server -> Client Messages ---

export interface ReadyMessage {
  type: 'ready';
}

export interface PongMessage {
  type: 'pong';
}

export interface VadMessage {
  type: 'vad';
  state: 'speech_start' | 'speech_end';
}

export interface StatusMessage {
  type: 'status';
  state?: 'loading_model' | 'model_ready' | string;
  engine?: string;
  status?: string;
  message?: string;
  [key: string]: any;
}

export interface SpeechResultMessage {
  type: 'speech_result';
  transcript: string;
  language: string;
  emotion: string | null;
  confidence: number | null;
  processing_time_ms: number;
  model_version?: string;
  audio_events?: string[];
  segments?: any[];
  debug?: {
    raw_tags?: string[];
    vad_has_speech?: boolean;
    segment_index?: number;
    segment_bytes?: number;
    segment_duration_s?: number;
    session_total_audio_bytes?: number;
    flushed_on_stop?: boolean;
    [key: string]: any;
  };
}

export interface LlmDeltaMessage {
  type: 'llm_delta';
  delta: string;
}

export interface RagSourceItem {
  doc_name: string;
  chunk_id: string;
  score: number;
  [key: string]: any;
}

export interface RagSourcesMessage {
  type: 'rag_sources';
  sources: RagSourceItem[];
}

export interface LlmDoneMessage {
  type: 'llm_done';
  text: string;
  sources?: RagSourceItem[];
}

export interface TtsChunkMessage {
  type: 'tts_chunk';
  index: number;
  sample_rate: number;
  text: string;
  format: string;
}

export interface TtsDoneMessage {
  type: 'tts_done';
  total_chunks: number;
  total_duration_ms: number;
}

export interface ErrorMessage {
  type: 'error';
  code: string;
  message: string;
}

export type ServerMessage =
  | ReadyMessage
  | PongMessage
  | VadMessage
  | StatusMessage
  | SpeechResultMessage
  | LlmDeltaMessage
  | RagSourcesMessage
  | LlmDoneMessage
  | TtsChunkMessage
  | TtsDoneMessage
  | ErrorMessage;

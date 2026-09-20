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
    [key: string]: any;
  };
}

export interface ErrorMessage {
  type: 'error';
  code: string;
  message: string;
}

// --- Reserved Downstream Message Types (Phase 5-8) ---
export type ReservedMessageType =
  | 'llm_delta'
  | 'llm_done'
  | 'tts_chunk'
  | 'tts_done'
  | 'status';

export interface ReservedMessage {
  type: ReservedMessageType;
  [key: string]: any;
}

export type ServerMessage =
  | ReadyMessage
  | PongMessage
  | VadMessage
  | SpeechResultMessage
  | ErrorMessage
  | ReservedMessage;

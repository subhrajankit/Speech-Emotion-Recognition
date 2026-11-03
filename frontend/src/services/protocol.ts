/**
 * VoiceSense AI — Protocol v1 Serializer & Parser
 * Pure functions with zero external dependencies.
 */

import {
  StartMessage,
  StopMessage,
  PingMessage,
  ServerMessage,
  StatusMessage,
  LlmDeltaMessage,
  LlmDoneMessage,
  RagSourcesMessage,
  TtsChunkMessage,
  TtsDoneMessage,
} from '../types/websocket';

export const RESERVED_MESSAGE_TYPES = [
  'llm_delta',
  'llm_done',
  'tts_chunk',
  'tts_done',
  'status',
  'rag_sources',
] as const;

export function isReservedMessageType(type: string): boolean {
  return (RESERVED_MESSAGE_TYPES as readonly string[]).includes(type);
}

export function createStartMessage(options?: {
  sample_rate?: number;
  encoding?: string;
  language_hint?: string | null;
  auth_token?: string | null;
  session_id?: string | null;
}): StartMessage {
  const msg: StartMessage = {
    type: 'start',
    sample_rate: options?.sample_rate ?? 16000,
    encoding: options?.encoding ?? 'pcm_s16le',
    language_hint: options?.language_hint ?? null,
  };

  if (options?.auth_token !== undefined && options.auth_token !== null && options.auth_token !== '') {
    msg.auth_token = options.auth_token;
  }
  if (options?.session_id !== undefined && options.session_id !== null && options.session_id !== '') {
    msg.session_id = options.session_id;
  }

  return msg;
}

export function createStopMessage(): StopMessage {
  return {
    type: 'stop',
  };
}

export function createPingMessage(): PingMessage {
  return {
    type: 'ping',
  };
}

/**
 * Parses and validates incoming JSON text frames from the server.
 * Returns typed ServerMessage or null for completely invalid payloads.
 */
export function parseServerMessage(data: unknown): ServerMessage | null {
  if (!data) return null;

  let parsed: any;
  if (typeof data === 'string') {
    try {
      parsed = JSON.parse(data);
    } catch {
      console.warn('[Protocol] Malformed JSON received:', data);
      return null;
    }
  } else if (typeof data === 'object') {
    parsed = data;
  } else {
    return null;
  }

  if (!parsed || typeof parsed.type !== 'string') {
    console.debug('[Protocol] Message missing type attribute:', parsed);
    return null;
  }

  switch (parsed.type) {
    case 'ready':
      return { type: 'ready' };

    case 'pong':
      return { type: 'pong' };

    case 'vad':
      if (parsed.state === 'speech_start' || parsed.state === 'speech_end') {
        return {
          type: 'vad',
          state: parsed.state,
        };
      }
      return null;

    case 'status':
      return {
        type: 'status',
        state: typeof parsed.state === 'string' ? parsed.state : undefined,
        engine: typeof parsed.engine === 'string' ? parsed.engine : undefined,
        status: typeof parsed.status === 'string' ? parsed.status : undefined,
        message: typeof parsed.message === 'string' ? parsed.message : undefined,
        ...parsed,
      } as StatusMessage;

    case 'speech_result':
      return {
        type: 'speech_result',
        transcript: typeof parsed.transcript === 'string' ? parsed.transcript : '',
        language: typeof parsed.language === 'string' ? parsed.language : 'unknown',
        emotion: typeof parsed.emotion === 'string' ? parsed.emotion : null,
        confidence: typeof parsed.confidence === 'number' ? parsed.confidence : null,
        processing_time_ms:
          typeof parsed.processing_time_ms === 'number' ? parsed.processing_time_ms : 0,
        model_version: parsed.model_version,
        audio_events: Array.isArray(parsed.audio_events) ? parsed.audio_events : [],
        segments: Array.isArray(parsed.segments) ? parsed.segments : [],
        debug: typeof parsed.debug === 'object' && parsed.debug !== null ? parsed.debug : {},
      };

    case 'llm_delta':
      return {
        type: 'llm_delta',
        delta: typeof parsed.delta === 'string' ? parsed.delta : '',
      } as LlmDeltaMessage;

    case 'llm_done':
      return {
        type: 'llm_done',
        text: typeof parsed.text === 'string' ? parsed.text : '',
        sources: Array.isArray(parsed.sources) ? parsed.sources : [],
      } as LlmDoneMessage;

    case 'rag_sources':
      return {
        type: 'rag_sources',
        sources: Array.isArray(parsed.sources) ? parsed.sources : [],
      } as RagSourcesMessage;

    case 'tts_chunk':
      return {
        type: 'tts_chunk',
        index: typeof parsed.index === 'number' ? parsed.index : 0,
        sample_rate: typeof parsed.sample_rate === 'number' ? parsed.sample_rate : 44100,
        text: typeof parsed.text === 'string' ? parsed.text : '',
        format: typeof parsed.format === 'string' ? parsed.format : 'wav',
      } as TtsChunkMessage;

    case 'tts_done':
      return {
        type: 'tts_done',
        total_chunks: typeof parsed.total_chunks === 'number' ? parsed.total_chunks : 0,
        total_duration_ms:
          typeof parsed.total_duration_ms === 'number' ? parsed.total_duration_ms : 0,
      } as TtsDoneMessage;

    case 'error':
      return {
        type: 'error',
        code: typeof parsed.code === 'string' ? parsed.code : 'UNKNOWN_ERROR',
        message: typeof parsed.message === 'string' ? parsed.message : 'An unknown error occurred.',
      };

    default:
      console.debug(`[Protocol] Unknown message type ignored: ${parsed.type}`);
      return null;
  }
}

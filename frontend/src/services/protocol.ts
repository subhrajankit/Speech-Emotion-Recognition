/**
 * VoiceSense AI — Protocol v1 Serializer & Parser
 * Pure functions with zero external dependencies.
 */

import {
  StartMessage,
  StopMessage,
  PingMessage,
  ServerMessage,
  ReservedMessageType,
} from '../types/websocket';

export const RESERVED_MESSAGE_TYPES: ReservedMessageType[] = [
  'llm_delta',
  'llm_done',
  'tts_chunk',
  'tts_done',
  'status',
];

export function createStartMessage(options?: {
  sample_rate?: number;
  encoding?: string;
  language_hint?: string | null;
}): StartMessage {
  return {
    type: 'start',
    sample_rate: options?.sample_rate ?? 16000,
    encoding: options?.encoding ?? 'pcm_s16le',
    language_hint: options?.language_hint ?? null,
  };
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

export function isReservedMessageType(type: string): type is ReservedMessageType {
  return (RESERVED_MESSAGE_TYPES as string[]).includes(type);
}

/**
 * Parses and validates incoming JSON text frames from the server.
 * Unknown or reserved messages return the raw object (or null for completely invalid payloads)
 * and do not raise exceptions.
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
        debug: typeof parsed.debug === 'object' ? parsed.debug : {},
      };

    case 'error':
      return {
        type: 'error',
        code: typeof parsed.code === 'string' ? parsed.code : 'UNKNOWN_ERROR',
        message: typeof parsed.message === 'string' ? parsed.message : 'An unknown error occurred.',
      };

    default:
      if (isReservedMessageType(parsed.type)) {
        console.debug(`[Protocol] Ignoring reserved message type: ${parsed.type}`);
        return parsed as ServerMessage;
      }
      console.debug(`[Protocol] Unknown message type ignored: ${parsed.type}`);
      return null;
  }
}

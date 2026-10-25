import { describe, it, expect, vi } from 'vitest';
import {
  parseServerMessage,
  createStartMessage,
  createStopMessage,
  createPingMessage,
  isReservedMessageType,
} from '../services/protocol';

describe('WebSocket Protocol v1 Serializer', () => {
  it('creates a standard start message with default values', () => {
    const msg = createStartMessage();
    expect(msg).toEqual({
      type: 'start',
      sample_rate: 16000,
      encoding: 'pcm_s16le',
      language_hint: null,
    });
  });

  it('creates a start message with custom parameters', () => {
    const msg = createStartMessage({
      sample_rate: 16000,
      encoding: 'pcm_s16le',
      language_hint: 'hi',
    });
    expect(msg).toEqual({
      type: 'start',
      sample_rate: 16000,
      encoding: 'pcm_s16le',
      language_hint: 'hi',
    });
  });

  it('creates a stop message', () => {
    expect(createStopMessage()).toEqual({ type: 'stop' });
  });

  it('creates a ping keepalive message', () => {
    expect(createPingMessage()).toEqual({ type: 'ping' });
  });
});

describe('WebSocket Protocol v1 Parser', () => {
  it('parses valid ready message', () => {
    const raw = JSON.stringify({ type: 'ready' });
    const result = parseServerMessage(raw);
    expect(result).toEqual({ type: 'ready' });
  });

  it('parses valid pong message', () => {
    const raw = JSON.stringify({ type: 'pong' });
    const result = parseServerMessage(raw);
    expect(result).toEqual({ type: 'pong' });
  });

  it('parses valid vad state transitions', () => {
    const startRaw = JSON.stringify({ type: 'vad', state: 'speech_start' });
    expect(parseServerMessage(startRaw)).toEqual({
      type: 'vad',
      state: 'speech_start',
    });

    const endRaw = JSON.stringify({ type: 'vad', state: 'speech_end' });
    expect(parseServerMessage(endRaw)).toEqual({
      type: 'vad',
      state: 'speech_end',
    });
  });

  it('parses unified speech_result frame with rich attributes', () => {
    const raw = JSON.stringify({
      type: 'speech_result',
      transcript: 'Namaste, how are you today?',
      language: 'hi',
      emotion: 'happy',
      confidence: null,
      processing_time_ms: 85,
      model_version: 'SenseVoiceSmall (funasr)',
      audio_events: ['Speech'],
      segments: [],
      debug: {
        raw_tags: ['<|hi|>', '<|HAPPY|>', '<|Speech|>'],
        vad_has_speech: true,
      },
    });

    const result = parseServerMessage(raw);
    expect(result).not.toBeNull();
    expect(result?.type).toBe('speech_result');

    if (result && result.type === 'speech_result') {
      expect(result.transcript).toBe('Namaste, how are you today?');
      expect(result.language).toBe('hi');
      expect(result.emotion).toBe('happy');
      expect(result.confidence).toBeNull();
      expect(result.processing_time_ms).toBe(85);
      expect(result.model_version).toBe('SenseVoiceSmall (funasr)');
      expect(result.audio_events).toContain('Speech');
    }
  });

  it('parses speech_result with emotion = null and confidence = null correctly', () => {
    const raw = JSON.stringify({
      type: 'speech_result',
      transcript: 'नमस्ते आप कैसे हैं',
      language: 'hi',
      emotion: null,
      confidence: null,
      processing_time_ms: 110,
      model_version: 'IndicConformer-600m',
      audio_events: ['Speech'],
      segments: [],
    });

    const result = parseServerMessage(raw);
    expect(result).not.toBeNull();
    expect(result?.type).toBe('speech_result');

    if (result && result.type === 'speech_result') {
      expect(result.transcript).toBe('नमस्ते आप कैसे हैं');
      expect(result.language).toBe('hi');
      expect(result.emotion).toBeNull();
      expect(result.confidence).toBeNull();
      expect(result.processing_time_ms).toBe(110);
      expect(result.model_version).toBe('IndicConformer-600m');
    }
  });

  it('parses error frames correctly', () => {
    const raw = JSON.stringify({
      type: 'error',
      code: 'BUFFER_OVERFLOW',
      message: 'Connection buffer limit exceeded.',
    });

    const result = parseServerMessage(raw);
    expect(result).toEqual({
      type: 'error',
      code: 'BUFFER_OVERFLOW',
      message: 'Connection buffer limit exceeded.',
    });
  });

  it('safely handles reserved downstream message types without throwing', () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});

    expect(isReservedMessageType('llm_delta')).toBe(true);
    expect(isReservedMessageType('tts_chunk')).toBe(true);

    const reservedMsg = JSON.stringify({
      type: 'tts_chunk',
      chunk_index: 0,
    });
    const parsed = parseServerMessage(reservedMsg);
    expect(parsed).not.toBeNull();
    expect(parsed?.type).toBe('tts_chunk');

    debugSpy.mockRestore();
  });

  it('safely handles unknown message types by returning null and logging debug', () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});

    const unknown = JSON.stringify({
      type: 'some_future_unsupported_action',
      foo: 'bar',
    });
    expect(parseServerMessage(unknown)).toBeNull();

    debugSpy.mockRestore();
  });

  it('gracefully handles malformed JSON without raising exceptions', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    expect(parseServerMessage('{ malformed: true ')).toBeNull();
    expect(parseServerMessage('')).toBeNull();
    expect(parseServerMessage(null)).toBeNull();
    expect(parseServerMessage(undefined)).toBeNull();

    warnSpy.mockRestore();
  });
});

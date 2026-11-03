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

  it('creates a start message with in-frame auth_token and session_id', () => {
    const msg = createStartMessage({
      sample_rate: 16000,
      encoding: 'pcm_s16le',
      language_hint: 'hi',
      auth_token: 'fake-jwt-token-xyz',
      session_id: 'sess_12345',
    });
    expect(msg).toEqual({
      type: 'start',
      sample_rate: 16000,
      encoding: 'pcm_s16le',
      language_hint: 'hi',
      auth_token: 'fake-jwt-token-xyz',
      session_id: 'sess_12345',
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

  it('parses status messages for model lazy loading', () => {
    const loadMsg = JSON.stringify({
      type: 'status',
      state: 'loading_model',
      engine: 'indicconformer',
    });
    const parsedLoad = parseServerMessage(loadMsg);
    expect(parsedLoad).toEqual({
      type: 'status',
      state: 'loading_model',
      engine: 'indicconformer',
    });

    const readyMsg = JSON.stringify({
      type: 'status',
      state: 'model_ready',
      engine: 'indicconformer',
    });
    const parsedReady = parseServerMessage(readyMsg);
    expect(parsedReady).toEqual({
      type: 'status',
      state: 'model_ready',
      engine: 'indicconformer',
    });
  });

  it('parses unified speech_result frame with rich attributes and segment index', () => {
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
        segment_index: 2,
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
      expect(result.debug?.segment_index).toBe(2);
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

  it('parses llm_delta, llm_done, and rag_sources frames correctly', () => {
    const deltaRaw = JSON.stringify({ type: 'llm_delta', delta: 'Hello world' });
    expect(parseServerMessage(deltaRaw)).toEqual({
      type: 'llm_delta',
      delta: 'Hello world',
    });

    const doneRaw = JSON.stringify({
      type: 'llm_done',
      text: 'Hello world from AI',
      sources: [{ doc_name: 'policy.md', chunk_id: 'c1', score: 0.95 }],
    });
    expect(parseServerMessage(doneRaw)).toEqual({
      type: 'llm_done',
      text: 'Hello world from AI',
      sources: [{ doc_name: 'policy.md', chunk_id: 'c1', score: 0.95 }],
    });

    const ragRaw = JSON.stringify({
      type: 'rag_sources',
      sources: [{ doc_name: 'manual.txt', chunk_id: 'c2', score: 0.88 }],
    });
    expect(parseServerMessage(ragRaw)).toEqual({
      type: 'rag_sources',
      sources: [{ doc_name: 'manual.txt', chunk_id: 'c2', score: 0.88 }],
    });
  });

  it('parses tts_chunk and tts_done frames correctly', () => {
    const chunkRaw = JSON.stringify({
      type: 'tts_chunk',
      index: 0,
      sample_rate: 44100,
      text: 'Hello',
      format: 'wav',
    });
    expect(parseServerMessage(chunkRaw)).toEqual({
      type: 'tts_chunk',
      index: 0,
      sample_rate: 44100,
      text: 'Hello',
      format: 'wav',
    });

    const doneRaw = JSON.stringify({
      type: 'tts_done',
      total_chunks: 1,
      total_duration_ms: 1200.0,
    });
    expect(parseServerMessage(doneRaw)).toEqual({
      type: 'tts_done',
      total_chunks: 1,
      total_duration_ms: 1200.0,
    });
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

  it('checks reserved message types', () => {
    expect(isReservedMessageType('llm_delta')).toBe(true);
    expect(isReservedMessageType('tts_chunk')).toBe(true);
    expect(isReservedMessageType('some_random_event')).toBe(false);
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

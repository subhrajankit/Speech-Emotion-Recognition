import { describe, it, expect } from 'vitest';
import { formatEmotion, formatConfidence, formatElapsedSeconds, formatErrorMessage } from '../lib/formatters';

describe('Null-Safe Display Formatters', () => {
  describe('formatEmotion', () => {
    it('returns "-" for null, undefined, empty, or "null" string', () => {
      expect(formatEmotion(null)).toBe('-');
      expect(formatEmotion(undefined)).toBe('-');
      expect(formatEmotion('')).toBe('-');
      expect(formatEmotion('null')).toBe('-');
      expect(formatEmotion('NULL')).toBe('-');
    });

    it('capitalizes valid emotion strings', () => {
      expect(formatEmotion('happy')).toBe('Happy');
      expect(formatEmotion('NEUTRAL')).toBe('Neutral');
      expect(formatEmotion('sad')).toBe('Sad');
      expect(formatEmotion('angry')).toBe('Angry');
    });
  });

  describe('formatConfidence', () => {
    it('returns "-" for null, undefined, "null", NaN, or non-finite numbers', () => {
      expect(formatConfidence(null)).toBe('-');
      expect(formatConfidence(undefined)).toBe('-');
      expect(formatConfidence('null')).toBe('-');
      expect(formatConfidence(NaN)).toBe('-');
      expect(formatConfidence(Infinity)).toBe('-');
      expect(formatConfidence('not-a-number')).toBe('-');
    });

    it('formats valid confidence numbers as percentages rounded to nearest integer', () => {
      expect(formatConfidence(0.952)).toBe('95%');
      expect(formatConfidence(0.8)).toBe('80%');
      expect(formatConfidence(1.0)).toBe('100%');
      expect(formatConfidence(0.0)).toBe('0%');
      expect(formatConfidence('0.87')).toBe('87%');
    });
  });

  describe('formatElapsedSeconds', () => {
    it('formats seconds as m:ss', () => {
      expect(formatElapsedSeconds(0)).toBe('0:00');
      expect(formatElapsedSeconds(7)).toBe('0:07');
      expect(formatElapsedSeconds(59)).toBe('0:59');
      expect(formatElapsedSeconds(60)).toBe('1:00');
      expect(formatElapsedSeconds(83)).toBe('1:23');
      expect(formatElapsedSeconds(600)).toBe('10:00');
    });

    it('clamps negative and fractional input', () => {
      expect(formatElapsedSeconds(-5)).toBe('0:00');
      expect(formatElapsedSeconds(7.9)).toBe('0:07');
    });
  });

  describe('formatErrorMessage', () => {
    it('maps standard backend error codes to user-friendly messages', () => {
      expect(formatErrorMessage('INFERENCE_ERROR')).toContain('Speech recognition error');
      expect(formatErrorMessage('llm_unavailable')).toContain('AI reasoning assistant is currently offline');
      expect(formatErrorMessage('llm_bad_response')).toContain('invalid or incomplete response');
      expect(formatErrorMessage('tts_unavailable')).toContain('Voice reply synthesis is unavailable');
      expect(formatErrorMessage('RATE_LIMIT_EXCEEDED')).toContain('rate limit exceeded');
      expect(formatErrorMessage('AUDIO_DURATION_LIMIT_EXCEEDED')).toContain('~30-second audio limit');
      expect(formatErrorMessage('AUDIO_DURATION_LIMIT_EXCEEDED')).toContain('discarded');
      expect(formatErrorMessage('AUDIO_DURATION_LIMIT_EXCEEDED')).toContain('still active');
      expect(formatErrorMessage('AUTH_REQUIRED')).toContain('Authentication required');
      expect(formatErrorMessage('AUTH_FAILED')).toContain('Authentication failed or token expired');
      // Chunk 9.8D: BUFFER_OVERFLOW is discard-and-continue, not "restart stream".
      expect(formatErrorMessage('BUFFER_OVERFLOW')).toContain('utterance was discarded');
      expect(formatErrorMessage('BUFFER_OVERFLOW')).toContain('still active');
      expect(formatErrorMessage('BUFFER_OVERFLOW')).not.toContain('restart');
    });

    it('falls back to raw message if available for unknown codes', () => {
      expect(formatErrorMessage('CUSTOM_ERR', 'Specific failure reason')).toBe('Specific failure reason');
    });

    it('provides generic fallback if no raw message is supplied for unknown codes', () => {
      expect(formatErrorMessage('UNKNOWN_CODE')).toBe('An unexpected error occurred (UNKNOWN_CODE).');
    });
  });
});


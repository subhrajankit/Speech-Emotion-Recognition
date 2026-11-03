import { describe, it, expect } from 'vitest';
import { formatEmotion, formatConfidence, formatErrorMessage } from '../lib/formatters';

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

  describe('formatErrorMessage', () => {
    it('maps standard backend error codes to user-friendly messages', () => {
      expect(formatErrorMessage('INFERENCE_ERROR')).toContain('Speech recognition error');
      expect(formatErrorMessage('llm_unavailable')).toContain('AI reasoning assistant is currently offline');
      expect(formatErrorMessage('llm_bad_response')).toContain('invalid or incomplete response');
      expect(formatErrorMessage('tts_unavailable')).toContain('Voice reply synthesis is unavailable');
      expect(formatErrorMessage('RATE_LIMIT_EXCEEDED')).toContain('rate limit exceeded');
      expect(formatErrorMessage('AUDIO_DURATION_LIMIT_EXCEEDED')).toContain('duration limit exceeded');
      expect(formatErrorMessage('AUTH_REQUIRED')).toContain('Authentication required');
      expect(formatErrorMessage('AUTH_FAILED')).toContain('Authentication failed or token expired');
      expect(formatErrorMessage('BUFFER_OVERFLOW')).toContain('buffer limit exceeded');
    });

    it('falls back to raw message if available for unknown codes', () => {
      expect(formatErrorMessage('CUSTOM_ERR', 'Specific failure reason')).toBe('Specific failure reason');
    });

    it('provides generic fallback if no raw message is supplied for unknown codes', () => {
      expect(formatErrorMessage('UNKNOWN_CODE')).toBe('An unexpected error occurred (UNKNOWN_CODE).');
    });
  });
});


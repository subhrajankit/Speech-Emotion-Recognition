import { describe, it, expect } from 'vitest';
import {
  isUtteranceDiscardError,
  discardAlertFor,
  sameAlertMessage,
} from '../lib/utteranceDiscard';

// Chunk 9.8D: duration-cap / buffer-overflow errors discard only the current
// utterance — the session stays live, so they map to a warning, not danger.

describe('isUtteranceDiscardError', () => {
  it('recognizes both discard-and-continue codes', () => {
    expect(isUtteranceDiscardError('AUDIO_DURATION_LIMIT_EXCEEDED')).toBe(true);
    expect(isUtteranceDiscardError('BUFFER_OVERFLOW')).toBe(true);
  });

  it('rejects unrelated error codes', () => {
    expect(isUtteranceDiscardError('RATE_LIMIT_EXCEEDED')).toBe(false);
    expect(isUtteranceDiscardError('INFERENCE_ERROR')).toBe(false);
    expect(isUtteranceDiscardError('NOT_STARTED')).toBe(false);
    expect(isUtteranceDiscardError('llm_unavailable')).toBe(false);
  });
});

describe('discardAlertFor', () => {
  it('maps duration-limit to a warning discard-and-continue alert', () => {
    const alert = discardAlertFor('AUDIO_DURATION_LIMIT_EXCEEDED');
    expect(alert).not.toBeNull();
    expect(alert!.variant).toBe('warning');
    expect(alert!.message).toContain('discarded');
    expect(alert!.message).toContain('still active');
  });

  it('maps buffer-overflow to the same discard-and-continue semantics', () => {
    const alert = discardAlertFor('BUFFER_OVERFLOW');
    expect(alert).not.toBeNull();
    expect(alert!.variant).toBe('warning');
    expect(alert!.message).toContain('discarded');
    expect(alert!.message).toContain('still active');
    expect(alert!.message).not.toContain('restart');
  });

  it('returns null for unrelated errors so they keep the danger path', () => {
    expect(discardAlertFor('RATE_LIMIT_EXCEEDED')).toBeNull();
    expect(discardAlertFor('INFERENCE_ERROR')).toBeNull();
    expect(discardAlertFor('AUTH_FAILED')).toBeNull();
  });
});

describe('sameAlertMessage — duplicate-frame dedupe', () => {
  it('is true only when the identical message is already showing', () => {
    const alert = discardAlertFor('BUFFER_OVERFLOW')!;
    expect(sameAlertMessage({ message: alert.message }, alert)).toBe(true);
    expect(sameAlertMessage({ message: 'different' }, alert)).toBe(false);
    expect(sameAlertMessage(null, alert)).toBe(false);
    expect(sameAlertMessage({}, alert)).toBe(false);
  });
});

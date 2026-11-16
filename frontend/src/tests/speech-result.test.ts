import { describe, it, expect } from 'vitest';
import {
  hasSpeechTranscript,
  isNoSpeechStatus,
  noSpeechNoticeFor,
  NO_SPEECH_MESSAGE,
  NO_SPEECH_STATUS_STATE,
} from '../lib/speechResult';

// NOTE: the handleSpeechResult wiring in App.tsx (skip turn/thinking on empty
// transcript, show notice, clear on next valid result) is React-level and is
// not runtime-tested in this node-env suite — verified by manual smoke.
// These tests pin the classification contract the handler relies on.

describe('hasSpeechTranscript — empty speech_result guard', () => {
  it('rejects an empty transcript', () => {
    expect(hasSpeechTranscript('')).toBe(false);
  });

  it('rejects a whitespace-only transcript', () => {
    expect(hasSpeechTranscript('   ')).toBe(false);
    expect(hasSpeechTranscript('\n\t  \r')).toBe(false);
  });

  it('rejects missing or malformed transcript values', () => {
    expect(hasSpeechTranscript(undefined)).toBe(false);
    expect(hasSpeechTranscript(null)).toBe(false);
    // Non-string payloads must not be treated as valid speech.
    expect(hasSpeechTranscript(42 as unknown)).toBe(false);
    expect(hasSpeechTranscript({} as unknown)).toBe(false);
  });

  it('accepts a normal transcript', () => {
    expect(hasSpeechTranscript('Hello, how are you?')).toBe(true);
  });

  it('accepts transcripts with leading/trailing whitespace', () => {
    expect(hasSpeechTranscript('  padded speech  ')).toBe(true);
  });
});

describe('NO_SPEECH_MESSAGE', () => {
  it('is a brief, non-error, actionable message', () => {
    expect(NO_SPEECH_MESSAGE).toContain('No speech detected');
    expect(NO_SPEECH_MESSAGE.length).toBeLessThan(80);
  });
});

describe('isNoSpeechStatus — server no_speech status event', () => {
  it('matches the documented status state emitted by the backend', () => {
    expect(NO_SPEECH_STATUS_STATE).toBe('no_speech');
    expect(isNoSpeechStatus('no_speech')).toBe(true);
  });

  it('does not match model-loading or other status states', () => {
    expect(isNoSpeechStatus('loading_model')).toBe(false);
    expect(isNoSpeechStatus('model_ready')).toBe(false);
    expect(isNoSpeechStatus(undefined)).toBe(false);
    expect(isNoSpeechStatus(null)).toBe(false);
  });
});

describe('noSpeechNoticeFor — notice lifecycle (Chunk 9.4B)', () => {
  it('shows the notice on a no-speech event', () => {
    expect(noSpeechNoticeFor('no_speech')).toBe(NO_SPEECH_MESSAGE);
  });

  it('clears the notice when a new recording starts', () => {
    // Sequence: notice shown -> user starts a fresh attempt -> cleared.
    expect(noSpeechNoticeFor('no_speech')).toBe(NO_SPEECH_MESSAGE);
    expect(noSpeechNoticeFor('recording_start')).toBeNull();
  });

  it('does not recreate the notice on recording stop (no event maps to it)', () => {
    // There is deliberately no 'recording_stop' event: stopping must never
    // produce the notice. Only 'no_speech' can.
    for (const event of [
      'valid_result',
      'recording_start',
      'dismiss',
      'reset',
    ] as const) {
      expect(noSpeechNoticeFor(event)).toBeNull();
    }
  });

  it('allows the notice to reappear on a subsequent no-speech result', () => {
    // no_speech -> recording_start -> no_speech again must show it again.
    expect(noSpeechNoticeFor('no_speech')).toBe(NO_SPEECH_MESSAGE);
    expect(noSpeechNoticeFor('recording_start')).toBeNull();
    expect(noSpeechNoticeFor('no_speech')).toBe(NO_SPEECH_MESSAGE);
  });

  it('clears on valid result, dismiss, and reset', () => {
    expect(noSpeechNoticeFor('valid_result')).toBeNull();
    expect(noSpeechNoticeFor('dismiss')).toBeNull();
    expect(noSpeechNoticeFor('reset')).toBeNull();
  });
});

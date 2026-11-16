import { describe, it, expect } from 'vitest';
import { micPhase, micToggleAction } from '../lib/micControl';

// Chunk 9.7C-3: shared mic phase model — the same logic App's toggle handler
// and MicrophoneControl's rendering both consume.

describe('micPhase', () => {
  it('is idle when neither recording nor starting', () => {
    expect(micPhase(false, false)).toBe('idle');
  });

  it('is starting while controller startup is pending', () => {
    expect(micPhase(false, true)).toBe('starting');
  });

  it('is recording when capture is live', () => {
    expect(micPhase(true, false)).toBe('recording');
    // Recording wins even if a stale starting flag were ever true.
    expect(micPhase(true, true)).toBe('recording');
  });
});

describe('micToggleAction', () => {
  it('starts from idle', () => {
    expect(micToggleAction('idle')).toBe('start');
  });

  it('cancels (stops) while starting — never a silent busy', () => {
    expect(micToggleAction('starting')).toBe('stop');
  });

  it('stops while recording', () => {
    expect(micToggleAction('recording')).toBe('stop');
  });
});

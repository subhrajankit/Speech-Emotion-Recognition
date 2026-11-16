import { describe, it, expect } from 'vitest';
import { isUnexpectedCaptureTermination } from '../lib/captureFailure';
import type { AudioCaptureErrorType } from '../hooks/useAudioCapture';

// Chunk 9.7B: only 'disconnected' (track ended mid-recording) is an
// unexpected termination that should route through controller.stop().
// Start-time failures are already handled by the controller's 'failed' path.

describe('isUnexpectedCaptureTermination', () => {
  it('returns true only for disconnected tracks', () => {
    const types: (AudioCaptureErrorType | null)[] = [
      'disconnected',
      'permission_denied',
      'no_device',
      'unknown',
      null,
    ];
    expect(isUnexpectedCaptureTermination('disconnected')).toBe(true);
    for (const t of types.filter((t) => t !== 'disconnected')) {
      expect(isUnexpectedCaptureTermination(t)).toBe(false);
    }
  });
});

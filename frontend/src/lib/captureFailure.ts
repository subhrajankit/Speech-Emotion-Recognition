import type { AudioCaptureErrorType } from '../hooks/useAudioCapture';

/**
 * Classifies audio-capture errors for lifecycle recovery (Chunk 9.7B).
 *
 * Only 'disconnected' represents an unexpected mid-recording termination
 * (hardware unplug, OS-level capture revocation) that the user did not
 * initiate. Permission/device/pipeline failures happen inside startCapture
 * and are already handled by the controller's 'failed' path — routing them
 * through stop() would emit a misleading stop frame for a session that
 * never captured audio.
 */
export function isUnexpectedCaptureTermination(
  type: AudioCaptureErrorType | null
): boolean {
  return type === 'disconnected';
}

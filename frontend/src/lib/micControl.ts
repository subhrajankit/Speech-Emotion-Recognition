// Pure phase model for the microphone control (Chunk 9.7C-3).
// Single source of truth shared by App's toggle handler and
// MicrophoneControl's rendering, so "what phase is the mic in" and
// "what should a press do" can never diverge.

export type MicPhase = 'idle' | 'starting' | 'recording';

/**
 * Derives the visible mic phase. `isRecording` (capture live) wins over
 * `isStarting` (controller startup pending) — they are mutually exclusive
 * in practice, but recording is the stronger signal if both were ever true.
 */
export function micPhase(isRecording: boolean, isStarting: boolean): MicPhase {
  if (isRecording) return 'recording';
  if (isStarting) return 'starting';
  return 'idle';
}

/**
 * What a press of the mic control should do in each phase:
 * idle → start; starting → cancel the pending start; recording → stop.
 */
export function micToggleAction(phase: MicPhase): 'start' | 'stop' {
  return phase === 'idle' ? 'start' : 'stop';
}

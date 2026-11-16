// Protocol error codes that mean "the current utterance was discarded but
// the recording session stays live" (Chunk 9.8D). These map to a warning —
// not a danger alert — because capture, the socket, and the controller all
// remain active; the user can simply keep speaking.

import { formatErrorMessage } from './formatters';

export const UTTERANCE_DISCARD_ERROR_CODES = new Set([
  'AUDIO_DURATION_LIMIT_EXCEEDED',
  'BUFFER_OVERFLOW',
]);

export function isUtteranceDiscardError(code: string): boolean {
  return UTTERANCE_DISCARD_ERROR_CODES.has(code);
}

export interface DiscardAlert {
  variant: 'warning';
  message: string;
}

/**
 * Returns the warning alert for a discard-and-continue error, or null for
 * any unrelated code (which keeps its existing error path).
 */
export function discardAlertFor(code: string, rawMessage?: string): DiscardAlert | null {
  if (!isUtteranceDiscardError(code)) return null;
  return { variant: 'warning', message: formatErrorMessage(code, rawMessage) };
}

/**
 * Dedupe guard: repeated identical discard frames must not re-announce or
 * re-render the alert. Returns the previous alert unchanged when the
 * incoming discard message is already on screen.
 */
export function sameAlertMessage(
  prev: { message?: string } | null,
  next: { message: string }
): boolean {
  return prev?.message === next.message;
}

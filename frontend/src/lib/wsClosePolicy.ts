/**
 * VoiceSense AI — WebSocket Close Outcome Classification
 * Pure decision helper for the close-code lifecycle: distinguishes policy
 * rejection (1008) from ordinary network disconnects, and deduplicates
 * repeated auth rejections within one episode.
 */

export type WsCloseOutcome =
  | 'manual' // intentionally closed — never reconnect
  | 'auth_rejected_notify' // first 1008 — notify app, allow one deferred retry
  | 'auth_rejected_silent' // repeated 1008 — stay disconnected, no re-notify
  | 'reconnect'; // ordinary failure — normal backoff reconnect

export const WS_POLICY_VIOLATION = 1008;

export function resolveWsCloseOutcome(
  closeCode: number | null | undefined,
  isManuallyClosed: boolean,
  authAlreadyRejected: boolean
): WsCloseOutcome {
  if (isManuallyClosed) return 'manual';
  if (closeCode === WS_POLICY_VIOLATION) {
    return authAlreadyRejected ? 'auth_rejected_silent' : 'auth_rejected_notify';
  }
  return 'reconnect';
}

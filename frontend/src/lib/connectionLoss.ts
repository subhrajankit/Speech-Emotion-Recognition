/**
 * VoiceSense AI — Connection Loss Classification
 * Pure helper deciding whether a WebSocket connection state represents a
 * genuine loss (vs. a normal transitional state like 'connecting').
 */

import { WebSocketConnectionState } from '../types/websocket';

const CONNECTION_LOST_STATES: ReadonlySet<string> = new Set([
  'reconnecting',
  'disconnected',
  'error',
]);

export function isConnectionLostState(
  state: WebSocketConnectionState | string
): boolean {
  return CONNECTION_LOST_STATES.has(state);
}

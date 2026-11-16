/**
 * Screen-reader live-announcement helpers (Chunk 9.5B).
 *
 * A single polite live region in App.tsx announces completed turns — never
 * per-token deltas. This module is pure so the announcement contract is
 * testable in the node-env suite; the React wiring is verified by smoke test.
 */

export interface LiveAnnouncement {
  /** Monotonic id used as a React key so identical text re-announces. */
  id: number;
  text: string;
}

export type AnnouncementEvent =
  | { type: 'speech_result'; transcript: string }
  | { type: 'llm_done'; text: string }
  | { type: 'interrupted' };
  // NOTE: llm_delta intentionally has no event — streaming tokens must never
  // reach the announcement region.

/** Maps a lifecycle event to announcement text, or null to stay silent. */
export function announcementTextFor(event: AnnouncementEvent): string | null {
  switch (event.type) {
    case 'speech_result': {
      const t = event.transcript.trim();
      return t ? `You said: ${t}` : null;
    }
    case 'llm_done': {
      const t = event.text.trim();
      return t ? `Assistant: ${t}` : null;
    }
    case 'interrupted':
      return 'Response interrupted';
    default:
      // llm_delta and any future non-announceable event stay silent.
      return null;
  }
}

/**
 * Stateful announcer: assigns a fresh id per announcement so two turns with
 * identical text still produce distinct DOM nodes (and therefore distinct
 * live-region announcements).
 */
export function createAnnouncer() {
  let seq = 0;
  return {
    announce(text: string | null): LiveAnnouncement | null {
      if (!text) return null;
      seq += 1;
      return { id: seq, text };
    },
  };
}

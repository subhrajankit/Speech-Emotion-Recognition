/**
 * VoiceSense AI — Request Sequencer
 * Monotonic request identities for guarding async history calls: a response
 * is only allowed to mutate state if its id is still current. `invalidate()`
 * (used on token change/unmount) or a newer `next()` orphans all prior ids.
 */

export interface RequestSequencer {
  /** Returns a fresh request id and orphans all previously issued ids. */
  next(): number;
  /** Invalidates every outstanding request id (e.g. on account switch). */
  invalidate(): void;
  /** True only while `id` is the most recently issued request. */
  isCurrent(id: number): boolean;
}

export function createRequestSequencer(): RequestSequencer {
  let current = 0;
  return {
    next() {
      current += 1;
      return current;
    },
    invalidate() {
      current += 1;
    },
    isCurrent(id: number) {
      return id === current;
    },
  };
}

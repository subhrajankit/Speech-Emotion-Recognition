/**
 * First-run guidance dismissal state.
 *
 * The project deliberately keeps auth tokens in memory only; this flag is a
 * non-sensitive UI preference, so localStorage is acceptable. Every access is
 * wrapped so browsers with storage disabled (private mode, quota, exceptions)
 * degrade to "not dismissed" — the card still renders and remains dismissible
 * for the current session.
 */

const GUIDANCE_KEY = 'voicesense.firstRunGuidance.dismissed';

function storage(): Storage | null {
  try {
    if (typeof globalThis.localStorage === 'undefined') return null;
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

export function isGuidanceDismissed(): boolean {
  const store = storage();
  if (!store) return false;
  try {
    return store.getItem(GUIDANCE_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissGuidance(): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(GUIDANCE_KEY, '1');
  } catch {
    // Storage unavailable — dismissal applies for this session only.
  }
}

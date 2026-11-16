// Pure helpers for modal focus containment (Chunk 9.5D).
// Kept DOM-light so the wrap-around math is unit-testable in the node
// Vitest environment; collectFocusable is the only DOM-touching export.

export const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

/**
 * Ordered focusable descendants of `root`. Excludes disabled controls,
 * aria-hidden subtrees, and elements explicitly removed from tab order.
 */
export function collectFocusable(root: HTMLElement): HTMLElement[] {
  const all = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  return all.filter((el) => {
    if (el.hasAttribute('disabled')) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
    if (el.tabIndex < 0) return false;
    return true;
  });
}

/**
 * Next index when tabbing through `count` focusable items.
 * `currentIndex` of -1 means focus is outside the list (e.g. on the
 * dialog container): forward goes to the first item, backward to the last.
 */
export function nextFocusIndex(currentIndex: number, count: number, reverse = false): number {
  if (count <= 0) return -1;
  if (currentIndex < 0) return reverse ? count - 1 : 0;
  const delta = reverse ? -1 : 1;
  return (currentIndex + delta + count) % count;
}

/** An element is a safe focus-restoration target if still in the document. */
export function isRestorable(element: HTMLElement | null): element is HTMLElement {
  return !!element && element.isConnected && !element.hasAttribute('disabled');
}

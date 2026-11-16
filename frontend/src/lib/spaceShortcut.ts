// Pure eligibility check for the global Space-to-talk shortcut (Chunk 9.6B).
// Kept DOM-agnostic so it is unit-testable in the node Vitest environment:
// callers pass the raw KeyboardEvent; `target` is inspected via duck typing
// (tagName / role / closest / isContentEditable) rather than instanceof,
// which also works for synthetic and partial event objects.

export interface SpaceShortcutEventLike {
  code: string;
  repeat: boolean;
  target: unknown;
}

export interface SpaceShortcutOptions {
  /** When true the shortcut is fully inert (no toggle, no preventDefault). */
  disabled?: boolean;
  /** When true a modal dialog owns the keyboard (e.g. AuthModal open). */
  modalOpen?: boolean;
}

const INTERACTIVE_TAGS = new Set(['A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION']);

const INTERACTIVE_ROLES = new Set([
  'button',
  'link',
  'radio',
  'switch',
  'checkbox',
  'tab',
  'option',
  'menuitem',
  'menuitemcheckbox',
  'menuitemradio',
  'combobox',
  'listbox',
  'slider',
  'spinbutton',
  'searchbox',
  'textbox',
]);

const INTERACTIVE_SELECTOR = [
  'a',
  'button',
  'input',
  'textarea',
  'select',
  'option',
  '[contenteditable=""]',
  '[contenteditable="true"]',
  '[contenteditable="plaintext-only"]',
  '[role="button"]',
  '[role="link"]',
  '[role="radio"]',
  '[role="switch"]',
  '[role="checkbox"]',
  '[role="tab"]',
  '[role="option"]',
  '[role="menuitem"]',
  '[role="menuitemcheckbox"]',
  '[role="menuitemradio"]',
  '[role="combobox"]',
  '[role="listbox"]',
  '[role="slider"]',
  '[role="spinbutton"]',
  '[role="searchbox"]',
  '[role="textbox"]',
].join(',');

interface TargetLike {
  isContentEditable?: boolean;
  tagName?: string;
  getAttribute?: (name: string) => string | null;
  closest?: (selector: string) => unknown;
}

/**
 * True when `target` is (or is inside) an interactive element whose native
 * Space/Enter behavior must be preserved — buttons, links, form fields,
 * content-editable regions, and ARIA interactive roles.
 */
export function isInteractiveTarget(target: unknown): boolean {
  if (!target || typeof target !== 'object') return false;
  const el = target as TargetLike;

  if (el.isContentEditable === true) return true;

  if (typeof el.closest === 'function') {
    try {
      if (el.closest(INTERACTIVE_SELECTOR)) return true;
    } catch {
      // Non-Element mock without a real closest implementation — fall through
      // to tagName/role inspection.
    }
  }

  const tag = typeof el.tagName === 'string' ? el.tagName.toUpperCase() : '';
  if (INTERACTIVE_TAGS.has(tag)) return true;

  const role = typeof el.getAttribute === 'function' ? el.getAttribute('role') : null;
  return !!role && INTERACTIVE_ROLES.has(role);
}

/**
 * Whether a Space keydown should trigger the microphone shortcut.
 * Returns false (and callers must not preventDefault) for repeats,
 * non-Space keys, disabled/modal-open states, and interactive targets.
 */
export function shouldHandleSpaceShortcut(
  event: SpaceShortcutEventLike,
  options: SpaceShortcutOptions = {}
): boolean {
  if (event.code !== 'Space' || event.repeat) return false;
  if (options.disabled || options.modalOpen) return false;
  return !isInteractiveTarget(event.target);
}

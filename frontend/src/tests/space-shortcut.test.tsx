import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  shouldHandleSpaceShortcut,
  isInteractiveTarget,
} from '../lib/spaceShortcut';
import { LanguageSelector } from '../components/LanguageSelector';

// Chunk 9.6B: Space-to-talk shortcut eligibility + LanguageSelector semantics.
// Event-dispatch behavior (actual window listener, preventDefault) requires
// browser validation — these tests pin the pure decision logic and markup.

const space = { code: 'Space', repeat: false };

const el = (over: Record<string, unknown> = {}) =>
  ({ tagName: 'DIV', isContentEditable: false, ...over }) as unknown;

describe('shouldHandleSpaceShortcut', () => {
  it('toggles for Space on ordinary non-interactive content', () => {
    expect(shouldHandleSpaceShortcut({ ...space, target: el() })).toBe(true);
    expect(shouldHandleSpaceShortcut({ ...space, target: documentlessBody() })).toBe(true);
  });

  it('ignores repeated keydown (held Space)', () => {
    expect(
      shouldHandleSpaceShortcut({ code: 'Space', repeat: true, target: el() })
    ).toBe(false);
  });

  it('ignores non-Space keys', () => {
    expect(
      shouldHandleSpaceShortcut({ code: 'Enter', repeat: false, target: el() })
    ).toBe(false);
  });

  it('does not fire on interactive elements (native activation preserved)', () => {
    for (const tag of ['BUTTON', 'A', 'INPUT', 'TEXTAREA', 'SELECT']) {
      expect(shouldHandleSpaceShortcut({ ...space, target: el({ tagName: tag }) })).toBe(false);
    }
  });

  it('does not fire inside elements with interactive ARIA roles', () => {
    const card = el({ getAttribute: (n: string) => (n === 'role' ? 'button' : null) });
    expect(isInteractiveTarget(card)).toBe(true);
    expect(shouldHandleSpaceShortcut({ ...space, target: card })).toBe(false);

    for (const role of ['radio', 'switch', 'checkbox', 'tab', 'option', 'link']) {
      const t = el({ getAttribute: (n: string) => (n === 'role' ? role : null) });
      expect(shouldHandleSpaceShortcut({ ...space, target: t })).toBe(false);
    }
  });

  it('detects interactive ancestors via closest()', () => {
    const inner = {
      tagName: 'SPAN',
      isContentEditable: false,
      closest: (sel: string) => (sel.includes('button') ? {} : null),
    };
    expect(isInteractiveTarget(inner)).toBe(true);
    expect(shouldHandleSpaceShortcut({ ...space, target: inner })).toBe(false);
  });

  it('respects contentEditable targets', () => {
    expect(shouldHandleSpaceShortcut({ ...space, target: el({ isContentEditable: true }) })).toBe(false);
  });

  it('is inert when disabled — caller must not preventDefault', () => {
    expect(shouldHandleSpaceShortcut({ ...space, target: el() }, { disabled: true })).toBe(false);
  });

  it('is inert while a modal dialog owns the keyboard', () => {
    expect(shouldHandleSpaceShortcut({ ...space, target: el() }, { modalOpen: true })).toBe(false);
  });
});

function documentlessBody() {
  // Simulates document.body: a plain non-interactive element.
  return { tagName: 'BODY', isContentEditable: false };
}

describe('LanguageSelector toggle semantics', () => {
  it('exposes aria-pressed and no radio semantics', () => {
    const html = renderToStaticMarkup(
      <LanguageSelector selectedLanguage="en" onChange={() => {}} englishOnly />
    );
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-labelledby="language-selector-label"');
    expect(html).not.toContain('radiogroup');
    expect(html).not.toContain('role="radio"');
    expect(html).not.toContain('aria-checked');
    // English selected → its button pressed, Auto not.
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-pressed="false"');
  });
});

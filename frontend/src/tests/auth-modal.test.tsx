import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AuthModal, AuthFeedback } from '../components/AuthModal';
import { nextFocusIndex, isRestorable } from '../lib/focusTrap';

// Chunk 9.5D: AuthModal focus/keyboard accessibility.
// Node-env coverage: dialog semantics, toggle-button semantics, feedback
// roles, and the pure focus-wrap math. Real DOM focus, Tab/Escape dispatch,
// and async session races require browser validation (no jsdom installed).

const baseProps = {
  isOpen: true,
  onClose: () => {},
  token: null,
  currentUser: null,
  onAuthSuccess: () => {},
  onLogout: () => {},
};

describe('AuthModal dialog semantics', () => {
  it('renders a modal dialog with an accessible name', () => {
    const html = renderToStaticMarkup(<AuthModal {...baseProps} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('aria-labelledby="auth-modal-title"');
    expect(html).toContain('id="auth-modal-title"');
  });

  it('renders nothing when closed', () => {
    const html = renderToStaticMarkup(<AuthModal {...baseProps} isOpen={false} />);
    expect(html).toBe('');
  });

  it('exposes mode controls as toggle buttons, not tabs', () => {
    const html = renderToStaticMarkup(<AuthModal {...baseProps} />);
    expect(html).not.toContain('role="tablist"');
    expect(html).not.toContain('role="tab"');
    expect(html).not.toContain('aria-selected');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('aria-label="Account mode"');
  });

  it('labels all form inputs', () => {
    const html = renderToStaticMarkup(<AuthModal {...baseProps} />);
    expect(html).toContain('for="auth-username-input"');
    expect(html).toContain('id="auth-username-input"');
    expect(html).toContain('for="auth-password-input"');
    expect(html).toContain('id="auth-password-input"');
  });
});

describe('AuthFeedback announcement roles', () => {
  it('uses role="alert" for errors', () => {
    const html = renderToStaticMarkup(<AuthFeedback tone="error">bad creds</AuthFeedback>);
    expect(html).toContain('role="alert"');
    expect(html).not.toContain('role="status"');
  });

  it('uses role="status" for success', () => {
    const html = renderToStaticMarkup(<AuthFeedback tone="success">signed in</AuthFeedback>);
    expect(html).toContain('role="status"');
    expect(html).not.toContain('role="alert"');
  });
});

describe('focusTrap helpers', () => {
  it('wraps forward from last to first', () => {
    expect(nextFocusIndex(2, 3)).toBe(0);
  });

  it('wraps backward from first to last', () => {
    expect(nextFocusIndex(0, 3, true)).toBe(2);
  });

  it('moves normally within bounds', () => {
    expect(nextFocusIndex(0, 3)).toBe(1);
    expect(nextFocusIndex(1, 3, true)).toBe(0);
  });

  it('focus outside the list enters at the correct end', () => {
    expect(nextFocusIndex(-1, 3)).toBe(0);
    expect(nextFocusIndex(-1, 3, true)).toBe(2);
  });

  it('returns -1 for an empty focusable set', () => {
    expect(nextFocusIndex(0, 0)).toBe(-1);
    expect(nextFocusIndex(-1, 0, true)).toBe(-1);
  });

  it('isRestorable accepts connected enabled elements only', () => {
    const connected = { isConnected: true, hasAttribute: () => false } as unknown as HTMLElement;
    const detached = { isConnected: false, hasAttribute: () => false } as unknown as HTMLElement;
    const disabled = { isConnected: true, hasAttribute: (a: string) => a === 'disabled' } as unknown as HTMLElement;
    expect(isRestorable(connected)).toBe(true);
    expect(isRestorable(detached)).toBe(false);
    expect(isRestorable(disabled)).toBe(false);
    expect(isRestorable(null)).toBe(false);
  });
});

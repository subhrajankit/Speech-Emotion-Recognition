import { describe, it, expect } from 'vitest';
import {
  resolveWsCloseOutcome,
  WS_POLICY_VIOLATION,
} from '../lib/wsClosePolicy';

describe('resolveWsCloseOutcome — WebSocket close classification', () => {
  it('close 1008 with credentials in use → notify once, no backoff reconnect', () => {
    expect(resolveWsCloseOutcome(1008, false, false)).toBe('auth_rejected_notify');
  });

  it('repeated 1008 within the same episode → silent, callback not duplicated', () => {
    expect(resolveWsCloseOutcome(1008, false, true)).toBe('auth_rejected_silent');
  });

  it('ordinary network close codes still schedule reconnect', () => {
    for (const code of [1000, 1001, 1006, 1011, 1012]) {
      expect(resolveWsCloseOutcome(code, false, false)).toBe('reconnect');
      expect(resolveWsCloseOutcome(code, false, true)).toBe('reconnect');
    }
  });

  it('missing/abnormal close code → reconnect', () => {
    expect(resolveWsCloseOutcome(null, false, false)).toBe('reconnect');
    expect(resolveWsCloseOutcome(undefined, false, false)).toBe('reconnect');
  });

  it('manual close always wins — even over a pending auth rejection', () => {
    expect(resolveWsCloseOutcome(1008, true, false)).toBe('manual');
    expect(resolveWsCloseOutcome(1006, true, true)).toBe('manual');
  });

  it('anonymous 1008 (AUTH_REQUIRED, no token) still classifies as auth rejection', () => {
    // The classifier is credential-agnostic; App-side clearing is a no-op when
    // no token is held, so anonymous state is never incorrectly cleared.
    expect(resolveWsCloseOutcome(WS_POLICY_VIOLATION, false, false)).toBe('auth_rejected_notify');
  });
});

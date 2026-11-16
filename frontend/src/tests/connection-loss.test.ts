import { describe, it, expect } from 'vitest';
import { isConnectionLostState } from '../lib/connectionLoss';

describe('isConnectionLostState — genuine disconnect classification', () => {
  it('treats reconnecting, disconnected, and error as connection loss', () => {
    expect(isConnectionLostState('reconnecting')).toBe(true);
    expect(isConnectionLostState('disconnected')).toBe(true);
    expect(isConnectionLostState('error')).toBe(true);
  });

  it('does not treat connected or connecting as loss', () => {
    expect(isConnectionLostState('connected')).toBe(false);
    expect(isConnectionLostState('connecting')).toBe(false);
  });
});

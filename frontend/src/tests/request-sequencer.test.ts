import { describe, it, expect } from 'vitest';
import { createRequestSequencer } from '../lib/requestSequencer';

describe('createRequestSequencer — stale async response guarding', () => {
  it('only the most recently issued request id is current', () => {
    const seq = createRequestSequencer();
    const first = seq.next();
    const second = seq.next();

    expect(seq.isCurrent(first)).toBe(false);
    expect(seq.isCurrent(second)).toBe(true);
  });

  it('invalidate() orphans all outstanding request ids (account reset)', () => {
    const seq = createRequestSequencer();
    const reqA = seq.next(); // issued under account A's token

    // Token cleared / account switched before the response arrives.
    seq.invalidate();
    expect(seq.isCurrent(reqA)).toBe(false);

    // A new request under account B proceeds normally.
    const reqB = seq.next();
    expect(seq.isCurrent(reqB)).toBe(true);
  });

  it('a stale response cannot pass isCurrent even after later requests complete', () => {
    const seq = createRequestSequencer();
    const stale = seq.next();
    seq.next();
    seq.next();
    expect(seq.isCurrent(stale)).toBe(false);
  });

  it('ids are monotonic and never reused', () => {
    const seq = createRequestSequencer();
    const ids = [seq.next(), seq.next(), seq.next()];
    expect(new Set(ids).size).toBe(3);
    expect(ids).toEqual([...ids].sort((a, b) => a - b));
  });
});

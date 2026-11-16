import { describe, it, expect } from 'vitest';
import {
  announcementTextFor,
  createAnnouncer,
} from '../lib/announcements';

// Chunk 9.5B: announcement contract. The React wiring (single polite region,
// imperative handler calls, key-based re-announcement) is not runtime-tested
// in this node-env suite — verified by manual screen-reader smoke.

describe('announcementTextFor — event → text mapping', () => {
  it('announces a valid transcript once as "You said: ..."', () => {
    expect(
      announcementTextFor({ type: 'speech_result', transcript: 'Hello there' })
    ).toBe('You said: Hello there');
  });

  it('trims whitespace and stays silent for empty/whitespace transcripts', () => {
    expect(
      announcementTextFor({ type: 'speech_result', transcript: '   ' })
    ).toBeNull();
    expect(
      announcementTextFor({ type: 'speech_result', transcript: '' })
    ).toBeNull();
    expect(
      announcementTextFor({ type: 'speech_result', transcript: '  hi  ' })
    ).toBe('You said: hi');
  });

  it('announces the completed assistant response once on llm_done', () => {
    expect(
      announcementTextFor({ type: 'llm_done', text: 'Here is your answer.' })
    ).toBe('Assistant: Here is your answer.');
  });

  it('stays silent for empty llm_done text', () => {
    expect(announcementTextFor({ type: 'llm_done', text: '   ' })).toBeNull();
  });

  it('announces interruption only via the explicit interrupted event', () => {
    expect(announcementTextFor({ type: 'interrupted' })).toBe(
      'Response interrupted'
    );
    // No event type exists for llm_delta — deltas can never announce.
    expect(
      announcementTextFor({ type: 'llm_delta', delta: 'x' } as never)
    ).toBeNull();
  });
});

describe('createAnnouncer — distinct ids for identical text', () => {
  it('assigns a fresh id per announcement so identical text re-announces', () => {
    const announcer = createAnnouncer();
    const a1 = announcer.announce('You said: hi');
    const a2 = announcer.announce('You said: hi');
    expect(a1?.text).toBe('You said: hi');
    expect(a2?.text).toBe('You said: hi');
    expect(a1?.id).not.toBe(a2?.id);
  });

  it('returns null for empty text and never announces nothing', () => {
    const announcer = createAnnouncer();
    expect(announcer.announce(null)).toBeNull();
    expect(announcer.announce('')).toBeNull();
  });
});

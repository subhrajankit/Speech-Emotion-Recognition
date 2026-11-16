import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { FirstRunGuidance } from '../components/FirstRunGuidance';
import { MicrophoneControl } from '../components/audio/MicrophoneControl';
import {
  dismissGuidance,
  isGuidanceDismissed,
} from '../lib/onboarding';

function makeStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (k: string) => map.get(k) ?? null,
    key: (i: number) => [...map.keys()][i] ?? null,
    removeItem: (k: string) => void map.delete(k),
    setItem: (k: string, v: string) => void map.set(k, String(v)),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('first-run guidance storage', () => {
  it('is not dismissed on a first visit (fresh storage)', () => {
    vi.stubGlobal('localStorage', makeStorage());
    expect(isGuidanceDismissed()).toBe(false);
  });

  it('persists dismissal across reads', () => {
    const store = makeStorage();
    vi.stubGlobal('localStorage', store);
    dismissGuidance();
    expect(isGuidanceDismissed()).toBe(true);
    // Simulates a subsequent visit in the same browser.
    expect(isGuidanceDismissed()).toBe(true);
  });

  it('falls back to not-dismissed when storage throws on read', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {},
    });
    expect(isGuidanceDismissed()).toBe(false);
  });

  it('does not throw when storage is unavailable or throws on write', () => {
    vi.stubGlobal('localStorage', undefined);
    expect(() => dismissGuidance()).not.toThrow();

    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {
        throw new Error('quota');
      },
    });
    expect(() => dismissGuidance()).not.toThrow();
    expect(isGuidanceDismissed()).toBe(false);
  });
});

describe('FirstRunGuidance component', () => {
  it('renders guidance with accurate English-only, text-response wording', () => {
    vi.stubGlobal('localStorage', makeStorage());
    const html = renderToStaticMarkup(<FirstRunGuidance />);

    expect(html).toContain('Your first voice interaction');
    expect(html).toContain('Select English');
    expect(html).toContain('English-only Auto');
    expect(html).toContain('Start Listening');
    expect(html).toContain('microphone access');
    expect(html).toContain("assistant&#x27;s text response");
    expect(html).toContain('voice playback is disabled by default');

    // Must not overclaim capabilities.
    expect(html).not.toMatch(/multilingual/i);
    expect(html).not.toMatch(/hindi/i);
    expect(html).not.toMatch(/detect any language/i);
    expect(html).not.toMatch(/stored locally|processed locally/i);
  });

  it('renders nothing after persisted dismissal', () => {
    const store = makeStorage();
    vi.stubGlobal('localStorage', store);
    dismissGuidance();
    expect(renderToStaticMarkup(<FirstRunGuidance />)).toBe('');
  });

  it('renders nothing while a recording is active', () => {
    vi.stubGlobal('localStorage', makeStorage());
    expect(renderToStaticMarkup(<FirstRunGuidance isRecording />)).toBe('');
  });

  it('still renders when storage is entirely unavailable', () => {
    vi.stubGlobal('localStorage', undefined);
    const html = renderToStaticMarkup(<FirstRunGuidance />);
    expect(html).toContain('Your first voice interaction');
  });
});

describe('MicrophoneControl permission microcopy', () => {
  it('shows the browser-permission note before recording', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording={false} onToggle={() => {}} />
    );
    expect(html).toContain(
      'Your browser will ask for microphone access before recording.'
    );
  });

  it('hides the permission note while recording', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording onToggle={() => {}} />
    );
    expect(html).not.toContain('microphone access before recording');
  });
});

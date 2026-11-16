import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { LanguageSelector } from '../components/LanguageSelector';
import { isAsrEnglishOnly } from '../lib/env';

describe('ASR English-only frontend mode', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('defaults to English-only when VITE_ASR_ENGLISH_ONLY is unset', () => {
    expect(isAsrEnglishOnly()).toBe(true);
  });

  it('disables English-only only when VITE_ASR_ENGLISH_ONLY=false', () => {
    vi.stubEnv('VITE_ASR_ENGLISH_ONLY', 'false');
    expect(isAsrEnglishOnly()).toBe(false);
  });

  it('hides Hindi in English-only mode but keeps Auto and English', () => {
    const html = renderToStaticMarkup(
      <LanguageSelector selectedLanguage="auto" onChange={() => {}} englishOnly />
    );

    expect(html).toContain('Auto');
    expect(html).toContain('English');
    expect(html).not.toContain('Hindi');
    expect(html).not.toContain('IndicConformer');
  });

  it('shows Hindi when English-only mode is disabled', () => {
    const html = renderToStaticMarkup(
      <LanguageSelector selectedLanguage="auto" onChange={() => {}} englishOnly={false} />
    );

    expect(html).toContain('Hindi');
  });
});

// Chunk 10.1B: App passes disabled={isRecording || isMicStarting} so a
// language change cannot emit an extra `start` frame while a recording
// startup is still pending. These tests pin the rendered disabled contract;
// the App-level prop wiring itself requires browser validation.
describe('LanguageSelector disabled contract', () => {
  it('disables every option button while disabled (recording or starting)', () => {
    const html = renderToStaticMarkup(
      <LanguageSelector selectedLanguage="auto" onChange={() => {}} disabled />
    );

    const buttons = html.match(/<button[^>]*>/g) ?? [];
    expect(buttons.length).toBeGreaterThan(0);
    for (const btn of buttons) {
      expect(btn).toContain('disabled');
    }
  });

  it('enables options when idle (not recording, not starting)', () => {
    const html = renderToStaticMarkup(
      <LanguageSelector selectedLanguage="auto" onChange={() => {}} />
    );

    expect(html).not.toContain('disabled');
    expect(html).toContain('Auto');
    expect(html).toContain('English');
  });
});

import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { resolveDisplayEmotion } from '../lib/emotionDisplay';
import { EmotionBadge } from '../components/emotion/EmotionBadge';

// Chunk 10.4B: explicit EMO_UNKNOWN/UNK raw tags display "Unknown",
// distinct from missing emotion metadata ("-"). No fabricated labels.

describe('resolveDisplayEmotion', () => {
  it('passes real emotion labels through unchanged', () => {
    for (const emo of ['neutral', 'happy', 'sad', 'angry', 'fearful', 'surprised', 'disgusted']) {
      expect(resolveDisplayEmotion(emo, ['<|en|>', '<|NEUTRAL|>', '<|Speech|>'])).toBe(emo);
    }
  });

  it('returns "unknown" when emotion is null and raw tags contain EMO_UNKNOWN', () => {
    expect(
      resolveDisplayEmotion(null, ['<|en|>', '<|EMO_UNKNOWN|>', '<|Speech|>', '<|withitn|>'])
    ).toBe('unknown');
  });

  it('returns "unknown" when emotion is null and raw tags contain <|UNK|>', () => {
    expect(resolveDisplayEmotion(null, ['<|en|>', '<|UNK|>', '<|Speech|>'])).toBe('unknown');
  });

  it('returns null when emotion is null and no raw tag metadata exists', () => {
    expect(resolveDisplayEmotion(null, undefined)).toBeNull();
    expect(resolveDisplayEmotion(null, null)).toBeNull();
    expect(resolveDisplayEmotion(null, [])).toBeNull();
    expect(resolveDisplayEmotion(null, ['<|en|>', '<|Speech|>'])).toBeNull();
    expect(resolveDisplayEmotion(undefined, undefined)).toBeNull();
  });

  it('does not mark unknown when a real emotion label is present', () => {
    expect(
      resolveDisplayEmotion('neutral', ['<|en|>', '<|NEUTRAL|>', '<|Speech|>'])
    ).toBe('neutral');
  });
});

describe('EmotionBadge unknown display', () => {
  it('renders "Unknown" for explicit unknown emotion', () => {
    const html = renderToStaticMarkup(<EmotionBadge emotion="unknown" confidence={null} />);
    expect(html).toContain('Unknown');
    expect(html).not.toContain('Emotion: -');
  });

  it('renders "Emotion: -" when emotion metadata is missing', () => {
    const html = renderToStaticMarkup(<EmotionBadge emotion={null} confidence={null} />);
    expect(html).toContain('Emotion: -');
  });

  it('renders real labels normally', () => {
    const html = renderToStaticMarkup(<EmotionBadge emotion="neutral" confidence={null} />);
    expect(html).toContain('Neutral');
  });
});

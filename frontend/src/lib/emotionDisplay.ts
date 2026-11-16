/**
 * VoiceSense AI — Emotion display resolution (Chunk 10.4B)
 *
 * The backend emits emotion=null both when the model reports EMO_UNKNOWN and
 * when no emotion metadata exists at all. raw SenseVoice tags in
 * speech_result.debug.raw_tags distinguish the two cases: an explicit
 * <|EMO_UNKNOWN|> or <|UNK|> tag means the model ran SER and reported unknown,
 * which the UI surfaces as "Unknown" — never as a fabricated label and never
 * conflated with missing metadata ("").
 */

const UNKNOWN_EMOTION_TAGS = new Set(['<|EMO_UNKNOWN|>', '<|UNK|>']);

/**
 * Resolves the emotion value to display for a speech_result.
 * - Real model label ('neutral', 'happy', ...) passes through unchanged.
 * - null + explicit unknown tag in raw_tags -> 'unknown' (display: "Unknown").
 * - null + no/absent raw_tags -> null (display: "-").
 */
export function resolveDisplayEmotion(
  emotion: string | null | undefined,
  rawTags: unknown
): string | null {
  if (emotion !== null && emotion !== undefined && emotion !== '') {
    return emotion;
  }
  if (Array.isArray(rawTags) && rawTags.some((t) => UNKNOWN_EMOTION_TAGS.has(t))) {
    return 'unknown';
  }
  return null;
}

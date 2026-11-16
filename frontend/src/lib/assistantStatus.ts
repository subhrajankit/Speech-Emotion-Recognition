/**
 * VoiceSense AI — Assistant Availability Derivation
 * Separates text-assistant availability (LLM health) from voice-reply
 * availability (TTS health). A healthy LLM means text responses work even
 * when TTS is disabled; TTS state is surfaced independently by AudioPlayer.
 */

import { ComponentStatus, HealthComponents } from '../types/speech';

export interface AssistantStatus {
  /** Text replies can be generated — depends only on LLM health. */
  isTextAssistantAvailable: boolean;
  /** Spoken replies can be played back — depends only on TTS health. */
  isVoiceRepliesAvailable: boolean;
  /** LLM is down — assistant offline/error state should be shown. */
  isAssistantUnavailable: boolean;
}

const UNAVAILABLE_LLM_STATES: ReadonlySet<ComponentStatus | string> = new Set([
  'unavailable',
  'offline',
  'unhealthy',
  'not_configured',
]);

const AVAILABLE_TTS_STATES: ReadonlySet<ComponentStatus | string> = new Set([
  'ok',
  'degraded',
]);

export function deriveAssistantStatus(
  components: Pick<HealthComponents, 'llm' | 'tts'>
): AssistantStatus {
  const llm = components.llm;
  const tts = components.tts;

  const isAssistantUnavailable = UNAVAILABLE_LLM_STATES.has(llm);
  const isTextAssistantAvailable = llm === 'ok' || llm === 'degraded';
  const isVoiceRepliesAvailable = AVAILABLE_TTS_STATES.has(tts);

  return {
    isTextAssistantAvailable: isTextAssistantAvailable && !isAssistantUnavailable,
    isVoiceRepliesAvailable,
    isAssistantUnavailable,
  };
}

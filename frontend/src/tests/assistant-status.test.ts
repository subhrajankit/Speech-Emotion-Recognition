import { describe, it, expect } from 'vitest';
import { deriveAssistantStatus } from '../lib/assistantStatus';
import { HealthComponents } from '../types/speech';

function components(llm: HealthComponents['llm'], tts: HealthComponents['tts']): Pick<HealthComponents, 'llm' | 'tts'> {
  return { llm, tts };
}

describe('deriveAssistantStatus — text vs voice availability', () => {
  it('LLM ok + TTS disabled → text assistant available, voice replies disabled', () => {
    const s = deriveAssistantStatus(components('ok', 'disabled'));
    expect(s.isTextAssistantAvailable).toBe(true);
    expect(s.isVoiceRepliesAvailable).toBe(false);
    expect(s.isAssistantUnavailable).toBe(false);
  });

  it('LLM ok + TTS ok → text assistant available, voice replies available', () => {
    const s = deriveAssistantStatus(components('ok', 'ok'));
    expect(s.isTextAssistantAvailable).toBe(true);
    expect(s.isVoiceRepliesAvailable).toBe(true);
    expect(s.isAssistantUnavailable).toBe(false);
  });

  it('LLM unavailable + TTS disabled → text assistant unavailable, voice disabled', () => {
    const s = deriveAssistantStatus(components('unavailable', 'disabled'));
    expect(s.isTextAssistantAvailable).toBe(false);
    expect(s.isVoiceRepliesAvailable).toBe(false);
    expect(s.isAssistantUnavailable).toBe(true);
  });

  it('LLM unavailable + TTS ok → text assistant unavailable; voice alone does not imply availability', () => {
    const s = deriveAssistantStatus(components('unavailable', 'ok'));
    expect(s.isTextAssistantAvailable).toBe(false);
    expect(s.isVoiceRepliesAvailable).toBe(true);
    expect(s.isAssistantUnavailable).toBe(true);
  });

  it('LLM offline (backend unreachable) → unavailable regardless of TTS', () => {
    const s = deriveAssistantStatus(components('offline', 'ok'));
    expect(s.isTextAssistantAvailable).toBe(false);
    expect(s.isAssistantUnavailable).toBe(true);
  });

  it('TTS degraded still counts as voice-capable; unknown TTS states do not', () => {
    expect(deriveAssistantStatus(components('ok', 'degraded')).isVoiceRepliesAvailable).toBe(true);
    expect(deriveAssistantStatus(components('ok', 'not_loaded' as any)).isVoiceRepliesAvailable).toBe(false);
    expect(deriveAssistantStatus(components('ok', 'unavailable')).isVoiceRepliesAvailable).toBe(false);
  });
});

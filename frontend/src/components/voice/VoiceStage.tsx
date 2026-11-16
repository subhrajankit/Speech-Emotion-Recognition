import React from 'react';
import { Mic, Square, Globe, Languages } from 'lucide-react';
import { MicrophoneControl } from '../audio/MicrophoneControl';
import { WaveformVisualizer } from '../audio/WaveformVisualizer';
import { LanguageOption } from '../LanguageSelector';

export type VoiceVisualState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface VoiceStageProps {
  visualState: VoiceVisualState;
  audioLevel: number;

  // Microphone control (passed straight through — no second controller)
  isRecording: boolean;
  onToggleRecording: () => void;
  micDisabled?: boolean;
  isConnecting?: boolean;
  isStarting?: boolean;
  modalOpen?: boolean;
  speechDetected?: boolean;
  elapsedSeconds?: number;

  // Suggested language actions (existing language_hint path)
  selectedLanguage: LanguageOption;
  onLanguageChange: (language: LanguageOption, hint: string | null) => void;
  englishOnly?: boolean;
}

const WAVE_HEIGHT = 120;

/**
 * Premium central voice stage: welcome heading, glowing orb combining the
 * existing WaveformVisualizer (canvas behind) and MicrophoneControl (center),
 * a tap/space instruction, and suggested action cards backed by real handlers.
 */
export const VoiceStage: React.FC<VoiceStageProps> = ({
  visualState,
  audioLevel,
  isRecording,
  onToggleRecording,
  micDisabled = false,
  isConnecting = false,
  isStarting = false,
  modalOpen = false,
  speechDetected = false,
  elapsedSeconds = 0,
  selectedLanguage,
  onLanguageChange,
  englishOnly = false,
}) => {
  const orbStateClass =
    visualState === 'listening'
      ? 'is-listening'
      : visualState === 'thinking'
      ? 'is-thinking'
      : visualState === 'speaking'
      ? 'is-speaking'
      : '';

  const languageActions: { value: LanguageOption; label: string; sub: string }[] = [
    { value: 'auto', label: 'Auto', sub: englishOnly ? 'English ASR' : 'Default engine' },
    { value: 'en', label: 'English', sub: 'en hint' },
    ...(!englishOnly
      ? [{ value: 'hi' as LanguageOption, label: 'Hindi', sub: 'हिन्दी · hi hint' }]
      : []),
  ];

  return (
    <section
      className="voice-console-hero"
      aria-label="Voice assistant"
    >
      {/* Welcome heading */}
      <div className="voice-welcome">
        <h2 className="voice-welcome-title">
          How can I <span className="accent">help</span> you today?
        </h2>
        <p className="voice-welcome-sub">
          Speak naturally — transcription, emotion and AI replies happen locally.
        </p>
      </div>

      {/* Central orb stage */}
      <div className={`voice-stage-orb ${orbStateClass}`}>
        {/* Waveform canvas renders behind the mic control */}
        <div className="voice-stage-canvas" aria-hidden="true">
          <WaveformVisualizer
            state={visualState}
            audioLevel={audioLevel}
            height={WAVE_HEIGHT}
            className="voice-stage-wave"
          />
        </div>

        <div className="voice-stage-content">
          <MicrophoneControl
            isRecording={isRecording}
            onToggle={onToggleRecording}
            disabled={micDisabled}
            isConnecting={isConnecting}
            isStarting={isStarting}
            modalOpen={modalOpen}
            speechDetected={speechDetected}
            elapsedSeconds={elapsedSeconds}
          />

          <div
            className={`voice-instruction ${isRecording ? 'is-recording' : ''}`}
            aria-hidden="true"
          >
            <span className="dot" />
            <span>{isRecording ? 'Listening… tap to stop' : 'Tap to speak or press Space'}</span>
          </div>
        </div>
      </div>

      {/* Suggested actions — all backed by existing functionality */}
      <div className="suggest-grid" role="group" aria-label="Suggested actions">
        <button
          type="button"
          className="suggest-card"
          onClick={onToggleRecording}
          disabled={micDisabled || isConnecting || isStarting}
        >
          <span className="suggest-icon">
            {isRecording ? <Square size={17} aria-hidden="true" /> : <Mic size={17} aria-hidden="true" />}
          </span>
          <span className="suggest-title">{isRecording ? 'Stop listening' : 'Start conversation'}</span>
          <span className="suggest-sub">{isRecording ? 'End this utterance' : 'Speak a question or command'}</span>
        </button>

        {languageActions.map((lang) => (
          <button
            key={lang.value}
            type="button"
            className={`suggest-card ${selectedLanguage === lang.value ? 'active' : ''}`}
            onClick={() =>
              onLanguageChange(lang.value, lang.value === 'auto' ? null : lang.value)
            }
            disabled={micDisabled || isRecording || isStarting}
            aria-pressed={selectedLanguage === lang.value}
          >
            <span className="suggest-icon">
              {lang.value === 'auto' ? (
                <Languages size={17} aria-hidden="true" />
              ) : (
                <Globe size={17} aria-hidden="true" />
              )}
            </span>
            <span className="suggest-title">{lang.label}</span>
            <span className="suggest-sub">{lang.sub}</span>
          </button>
        ))}
      </div>
    </section>
  );
};

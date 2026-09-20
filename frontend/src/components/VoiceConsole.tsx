import React, { useEffect } from 'react';
import { Mic, Square, AlertCircle } from 'lucide-react';
import { WaveformVisualizer } from './WaveformVisualizer';

export type PipelineStage = 'idle' | 'listening' | 'thinking' | 'speaking';

interface VoiceConsoleProps {
  stage: PipelineStage;
  isRecording: boolean;
  onToggleRecording: () => void;
  transcript: string;
  responseText: string;
  audioLevel: number;
  detectedLanguage: string;
  primaryEmotion: string;
  valence: number;
  arousal: number;
  intentCategory: string;
  llmProvider: string;
  latencies: {
    asr_ms?: number;
    ttft_ms?: number;
    ttfa_ms?: number;
    total_ms?: number;
  };
  errorMessage?: string;
  onClearError?: () => void;
}

export const VoiceConsole: React.FC<VoiceConsoleProps> = ({
  stage,
  isRecording,
  onToggleRecording,
  transcript,
  responseText,
  audioLevel,
  detectedLanguage,
  primaryEmotion,
  valence,
  arousal,
  intentCategory,
  llmProvider,
  latencies,
  errorMessage,
  onClearError
}) => {
  // Keyboard shortcut: Space toggles microphone when not focused on an input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        onToggleRecording();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onToggleRecording]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '880px', margin: '0 auto' }}>
      {/* Active Stage & Status Ambient Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <span
            style={{
              display: 'inline-block',
              width: '9px',
              height: '9px',
              borderRadius: '50%',
              backgroundColor:
                stage === 'listening' ? 'var(--color-signal)' :
                stage === 'thinking' ? 'var(--color-energy)' :
                stage === 'speaking' ? 'var(--color-voice)' : 'var(--text-muted)'
            }}
          />
          <span style={{ fontSize: '0.9rem', fontWeight: 600, textTransform: 'capitalize' }}>
            {stage === 'idle' ? 'Ready to listen' :
             stage === 'listening' ? 'Listening to speech...' :
             stage === 'thinking' ? 'Synthesizing response...' :
             'Speaking audio output'}
          </span>
        </div>

        {/* Live contextual metadata (unobtrusive live state, not decorative badges) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          {intentCategory && (
            <span>Gate: <strong style={{ color: 'var(--color-signal)' }}>{intentCategory.toUpperCase()}</strong></span>
          )}
          {detectedLanguage && (
            <span>Lang: <strong style={{ color: 'var(--text-primary)' }}>{detectedLanguage.toUpperCase()}</strong></span>
          )}
          {primaryEmotion && (
            <span>Emotion: <strong style={{ color: 'var(--color-energy)' }}>{primaryEmotion}</strong> ({valence >= 0 ? `+${valence.toFixed(2)}` : valence.toFixed(2)}, {arousal >= 0 ? `+${arousal.toFixed(2)}` : arousal.toFixed(2)})</span>
          )}
          <span>Engine: <strong style={{ color: 'var(--text-primary)' }}>{llmProvider === 'cloud' ? 'Gemini 3 Flash' : 'Local Qwen3'}</strong></span>
        </div>
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.85rem 1.25rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: 'var(--color-danger)', fontSize: '0.88rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={16} />
            <span>{errorMessage}</span>
          </div>
          {onClearError && (
            <button onClick={onClearError} style={{ background: 'transparent', border: 'none', color: 'var(--color-danger)', cursor: 'pointer', fontWeight: 600 }}>
              Dismiss
            </button>
          )}
        </div>
      )}

      {/* Central Visualizer Portal (The Orchestrated State Moment) */}
      <div className="panel" style={{ position: 'relative', overflow: 'hidden', padding: '2rem 1.5rem', background: 'var(--bg-surface)' }}>
        <WaveformVisualizer state={stage} audioLevel={audioLevel} height={120} />

        {/* Central Action Button */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '1.75rem', gap: '0.75rem' }}>
          <button
            className="btn-primary"
            style={{
              padding: '0.9rem 2.2rem',
              fontSize: '1.05rem',
              background: isRecording ? 'var(--color-danger)' : 'var(--color-voice)',
              borderRadius: 'var(--radius-full)'
            }}
            onClick={onToggleRecording}
            aria-label={isRecording ? 'Stop listening' : 'Start listening'}
          >
            {isRecording ? <Square size={18} /> : <Mic size={18} />}
            <span>{isRecording ? 'Finish Speaking' : 'Start Listening'}</span>
          </button>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Press Spacebar to toggle</span>
        </div>
      </div>

      {/* Transcript & Response Area */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
        {/* User Inbound Transcript */}
        <div className="panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>You said</span>
            {latencies.asr_ms !== undefined && latencies.asr_ms > 0 && (
              <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>ASR: {latencies.asr_ms}ms</span>
            )}
          </div>
          <div style={{ fontSize: '1.05rem', color: transcript ? 'var(--text-primary)' : 'var(--text-muted)', minHeight: '42px', fontStyle: transcript ? 'normal' : 'italic' }}>
            {transcript || 'Speak or press Start Listening...'}
          </div>
        </div>

        {/* Assistant Outbound Streaming Response */}
        <div className="panel" style={{ borderLeft: '3px solid var(--color-voice)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--color-voice)' }}>SenseAI Response</span>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              {latencies.ttft_ms !== undefined && latencies.ttft_ms > 0 && (
                <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>TTFT: {latencies.ttft_ms}ms</span>
              )}
              {latencies.ttfa_ms !== undefined && latencies.ttfa_ms > 0 && (
                <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--color-signal)' }}>TTFA: {latencies.ttfa_ms}ms</span>
              )}
              {latencies.total_ms !== undefined && latencies.total_ms > 0 && (
                <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Total: {latencies.total_ms}ms</span>
              )}
            </div>
          </div>
          <div style={{ fontSize: '1.05rem', color: responseText ? 'var(--text-primary)' : 'var(--text-muted)', minHeight: '64px', lineHeight: 1.6 }}>
            {responseText || (stage === 'thinking' ? 'Formulating response...' : 'Awaiting voice input.')}
          </div>
        </div>
      </div>
    </div>
  );
};

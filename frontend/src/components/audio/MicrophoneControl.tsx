import React, { useEffect } from 'react';
import { Mic, Square } from 'lucide-react';

export interface MicrophoneControlProps {
  isRecording: boolean;
  onToggle: () => void;
  disabled?: boolean;
  isConnecting?: boolean;
  speechDetected?: boolean;
}

export const MicrophoneControl: React.FC<MicrophoneControlProps> = ({
  isRecording,
  onToggle,
  disabled = false,
  isConnecting = false,
  speechDetected = false,
}) => {
  // Global shortcut: Space toggles microphone when not focused on an input element
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.code === 'Space' &&
        !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        if (!disabled) {
          onToggle();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onToggle, disabled]);

  const buttonLabel = isRecording
    ? 'Stop listening'
    : isConnecting
    ? 'Connecting to speech server...'
    : 'Start listening';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem' }}>
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {/* Animated pulse halo when actively recording */}
        {isRecording && (
          <span
            style={{
              position: 'absolute',
              width: '88px',
              height: '88px',
              borderRadius: '50%',
              backgroundColor: speechDetected ? 'rgba(239, 68, 68, 0.4)' : 'rgba(59, 130, 246, 0.3)',
              animation: 'pulse 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite',
              pointerEvents: 'none',
            }}
          />
        )}

        <button
          type="button"
          onClick={onToggle}
          disabled={disabled || isConnecting}
          aria-label={buttonLabel}
          aria-pressed={isRecording}
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.6rem',
            padding: '0.95rem 2.2rem',
            fontSize: '1rem',
            fontWeight: 600,
            borderRadius: 'var(--radius-full)',
            backgroundColor: isRecording
              ? 'var(--color-danger)'
              : disabled
              ? 'var(--bg-surface-hover)'
              : 'var(--color-voice)',
            color: disabled ? 'var(--text-muted)' : '#FFFFFF',
            border: 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
            boxShadow: isRecording
              ? '0 0 20px rgba(239, 68, 68, 0.4)'
              : '0 4px 14px rgba(59, 130, 246, 0.25)',
            transition: 'all 0.2s ease',
          }}
        >
          {isRecording ? <Square size={20} /> : <Mic size={20} />}
          <span>{isRecording ? 'Stop Listening' : 'Start Listening'}</span>
        </button>
      </div>

      <div
        aria-live="polite"
        style={{
          fontSize: '0.8rem',
          color: isRecording ? 'var(--color-danger)' : 'var(--text-muted)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
        }}
      >
        {isRecording ? (
          <>
            <span
              style={{
                display: 'inline-block',
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-danger)',
              }}
            />
            <span>{speechDetected ? 'Speech detected (VAD)' : 'Listening for speech...'}</span>
          </>
        ) : (
          <span>Press button or <kbd style={{ fontFamily: 'var(--font-mono)', padding: '0.1rem 0.35rem', background: 'var(--bg-surface-hover)', borderRadius: '3px' }}>Space</kbd> to talk</span>
        )}
      </div>
    </div>
  );
};

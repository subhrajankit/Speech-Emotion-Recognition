import React, { useEffect } from 'react';
import { Mic, Square } from 'lucide-react';
import { formatElapsedSeconds } from '../../lib/formatters';
import { shouldHandleSpaceShortcut } from '../../lib/spaceShortcut';
import { micPhase } from '../../lib/micControl';

/** Seconds of mic-active time after which the duration-limit warning appears. */
export const DURATION_WARNING_SECONDS = 25;

export interface MicrophoneControlProps {
  isRecording: boolean;
  onToggle: () => void;
  disabled?: boolean;
  isConnecting?: boolean;
  /** True while a recording start is pending (permission/pipeline init);
   *  the control acts as a cancel affordance in this state. */
  isStarting?: boolean;
  /** True while a modal dialog (e.g. AuthModal) owns the keyboard. */
  modalOpen?: boolean;
  speechDetected?: boolean;
  /** Elapsed microphone-active seconds; only meaningful while isRecording. */
  elapsedSeconds?: number;
}

export const MicrophoneControl: React.FC<MicrophoneControlProps> = ({
  isRecording,
  onToggle,
  disabled = false,
  isConnecting = false,
  isStarting = false,
  modalOpen = false,
  speechDetected = false,
  elapsedSeconds = 0,
}) => {
  // Global shortcut: Space toggles microphone from non-interactive content.
  // Interactive elements keep their native Space/Enter activation, repeats
  // are ignored, and the shortcut is inert while disabled or modal-blocked.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!shouldHandleSpaceShortcut(e, { disabled, modalOpen })) return;
      e.preventDefault();
      onToggle();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onToggle, disabled, modalOpen]);

  const phase = micPhase(isRecording, isStarting);
  const buttonLabel =
    phase === 'recording'
      ? 'Stop listening'
      : phase === 'starting'
      ? 'Cancel microphone startup'
      : isConnecting
      ? 'Connecting to speech server...'
      : 'Start listening';

  const buttonText =
    phase === 'recording' ? 'Stop Listening' : phase === 'starting' ? 'Starting…' : 'Start Listening';

  const buttonClass = [
    'mic-button',
    phase === 'recording' ? 'is-recording' : '',
    phase === 'starting' ? 'is-starting' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="mic-console">
      <div className="mic-stage">
        {/* Animated halo while actively recording */}
        {isRecording && (
          <span
            className={`mic-halo ${speechDetected ? 'speech' : ''}`}
            aria-hidden="true"
          />
        )}

        <button
          type="button"
          onClick={onToggle}
          disabled={disabled || isConnecting}
          aria-label={buttonLabel}
          aria-pressed={isRecording}
          className={buttonClass}
        >
          <span className="mic-button-face">
            {phase === 'recording' ? <Square size={22} /> : <Mic size={26} />}
            <span className="mic-button-label">{buttonText}</span>
          </span>
        </button>
      </div>

      <div
        aria-live="polite"
        className={`mic-status ${isRecording ? 'is-recording' : ''}`}
      >
        {phase === 'starting' ? (
          <span>Starting microphone…</span>
        ) : phase === 'recording' ? (
          <>
            <span className="rec-dot" aria-hidden="true" />
            <span>{speechDetected ? 'Speech detected (VAD)' : 'Listening for speech...'}</span>
          </>
        ) : (
          <span>Press button or <kbd>Space</kbd> to talk</span>
        )}
      </div>

      {!isRecording && (
        <p className="mic-hint">
          Your browser will ask for microphone access before recording.
        </p>
      )}

      {isRecording && (
        <div className="mic-timer-block">
          {/* role="timer" has implicit aria-live="off": the per-second tick is
              never announced; screen readers get state via the status line. */}
          <span
            role="timer"
            aria-label={`Recording time ${formatElapsedSeconds(elapsedSeconds)}`}
            className="mic-timer"
          >
            {formatElapsedSeconds(elapsedSeconds)}
          </span>
          {elapsedSeconds >= DURATION_WARNING_SECONDS && (
            <span role="status" className="mic-warning">
              Recording session time — the server discards utterances buffered beyond ~30 seconds. Finish this thought soon.
            </span>
          )}
        </div>
      )}
    </div>
  );
};

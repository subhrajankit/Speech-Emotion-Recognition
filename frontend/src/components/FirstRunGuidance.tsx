import React, { useState } from 'react';
import { Info, X } from 'lucide-react';
import { dismissGuidance, isGuidanceDismissed } from '../lib/onboarding';

export interface FirstRunGuidanceProps {
  /** Hide while a recording is in progress so the card never covers the mic controls. */
  isRecording?: boolean;
}

/**
 * Compact, dismissible first-run guidance for the voice tab.
 * Dismissal persists via localStorage when available; otherwise it is
 * session-only. Renders nothing once dismissed or while recording.
 */
export const FirstRunGuidance: React.FC<FirstRunGuidanceProps> = ({
  isRecording = false,
}) => {
  const [dismissed, setDismissed] = useState(isGuidanceDismissed);

  if (dismissed || isRecording) return null;

  const handleDismiss = () => {
    dismissGuidance();
    setDismissed(true);
  };

  return (
    <section
      aria-label="First voice interaction guide"
      className="guidance-card"
    >
      <div className="guidance-head">
        <h2 className="guidance-title">
          <Info size={16} aria-hidden="true" />
          Your first voice interaction
        </h2>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss guidance"
          className="icon-btn"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      <ol className="guidance-list">
        <li>Select English (or leave the English-only Auto option selected).</li>
        <li>Click Start Listening and allow microphone access when your browser asks.</li>
        <li>Speak naturally, then stop listening when finished.</li>
        <li>Your transcript and the assistant's text response will appear below.</li>
      </ol>

      <p className="guidance-note">
        Replies appear as text — voice playback is disabled by default on this server.
      </p>
    </section>
  );
};

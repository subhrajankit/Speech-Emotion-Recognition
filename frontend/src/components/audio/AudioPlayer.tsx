import React from 'react';
import { Volume2, VolumeX, MicOff } from 'lucide-react';
import { ComponentStatus } from '../../types/speech';

export interface AudioPlayerProps {
  isPlaying: boolean;
  onStop: () => void;
  ttsStatus?: ComponentStatus | string;
  className?: string;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  isPlaying,
  onStop,
  ttsStatus,
  className = '',
}) => {
  // Requirement 6: If tts is "disabled", hide playback controls and show "Voice replies are off on this server".
  if (ttsStatus === 'disabled') {
    return (
      <div
        className={`player-disabled ${className}`}
        role="status"
        aria-live="polite"
      >
        <MicOff size={14} aria-hidden="true" />
        <span>Voice replies are off on this server</span>
      </div>
    );
  }

  if (!isPlaying) {
    return null;
  }

  return (
    <div
      className={`player-bar ${className}`}
      role="region"
      aria-label="Assistant audio playback"
    >
      <div className="player-status">
        <Volume2 size={18} className="animate-pulse" aria-hidden="true" />
        <span>Assistant speaking...</span>
      </div>
      <button
        type="button"
        onClick={onStop}
        className="player-stop"
        aria-label="Stop audio playback"
      >
        <VolumeX size={15} aria-hidden="true" />
        <span>Stop</span>
      </button>
    </div>
  );
};

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
        className={`audio-player-disabled ${className}`}
        role="status"
        aria-live="polite"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.45rem 0.85rem',
          borderRadius: 'var(--radius-sm)',
          backgroundColor: 'var(--bg-base)',
          border: '1px solid var(--border-subtle)',
          fontSize: '0.8rem',
          color: 'var(--text-muted)',
        }}
      >
        <MicOff size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <span>Voice replies are off on this server</span>
      </div>
    );
  }

  if (!isPlaying) {
    return null;
  }

  return (
    <div
      className={`audio-player ${className}`}
      role="region"
      aria-label="Assistant audio playback"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.6rem 1rem',
        borderRadius: 'var(--radius-sm)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
        fontSize: '0.85rem',
        width: '100%',
        maxWidth: '400px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--color-voice)' }}>
        <Volume2 size={18} className="animate-pulse" />
        <span style={{ fontWeight: 500 }}>Assistant speaking...</span>
      </div>
      <button
        type="button"
        onClick={onStop}
        aria-label="Stop audio playback"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.35rem',
          background: 'transparent',
          border: 'none',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
          padding: '0.2rem 0.5rem',
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.8rem',
        }}
      >
        <VolumeX size={15} />
        <span>Stop</span>
      </button>
    </div>
  );
};

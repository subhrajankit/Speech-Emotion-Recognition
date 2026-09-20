import React from 'react';
import { Volume2, VolumeX } from 'lucide-react';

export interface AudioPlayerProps {
  isPlaying: boolean;
  onStop: () => void;
  className?: string;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  isPlaying,
  onStop,
  className = '',
}) => {
  if (!isPlaying) {
    return null;
  }

  return (
    <div
      className={`audio-player ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.6rem 1rem',
        borderRadius: 'var(--radius-sm)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
        fontSize: '0.85rem',
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

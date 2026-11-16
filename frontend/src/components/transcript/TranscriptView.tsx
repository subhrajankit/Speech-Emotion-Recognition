import React from 'react';
import { Globe, Clock } from 'lucide-react';
import { Badge } from '../ui/Badge';

export interface TranscriptViewProps {
  transcript: string;
  detectedLanguage?: string | null;
  latencyMs?: number;
  audioEvents?: string[];
  isListening?: boolean;
  className?: string;
}

export const TranscriptView: React.FC<TranscriptViewProps> = ({
  transcript,
  detectedLanguage,
  latencyMs,
  audioEvents = [],
  isListening = false,
  className = '',
}) => {
  const languageLabel =
    detectedLanguage && detectedLanguage !== 'unknown' ? detectedLanguage.toUpperCase() : null;

  return (
    <div
      className={`surface-card conv-card conv-user ${className}`}
      role="region"
      aria-label="User speech transcript"
      style={{
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}
    >
      <div className="card-head">
        <div className="card-title">
          <span>User Speech</span>
          {languageLabel && (
            <Badge variant="accent" style={{ textTransform: 'uppercase' }}>
              <Globe size={11} aria-hidden="true" />
              {languageLabel}
            </Badge>
          )}
        </div>

        {latencyMs !== undefined && latencyMs > 0 && (
          <div className="meta-mono">
            <Clock size={12} aria-hidden="true" />
            <span>ASR: {Math.round(latencyMs)}ms</span>
          </div>
        )}
      </div>

      <div
        className={`transcript-body ${transcript ? 'has-text' : 'empty-hint'}`}
        style={{ minHeight: '48px', fontSize: '1.05rem', lineHeight: 'var(--leading-normal)' }}
      >
        {transcript ? (
          transcript
        ) : isListening ? (
          'Listening... speak into your microphone'
        ) : (
          'No speech detected yet. Click "Start Listening" to speak.'
        )}
      </div>

      {audioEvents.length > 0 && (
        <div className="chip-row">
          <span className="chip-label">Audio Events:</span>
          {audioEvents.map((evt, idx) => (
            <span key={idx} className="chip">
              {evt}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

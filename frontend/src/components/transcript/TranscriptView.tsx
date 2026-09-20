import React from 'react';
import { Globe, Clock } from 'lucide-react';
import { Badge } from '../ui/Badge';

export interface TranscriptViewProps {
  transcript: string;
  detectedLanguage?: string;
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
  return (
    <div
      className={`panel ${className}`}
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            User Speech
          </span>
          {detectedLanguage && detectedLanguage !== 'unknown' && (
            <Badge variant="accent" style={{ textTransform: 'uppercase' }}>
              <Globe size={11} style={{ marginRight: '3px' }} />
              {detectedLanguage}
            </Badge>
          )}
        </div>

        {latencyMs !== undefined && latencyMs > 0 && (
          <div
            className="mono"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
            }}
          >
            <Clock size={12} />
            <span>ASR: {latencyMs}ms</span>
          </div>
        )}
      </div>

      <div
        style={{
          minHeight: '48px',
          fontSize: '1.05rem',
          lineHeight: 1.5,
          color: transcript ? 'var(--text-primary)' : 'var(--text-muted)',
          fontStyle: transcript ? 'normal' : 'italic',
        }}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Audio Events:</span>
          {audioEvents.map((evt, idx) => (
            <span
              key={idx}
              style={{
                fontSize: '0.7rem',
                backgroundColor: 'var(--bg-surface-hover)',
                color: 'var(--text-secondary)',
                padding: '0.1rem 0.4rem',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              {evt}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

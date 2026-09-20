import React from 'react';
import { Bot, Info, Clock } from 'lucide-react';
import { Badge } from '../ui/Badge';

export interface ResponseViewProps {
  responseText?: string;
  isThinking?: boolean;
  isAssistantConfigured?: boolean;
  totalLatencyMs?: number;
  className?: string;
}

export const ResponseView: React.FC<ResponseViewProps> = ({
  responseText = '',
  isThinking = false,
  isAssistantConfigured = false,
  totalLatencyMs,
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
          <Bot size={16} style={{ color: 'var(--color-voice)' }} />
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            AI Assistant
          </span>
          {!isAssistantConfigured && (
            <Badge variant="neutral">Phase 2/3 Perception</Badge>
          )}
        </div>

        {totalLatencyMs !== undefined && totalLatencyMs > 0 && (
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
            <span>Turn: {totalLatencyMs}ms</span>
          </div>
        )}
      </div>

      <div
        style={{
          minHeight: '48px',
          fontSize: '1rem',
          lineHeight: 1.5,
        }}
      >
        {isThinking ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-energy)' }}>
            <span className="animate-spin">●</span>
            <span>Synthesizing response...</span>
          </div>
        ) : responseText ? (
          <div style={{ color: 'var(--text-primary)' }}>{responseText}</div>
        ) : !isAssistantConfigured ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.65rem 0.9rem',
              backgroundColor: 'rgba(59, 130, 246, 0.06)',
              border: '1px solid rgba(59, 130, 246, 0.15)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
            }}
          >
            <Info size={16} style={{ color: 'var(--color-signal)', flexShrink: 0 }} />
            <span>
              Assistant reasoning is not configured in this phase. Real-time ASR, language detection, and emotion analysis are fully operational.
            </span>
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            Assistant response will appear here after speech input.
          </div>
        )}
      </div>
    </div>
  );
};

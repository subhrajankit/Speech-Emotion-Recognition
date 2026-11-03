import React from 'react';
import { Bot, Info, Clock, AlertCircle, FileText } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { formatErrorMessage } from '../../lib/formatters';

export interface ResponseViewProps {
  responseText?: string;
  isThinking?: boolean;
  isAssistantConfigured?: boolean;
  isAssistantUnavailable?: boolean;
  errorCode?: string | null;
  errorMessage?: string | null;
  totalLatencyMs?: number;
  sources?: Array<{ doc_name: string; chunk_id: string; score: number; [key: string]: any }>;
  className?: string;
}

export const ResponseView: React.FC<ResponseViewProps> = ({
  responseText = '',
  isThinking = false,
  isAssistantConfigured = false,
  isAssistantUnavailable = false,
  errorCode = null,
  errorMessage = null,
  totalLatencyMs,
  sources = [],
  className = '',
}) => {
  const displayError = errorCode ? formatErrorMessage(errorCode, errorMessage ?? undefined) : errorMessage;

  return (
    <div
      className={`panel ${className}`}
      role="region"
      aria-label="AI Assistant response"
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
          {displayError || isAssistantUnavailable ? (
            <Badge variant="warning">Assistant Offline / Error</Badge>
          ) : !isAssistantConfigured ? (
            <Badge variant="neutral">Perception Mode</Badge>
          ) : null}
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
        ) : displayError ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.5rem',
              padding: '0.65rem 0.9rem',
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              border: '1px solid rgba(245, 158, 11, 0.25)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
            }}
          >
            <AlertCircle size={16} style={{ color: 'var(--color-energy)', flexShrink: 0, marginTop: '2px' }} />
            <span>{displayError}</span>
          </div>
        ) : responseText ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            <div style={{ color: 'var(--text-primary)' }}>{responseText}</div>

            {sources && sources.length > 0 && (
              <div
                style={{
                  marginTop: '0.4rem',
                  padding: '0.5rem 0.75rem',
                  backgroundColor: 'var(--bg-base)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.78rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                  <FileText size={12} />
                  <span>Sources:</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                  {sources.map((s, idx) => (
                    <div key={idx} style={{ color: 'var(--text-secondary)' }}>
                      • <strong>{s.doc_name}</strong> (relevance: {Math.round(s.score * 100)}%)
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : isAssistantUnavailable ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.65rem 0.9rem',
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              border: '1px solid rgba(245, 158, 11, 0.25)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
            }}
          >
            <Info size={16} style={{ color: 'var(--color-energy)', flexShrink: 0 }} />
            <span>
              Assistant offline. Speech transcription, language detection, and emotion analysis remain active.
            </span>
          </div>
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
              Voice perception active. Assistant response will stream here after speech input.
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

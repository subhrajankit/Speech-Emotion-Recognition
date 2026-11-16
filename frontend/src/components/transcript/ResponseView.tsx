import React from 'react';
import { Bot, Info, Clock, AlertCircle, FileText } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { formatErrorMessage } from '../../lib/formatters';

export interface ResponseViewProps {
  responseText?: string;
  isThinking?: boolean;
  isAssistantAvailable?: boolean;
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
  isAssistantAvailable = false,
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
      className={`surface-card conv-card conv-assistant ${className}`}
      role="region"
      aria-label="AI Assistant response"
      style={{
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}
    >
      <div className="card-head">
        <div className="card-title">
          <Bot size={16} style={{ color: 'var(--color-voice)' }} aria-hidden="true" />
          <span>AI Assistant</span>
          {displayError || isAssistantUnavailable ? (
            <Badge variant="warning">Assistant Offline / Error</Badge>
          ) : !isAssistantAvailable ? (
            <Badge variant="neutral">Perception Mode</Badge>
          ) : null}
        </div>

        {totalLatencyMs !== undefined && totalLatencyMs > 0 && (
          <div className="meta-mono">
            <Clock size={12} aria-hidden="true" />
            <span>Turn: {totalLatencyMs}ms</span>
          </div>
        )}
      </div>

      <div style={{ minHeight: '48px', fontSize: '1rem', lineHeight: 'var(--leading-normal)' }}>
        {isThinking ? (
          <div className="thinking-row">
            <span className="animate-spin" aria-hidden="true">●</span>
            <span>Synthesizing response...</span>
          </div>
        ) : displayError ? (
          <div className="notice notice-warning">
            <AlertCircle size={16} className="notice-icon" style={{ color: 'var(--color-energy)' }} aria-hidden="true" />
            <span>{displayError}</span>
          </div>
        ) : responseText ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            <div className="response-body" style={{ color: 'var(--text-primary)' }}>{responseText}</div>

            {sources && sources.length > 0 && (
              <div className="sources-box">
                <div className="sources-head">
                  <FileText size={12} aria-hidden="true" />
                  <span>Sources:</span>
                </div>
                <div className="sources-list">
                  {sources.map((s, idx) => (
                    <div key={idx}>
                      • <strong>{s.doc_name}</strong> (relevance: {Math.round(s.score * 100)}%)
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : isAssistantUnavailable ? (
          <div className="notice notice-warning">
            <Info size={16} className="notice-icon" style={{ color: 'var(--color-energy)' }} aria-hidden="true" />
            <span>
              Assistant offline. Speech transcription, language detection, and emotion analysis remain active.
            </span>
          </div>
        ) : !isAssistantAvailable ? (
          <div className="notice notice-info">
            <Info size={16} className="notice-icon" style={{ color: 'var(--color-voice)' }} aria-hidden="true" />
            <span>
              Voice perception active. Assistant response will stream here after speech input.
            </span>
          </div>
        ) : (
          <div className="empty-hint">
            Assistant response will appear here after speech input.
          </div>
        )}
      </div>
    </div>
  );
};

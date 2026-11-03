import React from 'react';
import { User, Bot, Globe, Clock, MessageSquare, AlertCircle, FileText } from 'lucide-react';
import { UtteranceTurn } from '../stores/conversationStore';
import { EmotionBadge } from './emotion/EmotionBadge';
import { Badge } from './ui/Badge';
import { formatErrorMessage } from '../lib/formatters';

export interface MultiSegmentTurnsProps {
  turns: UtteranceTurn[];
  activeStreamingTurnId?: string | null;
}

export const MultiSegmentTurns: React.FC<MultiSegmentTurnsProps> = ({
  turns,
  activeStreamingTurnId,
}) => {
  if (turns.length === 0) {
    return null;
  }

  return (
    <section
      role="region"
      aria-label="Conversation Utterance Segments"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        marginTop: '0.5rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3
          style={{
            fontSize: '0.95rem',
            fontWeight: 700,
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            margin: 0,
          }}
        >
          <MessageSquare size={16} />
          <span>Utterance Segments ({turns.length})</span>
        </h3>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Multi-segment turns recorded in this session
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        {turns.map((turn, index) => {
          const segNum = turn.segmentIndex ?? (turns.length - index);
          const isActivelyStreaming = turn.isStreaming && turn.id === activeStreamingTurnId;

          return (
            <div
              key={turn.id}
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.85rem',
                boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)',
              }}
            >
              {/* Segment Header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '0.5rem',
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingBottom: '0.6rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      backgroundColor: 'rgba(59, 130, 246, 0.15)',
                      color: 'var(--color-voice)',
                      padding: '0.15rem 0.5rem',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    Segment #{segNum}
                  </span>

                  {turn.language && turn.language !== 'unknown' && (
                    <Badge variant="accent" style={{ textTransform: 'uppercase' }}>
                      <Globe size={11} style={{ marginRight: '3px' }} />
                      {turn.language}
                    </Badge>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <EmotionBadge emotion={turn.emotion} confidence={turn.confidence} />

                  {turn.processing_time_ms !== undefined && turn.processing_time_ms > 0 && (
                    <div
                      className="mono"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                      }}
                    >
                      <Clock size={11} />
                      <span>{Math.round(turn.processing_time_ms)}ms</span>
                    </div>
                  )}
                </div>
              </div>

              {/* User Speech Utterance */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  <User size={13} />
                  <span>User Speech</span>
                </div>
                <div
                  style={{
                    fontSize: '1rem',
                    lineHeight: 1.5,
                    color: turn.transcript ? 'var(--text-primary)' : 'var(--text-muted)',
                    fontStyle: turn.transcript ? 'normal' : 'italic',
                  }}
                >
                  {turn.transcript || '-'}
                </div>

                {turn.audioEvents && turn.audioEvents.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', flexWrap: 'wrap', marginTop: '0.15rem' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Events:</span>
                    {turn.audioEvents.map((ev, i) => (
                      <span
                        key={i}
                        style={{
                          fontSize: '0.68rem',
                          backgroundColor: 'var(--bg-base)',
                          color: 'var(--text-secondary)',
                          padding: '0.1rem 0.35rem',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        {ev}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Paired Assistant Reply */}
              <div
                style={{
                  marginTop: '0.35rem',
                  paddingTop: '0.75rem',
                  borderTop: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.4rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-voice)' }}>
                  <Bot size={14} />
                  <span>AI Assistant Reply</span>
                  {isActivelyStreaming && (
                    <span style={{ fontSize: '0.72rem', color: 'var(--color-energy)', fontWeight: 400 }}>
                      (streaming...)
                    </span>
                  )}
                </div>

                {turn.assistantError ? (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.45rem',
                      padding: '0.55rem 0.75rem',
                      backgroundColor: 'rgba(245, 158, 11, 0.08)',
                      border: '1px solid rgba(245, 158, 11, 0.25)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.82rem',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <AlertCircle size={14} style={{ color: 'var(--color-energy)', flexShrink: 0, marginTop: '2px' }} />
                    <span>{formatErrorMessage(turn.assistantError)}</span>
                  </div>
                ) : turn.assistantText ? (
                  <div style={{ fontSize: '0.92rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                    {turn.assistantText}
                  </div>
                ) : isActivelyStreaming ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-energy)', fontSize: '0.85rem' }}>
                    <span className="animate-spin">●</span>
                    <span>Synthesizing response...</span>
                  </div>
                ) : (
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                    No assistant reply recorded for this segment.
                  </div>
                )}

                {/* Citations if present */}
                {turn.sources && turn.sources.length > 0 && (
                  <div
                    style={{
                      marginTop: '0.35rem',
                      padding: '0.45rem 0.65rem',
                      backgroundColor: 'var(--bg-base)',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '0.75rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
                      <FileText size={11} />
                      <span>Citations:</span>
                    </div>
                    {turn.sources.map((src, i) => (
                      <div key={i} style={{ color: 'var(--text-secondary)' }}>
                        • {src.doc_name} (score: {Math.round(src.score * 100)}%)
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};


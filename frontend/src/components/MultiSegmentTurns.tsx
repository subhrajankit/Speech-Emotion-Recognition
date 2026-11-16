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
      <div className="card-head">
        <h3 className="section-heading">
          <MessageSquare size={16} aria-hidden="true" />
          <span>Utterance Segments ({turns.length})</span>
        </h3>
        <span className="section-heading-note">
          Multi-segment turns recorded in this session
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        {turns.map((turn, index) => {
          const segNum = turn.segmentIndex ?? (turns.length - index);
          const isActivelyStreaming = turn.isStreaming && turn.id === activeStreamingTurnId;

          return (
            <div key={turn.id} className="turn-card">
              {/* Segment Header */}
              <div className="turn-head">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <span className="turn-badge">Segment #{segNum}</span>

                  {turn.language && turn.language !== 'unknown' && (
                    <Badge variant="accent" style={{ textTransform: 'uppercase' }}>
                      <Globe size={11} aria-hidden="true" />
                      {turn.language}
                    </Badge>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <EmotionBadge emotion={turn.emotion} confidence={turn.confidence} />

                  {turn.processing_time_ms !== undefined && turn.processing_time_ms > 0 && (
                    <div className="meta-mono">
                      <Clock size={11} aria-hidden="true" />
                      <span>{Math.round(turn.processing_time_ms)}ms</span>
                    </div>
                  )}
                </div>
              </div>

              {/* User Speech Utterance */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                <div className="turn-label">
                  <User size={13} aria-hidden="true" />
                  <span>User Speech</span>
                </div>
                <div className="turn-user-bubble">
                  <div className="turn-body" style={{ color: turn.transcript ? 'var(--text-primary)' : 'var(--text-muted)', fontStyle: turn.transcript ? 'normal' : 'italic' }}>
                    {turn.transcript || '-'}
                  </div>

                  {turn.audioEvents && turn.audioEvents.length > 0 && (
                    <div className="chip-row">
                      <span className="chip-label">Events:</span>
                      {turn.audioEvents.map((ev, i) => (
                        <span key={i} className="chip">
                          {ev}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Paired Assistant Reply */}
              <div className="turn-assistant-block">
                <div className="turn-label assistant">
                  <Bot size={14} aria-hidden="true" />
                  <span>AI Assistant Reply</span>
                  {isActivelyStreaming && (
                    <span className="turn-streaming">(streaming...)</span>
                  )}
                </div>

                {turn.assistantError ? (
                  <div className="notice notice-warning" style={{ padding: '0.55rem 0.75rem', fontSize: '0.82rem' }}>
                    <AlertCircle size={14} className="notice-icon" style={{ color: 'var(--color-energy)' }} aria-hidden="true" />
                    <span>{formatErrorMessage(turn.assistantError)}</span>
                  </div>
                ) : turn.assistantText ? (
                  <div className="turn-assistant-text">{turn.assistantText}</div>
                ) : isActivelyStreaming ? (
                  <div className="thinking-row" style={{ fontSize: '0.85rem' }}>
                    <span className="animate-spin" aria-hidden="true">●</span>
                    <span>Synthesizing response...</span>
                  </div>
                ) : (
                  <div className="empty-hint" style={{ fontSize: '0.85rem' }}>
                    No assistant reply recorded for this segment.
                  </div>
                )}

                {/* Citations if present */}
                {turn.sources && turn.sources.length > 0 && (
                  <div className="sources-box" style={{ marginTop: '0.35rem', padding: '0.45rem 0.65rem', fontSize: '0.75rem' }}>
                    <div className="sources-head">
                      <FileText size={11} aria-hidden="true" />
                      <span>Citations:</span>
                    </div>
                    <div className="sources-list">
                      {turn.sources.map((src, i) => (
                        <div key={i}>
                          • {src.doc_name} (score: {Math.round(src.score * 100)}%)
                        </div>
                      ))}
                    </div>
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

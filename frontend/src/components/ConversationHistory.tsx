import React, { useState, useMemo } from 'react';
import { Search, RefreshCw, MessageSquare, Trash2, Calendar, Filter, Clock } from 'lucide-react';
import { HistoryItem } from '../types/history';
import { EmotionBadge } from './emotion/EmotionBadge';
import { Badge } from './ui/Badge';

export interface ConversationHistoryProps {
  history: HistoryItem[];
  onRefresh: () => void;
  onClearHistory: () => void;
  isLoading?: boolean;
}

export const ConversationHistory: React.FC<ConversationHistoryProps> = ({
  history,
  onRefresh,
  onClearHistory,
  isLoading = false,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedEmotion, setSelectedEmotion] = useState('all');

  const filteredHistory = useMemo(() => {
    return history.filter((item) => {
      const matchesSearch =
        !searchTerm ||
        item.transcript.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.language.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesEmotion =
        selectedEmotion === 'all' ||
        (item.emotion && item.emotion.toLowerCase() === selectedEmotion.toLowerCase());

      return matchesSearch && matchesEmotion;
    });
  }, [history, searchTerm, selectedEmotion]);

  const uniqueEmotions = useMemo(() => {
    const set = new Set<string>();
    history.forEach((h) => {
      if (h.emotion) set.add(h.emotion.toLowerCase());
    });
    return Array.from(set);
  }, [history]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '960px', margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>Conversation History</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            Store-backed list of speech perception turns with emotion states and latencies.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={onRefresh}
            disabled={isLoading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.85rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
              cursor: isLoading ? 'not-allowed' : 'pointer',
            }}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            <span>Sync</span>
          </button>
          {history.length > 0 && (
            <button
              type="button"
              className="btn-secondary"
              onClick={onClearHistory}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.45rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                color: 'var(--color-danger)',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              <Trash2 size={14} />
              <span>Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div
        className="panel"
        style={{
          padding: '0.85rem 1rem',
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          gap: '0.85rem',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <div style={{ flex: '1 1 240px', position: 'relative' }}>
          <Search
            size={16}
            style={{
              position: 'absolute',
              left: '0.85rem',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-muted)',
            }}
          />
          <input
            type="text"
            className="input-text"
            style={{
              width: '100%',
              padding: '0.45rem 0.85rem 0.45rem 2.4rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-surface-elevated)',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
            }}
            placeholder="Search transcripts or language..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Filter size={15} style={{ color: 'var(--text-muted)' }} />
          <select
            value={selectedEmotion}
            onChange={(e) => setSelectedEmotion(e.target.value)}
            style={{
              padding: '0.45rem 0.85rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-surface-elevated)',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
            }}
          >
            <option value="all">All Emotions</option>
            {uniqueEmotions.map((em) => (
              <option key={em} value={em}>
                {em.charAt(0).toUpperCase() + em.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* History Records List */}
      {filteredHistory.length === 0 ? (
        <div
          className="panel"
          style={{
            padding: '3rem 1.5rem',
            textAlign: 'center',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '50%',
              background: 'var(--bg-surface-elevated)',
              color: 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1rem auto',
            }}
          >
            <MessageSquare size={22} />
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.35rem' }}>
            No speech interactions recorded yet
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: '420px', margin: '0 auto' }}>
            Spoken interactions will automatically appear here with detected language, emotion, and latency.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {filteredHistory.map((item) => (
            <div
              key={item.id}
              className="panel"
              style={{
                padding: '1rem 1.25rem',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.6rem',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '0.5rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <EmotionBadge emotion={item.emotion} confidence={item.confidence} />
                  {item.language && item.language !== 'unknown' && (
                    <Badge variant="accent" style={{ textTransform: 'uppercase' }}>
                      {item.language}
                    </Badge>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                  }}
                >
                  {item.processing_time_ms > 0 && (
                    <span className="mono" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                      <Clock size={12} />
                      {item.processing_time_ms}ms
                    </span>
                  )}
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <Calendar size={12} />
                    {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
              </div>

              <div style={{ fontSize: '0.98rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                &ldquo;{item.transcript}&rdquo;
              </div>

              {item.audioEvents && item.audioEvents.length > 0 && (
                <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                  {item.audioEvents.map((evt, i) => (
                    <span
                      key={i}
                      style={{
                        fontSize: '0.68rem',
                        backgroundColor: 'var(--bg-surface-elevated)',
                        color: 'var(--text-muted)',
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
          ))}
        </div>
      )}
    </div>
  );
};

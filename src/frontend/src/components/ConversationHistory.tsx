import React, { useState, useMemo } from 'react';
import { Search, RefreshCw, MessageSquare, Trash2, Calendar, Filter } from 'lucide-react';

export interface EmotionRecord {
  id?: number;
  timestamp?: string;
  conversation_id: string;
  primary_emotion: string;
  confidence: number;
  valence: number;
  arousal: number;
  raw_transcript: string;
}

interface ConversationHistoryProps {
  history: EmotionRecord[];
  onRefresh: () => void;
  isLoading: boolean;
  onClearHistory?: () => void;
}

export const ConversationHistory: React.FC<ConversationHistoryProps> = ({
  history,
  onRefresh,
  isLoading,
  onClearHistory,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedEmotion, setSelectedEmotion] = useState('all');

  const filteredHistory = useMemo(() => {
    return history.filter((item) => {
      const matchesSearch =
        !searchTerm ||
        item.raw_transcript?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.conversation_id?.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesEmotion =
        selectedEmotion === 'all' || item.primary_emotion?.toLowerCase() === selectedEmotion.toLowerCase();

      return matchesSearch && matchesEmotion;
    });
  }, [history, searchTerm, selectedEmotion]);

  const uniqueEmotions = useMemo(() => {
    const set = new Set<string>();
    history.forEach((h) => {
      if (h.primary_emotion) set.add(h.primary_emotion.toLowerCase());
    });
    return Array.from(set);
  }, [history]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '960px', margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2>Conversation History</h2>
          <p style={{ fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Encrypted session transcripts and affective emotional records.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn-secondary" onClick={onRefresh} disabled={isLoading}>
            <RefreshCw size={15} className={isLoading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
          {onClearHistory && history.length > 0 && (
            <button className="btn-secondary" onClick={onClearHistory} style={{ color: 'var(--color-danger)' }}>
              <Trash2 size={15} />
              <span>Clear History</span>
            </button>
          )}
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div className="panel" style={{ padding: '1rem', display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ flex: '1 1 240px', position: 'relative' }}>
          <Search size={16} style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            className="input-text"
            style={{ paddingLeft: '2.5rem' }}
            placeholder="Search transcripts or sessions..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Filter size={15} style={{ color: 'var(--text-muted)' }} />
          <select
            className="select-input"
            value={selectedEmotion}
            onChange={(e) => setSelectedEmotion(e.target.value)}
            style={{ width: 'auto', minWidth: '130px' }}
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
        <div className="panel" style={{ padding: '3.5rem 1.5rem', textAlign: 'center' }}>
          <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'var(--bg-surface-elevated)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem auto' }}>
            <MessageSquare size={24} />
          </div>
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>No conversations recorded yet</h3>
          <p style={{ fontSize: '0.9rem', maxWidth: '420px', margin: '0 auto 1.5rem auto' }}>
            Spoken interactions will appear here alongside detected emotional states and timestamps.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          {filteredHistory.map((item, idx) => (
            <div key={item.id || idx} className="panel" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--color-energy)', textTransform: 'capitalize' }}>
                    {item.primary_emotion || 'Neutral'}
                  </span>
                  <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    ({item.valence >= 0 ? `+${item.valence?.toFixed(2)}` : item.valence?.toFixed(2)}, {item.arousal >= 0 ? `+${item.arousal?.toFixed(2)}` : item.arousal?.toFixed(2)})
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  <span className="mono">{item.conversation_id}</span>
                  {item.timestamp && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Calendar size={13} />
                      {new Date(item.timestamp).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              <div style={{ fontSize: '0.95rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                "{item.raw_transcript}"
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

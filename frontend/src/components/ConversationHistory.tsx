import React, { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Trash2,
  Calendar,
  MessageSquare,
  Lock,
  ChevronRight,
  ArrowLeft,
  Bot,
  User as UserIcon,
  Globe,
  Loader2,
} from 'lucide-react';
import {
  fetchHistorySessions,
  fetchSessionDetail,
  deleteSession,
  purgeAllHistory,
} from '../services/api';
import { SessionSummary, SessionDetail } from '../types/history';
import { EmotionBadge } from './emotion/EmotionBadge';
import { Badge } from './ui/Badge';

export interface ConversationHistoryProps {
  token: string | null;
  onOpenAuth: () => void;
  onClearLocalHistory?: () => void;
}

export const ConversationHistory: React.FC<ConversationHistoryProps> = ({
  token,
  onOpenAuth,
}) => {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [confirmPurgeAll, setConfirmPurgeAll] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  // Load sessions list
  const loadSessions = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchHistorySessions(token);
      setSessions(data);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load conversation sessions.');
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      loadSessions();
    } else {
      setSessions([]);
      setSelectedSessionId(null);
      setSessionDetail(null);
    }
  }, [token, loadSessions]);

  // Open session detail
  const handleOpenSession = async (sessionId: string) => {
    if (!token) return;
    setSelectedSessionId(sessionId);
    setIsLoadingDetail(true);
    setErrorMessage(null);
    try {
      const detail = await fetchSessionDetail(sessionId, token);
      setSessionDetail(detail);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load session details.');
    } finally {
      setIsLoadingDetail(false);
    }
  };

  // Delete individual session
  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!token) return;
    if (!window.confirm(`Are you sure you want to delete session ${sessionId}?`)) {
      return;
    }

    setDeletingSessionId(sessionId);
    try {
      await deleteSession(sessionId, token);
      setSuccessMessage(`Session deleted.`);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
        setSessionDetail(null);
      }
      await loadSessions();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to delete session.');
    } finally {
      setDeletingSessionId(null);
    }
  };

  // Delete all my data (Delete-My-Data endpoint)
  const handlePurgeAllData = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const resp = await purgeAllHistory(token);
      setSuccessMessage(resp.message || 'All user history successfully deleted.');
      setConfirmPurgeAll(false);
      setSelectedSessionId(null);
      setSessionDetail(null);
      setSessions([]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to purge user history.');
    } finally {
      setIsLoading(false);
    }
  };

  // Format date helper
  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  // Unauthenticated State
  if (!token) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '1.25rem',
          padding: '3rem 1.5rem',
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          maxWidth: '560px',
          margin: '2rem auto',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            backgroundColor: 'rgba(59, 130, 246, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--color-voice)',
          }}
        >
          <Lock size={22} />
        </div>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>
            Account Required for History
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem', lineHeight: 1.5 }}>
            Under Phase 9 anonymous sessions are isolated and never persisted. Sign in or create a free local account to store, inspect, and manage your speech turns and conversational history.
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenAuth}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.65rem 1.25rem',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            backgroundColor: 'var(--color-voice)',
            color: '#FFFFFF',
            fontWeight: 600,
            fontSize: '0.88rem',
            cursor: 'pointer',
          }}
        >
          <Lock size={15} />
          <span>Sign In / Register</span>
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '960px', margin: '0 auto' }}>
      {/* Header Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', fontWeight: 700, margin: 0 }}>Conversational History</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            Persistent sessions and speech turns stored under your account.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={loadSessions}
            disabled={isLoading}
            aria-label="Refresh session list"
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
            <span>Refresh</span>
          </button>

          {sessions.length > 0 && !confirmPurgeAll && (
            <button
              type="button"
              onClick={() => setConfirmPurgeAll(true)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.45rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                color: 'var(--color-danger)',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              <Trash2 size={14} />
              <span>Delete All My Data</span>
            </button>
          )}

          {confirmPurgeAll && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
              <button
                type="button"
                onClick={handlePurgeAllData}
                disabled={isLoading}
                style={{
                  padding: '0.45rem 0.85rem',
                  borderRadius: 'var(--radius-sm)',
                  border: 'none',
                  backgroundColor: 'var(--color-danger)',
                  color: '#FFFFFF',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Confirm Purge All
              </button>
              <button
                type="button"
                onClick={() => setConfirmPurgeAll(false)}
                style={{
                  padding: '0.45rem 0.65rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  backgroundColor: 'var(--bg-surface)',
                  color: 'var(--text-secondary)',
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Notifications */}
      {errorMessage && (
        <div
          role="alert"
          style={{
            padding: '0.65rem 0.9rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            color: 'var(--color-danger)',
            fontSize: '0.85rem',
          }}
        >
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div
          role="status"
          style={{
            padding: '0.65rem 0.9rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            color: 'var(--color-success)',
            fontSize: '0.85rem',
          }}
        >
          {successMessage}
        </div>
      )}

      {/* Single Session Detail Drilldown */}
      {selectedSessionId && sessionDetail ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <button
            type="button"
            onClick={() => {
              setSelectedSessionId(null);
              setSessionDetail(null);
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              alignSelf: 'flex-start',
              background: 'transparent',
              border: 'none',
              color: 'var(--color-voice)',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              padding: '0.2rem 0',
            }}
          >
            <ArrowLeft size={16} />
            <span>Back to Sessions List</span>
          </button>

          <div
            style={{
              padding: '1.25rem',
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Session ID</div>
                <div className="mono" style={{ fontSize: '0.95rem', fontWeight: 600 }}>{sessionDetail.id}</div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {sessionDetail.primary_language && (
                  <Badge variant="accent">
                    <Globe size={11} style={{ marginRight: '3px' }} />
                    {sessionDetail.primary_language.toUpperCase()}
                  </Badge>
                )}
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {formatDate(sessionDetail.created_at)}
                </span>
              </div>
            </div>

            {/* List of Predictions and Paired Messages */}
            {isLoadingDetail ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', padding: '2rem 0', color: 'var(--text-muted)' }}>
                <Loader2 size={18} className="animate-spin" />
                <span>Loading session details...</span>
              </div>
            ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {sessionDetail.predictions.length === 0 && sessionDetail.messages.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '1rem 0' }}>
                  No stored turns found for this session.
                </div>
              ) : (
                sessionDetail.predictions.map((pred, idx) => {
                  const pairedAssistantMsg = sessionDetail.messages.find(
                    (m) => m.prediction_id === pred.id && m.role === 'assistant'
                  );

                  return (
                    <div
                      key={pred.id || idx}
                      style={{
                        padding: '1rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'var(--bg-base)',
                        border: '1px solid var(--border-subtle)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.65rem',
                      }}
                    >
                      {/* User Utterance */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                            <UserIcon size={13} />
                            <span>User Speech</span>
                            {pred.transcript?.language && (
                              <Badge variant="neutral">{pred.transcript.language}</Badge>
                            )}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <EmotionBadge
                              emotion={pred.emotion_result?.primary_emotion ?? null}
                              confidence={pred.emotion_result?.confidence ?? null}
                            />
                            {pred.processing_time_ms && (
                              <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                {Math.round(pred.processing_time_ms)}ms
                              </span>
                            )}
                          </div>
                        </div>
                        <div style={{ fontSize: '0.95rem', color: 'var(--text-primary)', lineHeight: 1.45 }}>
                          {pred.transcript?.text || <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>-</span>}
                        </div>
                      </div>

                      {/* Paired Assistant Response if present */}
                      {pairedAssistantMsg && (
                        <div
                          style={{
                            marginTop: '0.4rem',
                            paddingTop: '0.6rem',
                            borderTop: '1px solid var(--border-subtle)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '0.3rem',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', color: 'var(--color-voice)', fontWeight: 600 }}>
                            <Bot size={13} />
                            <span>AI Assistant</span>
                          </div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                            {pairedAssistantMsg.text}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
            )}
          </div>
        </div>
      ) : (
        /* Sessions List */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
              Loading sessions...
            </div>
          ) : sessions.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '2.5rem',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-muted)',
              }}
            >
              <MessageSquare size={32} style={{ margin: '0 auto 0.75rem auto', opacity: 0.4 }} />
              <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                No saved sessions found
              </div>
              <div style={{ fontSize: '0.82rem', marginTop: '0.25rem' }}>
                Speech sessions conducted while signed in are automatically stored here.
              </div>
            </div>
          ) : (
            sessions.map((sess) => (
              <div
                key={sess.id}
                role="button"
                tabIndex={0}
                onClick={() => handleOpenSession(sess.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    handleOpenSession(sess.id);
                  }
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '1rem 1.25rem',
                  backgroundColor: 'var(--bg-surface)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease, background-color 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <span className="mono" style={{ fontSize: '0.92rem', fontWeight: 600 }}>
                      {sess.id}
                    </span>
                    {sess.primary_language && (
                      <Badge variant="accent">
                        {sess.primary_language.toUpperCase()}
                      </Badge>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                      <Calendar size={12} />
                      {formatDate(sess.created_at)}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                      <MessageSquare size={12} />
                      {sess.turn_count} {sess.turn_count === 1 ? 'turn' : 'turns'}
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <button
                    type="button"
                    onClick={(e) => handleDeleteSession(sess.id, e)}
                    disabled={deletingSessionId === sess.id}
                    aria-label={`Delete session ${sess.id}`}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      padding: '0.4rem',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                  <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

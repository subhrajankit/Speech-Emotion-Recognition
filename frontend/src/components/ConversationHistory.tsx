import React, { useState, useEffect, useCallback, useRef } from 'react';
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
import { isAuthError } from '../lib/httpErrors';
import { createRequestSequencer, RequestSequencer } from '../lib/requestSequencer';
import { EmotionBadge } from './emotion/EmotionBadge';
import { Badge } from './ui/Badge';

export interface ConversationHistoryProps {
  token: string | null;
  onOpenAuth: () => void;
  onClearLocalHistory?: () => void;
  /** Called when a protected request fails with 401/403; parent clears credentials. */
  onAuthError?: () => void;
  /** External request to open a specific session detail (e.g. from the rail).
   *  `nonce` lets the parent retrigger the same session id. */
  openSessionRequest?: { sessionId: string; nonce: number } | null;
}

export const ConversationHistory: React.FC<ConversationHistoryProps> = ({
  token,
  onOpenAuth,
  onAuthError,
  openSessionRequest,
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

  // Request sequencing: stale async responses (e.g. issued under a previous
  // account's token, or for a previously selected session) must not mutate
  // current state. Invalidated on every token change and on unmount.
  const seqRef = useRef<RequestSequencer | null>(null);
  if (seqRef.current === null) {
    seqRef.current = createRequestSequencer();
  }
  const requestSeq = seqRef.current;

  // Load sessions list
  const loadSessions = useCallback(async () => {
    if (!token) return;
    const reqId = requestSeq.next();
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchHistorySessions(token);
      if (!requestSeq.isCurrent(reqId)) return;
      setSessions(data);
    } catch (err: any) {
      if (!requestSeq.isCurrent(reqId)) return;
      if (isAuthError(err)) {
        onAuthError?.();
        return;
      }
      setErrorMessage(err.message || 'Failed to load conversation sessions.');
    } finally {
      if (requestSeq.isCurrent(reqId)) {
        setIsLoading(false);
      }
    }
  }, [token, onAuthError, requestSeq]);

  useEffect(() => {
    // Invalidate any in-flight request from a previous token/account.
    requestSeq.invalidate();
    if (token) {
      loadSessions();
    } else {
      setSessions([]);
      setSelectedSessionId(null);
      setSessionDetail(null);
      setConfirmPurgeAll(false);
      setErrorMessage(null);
      setSuccessMessage(null);
      setDeletingSessionId(null);
    }
  }, [token, loadSessions, requestSeq]);

  // Invalidate outstanding requests when the component unmounts.
  useEffect(() => {
    return () => requestSeq.invalidate();
  }, [requestSeq]);

  // Open session detail
  const handleOpenSession = useCallback(async (sessionId: string) => {
    if (!token) return;
    const reqId = requestSeq.next();
    setSelectedSessionId(sessionId);
    setIsLoadingDetail(true);
    setErrorMessage(null);
    try {
      const detail = await fetchSessionDetail(sessionId, token);
      if (!requestSeq.isCurrent(reqId)) return;
      setSessionDetail(detail);
    } catch (err: any) {
      if (!requestSeq.isCurrent(reqId)) return;
      if (isAuthError(err)) {
        onAuthError?.();
        return;
      }
      setErrorMessage(err.message || 'Failed to load session details.');
    } finally {
      if (requestSeq.isCurrent(reqId)) {
        setIsLoadingDetail(false);
      }
    }
  }, [token, requestSeq, onAuthError]);

  // External deep-link: open a specific session when requested (e.g. from
  // the Recent Conversations rail). nonce retriggers repeat selections.
  useEffect(() => {
    if (openSessionRequest && token) {
      handleOpenSession(openSessionRequest.sessionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSessionRequest, token]);

  // Delete individual session
  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!token) return;
    if (!window.confirm(`Are you sure you want to delete session ${sessionId}?`)) {
      return;
    }

    setDeletingSessionId(sessionId);
    const reqId = requestSeq.next();
    try {
      await deleteSession(sessionId, token);
      if (!requestSeq.isCurrent(reqId)) return;
      setSuccessMessage(`Session deleted.`);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
        setSessionDetail(null);
      }
      setDeletingSessionId(null);
      await loadSessions();
    } catch (err: any) {
      if (!requestSeq.isCurrent(reqId)) return;
      if (isAuthError(err)) {
        onAuthError?.();
        return;
      }
      setErrorMessage(err.message || 'Failed to delete session.');
    } finally {
      if (requestSeq.isCurrent(reqId)) {
        setDeletingSessionId(null);
      }
    }
  };

  // Delete all my data (Delete-My-Data endpoint)
  const handlePurgeAllData = async () => {
    if (!token) return;
    const reqId = requestSeq.next();
    setIsLoading(true);
    try {
      const resp = await purgeAllHistory(token);
      if (!requestSeq.isCurrent(reqId)) return;
      setSuccessMessage(resp.message || 'All user history successfully deleted.');
      setConfirmPurgeAll(false);
      setSelectedSessionId(null);
      setSessionDetail(null);
      setSessions([]);
    } catch (err: any) {
      // A failed purge must disarm the confirmation so it cannot remain
      // armed for a stray second click.
      setConfirmPurgeAll(false);
      if (!requestSeq.isCurrent(reqId)) return;
      if (isAuthError(err)) {
        onAuthError?.();
        return;
      }
      setErrorMessage(err.message || 'Failed to purge user history.');
    } finally {
      if (requestSeq.isCurrent(reqId)) {
        setIsLoading(false);
      }
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
      <div className="locked-panel">
        <div className="locked-icon">
          <Lock size={22} aria-hidden="true" />
        </div>
        <div>
          <h2 className="history-title" style={{ fontSize: '1.25rem' }}>
            Account Required for History
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem', lineHeight: 1.5 }}>
            Under Phase 9 anonymous sessions are isolated and never persisted. Sign in or create a free local account to store, inspect, and manage your speech turns and conversational history.
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenAuth}
          className="btn btn-primary-solid"
        >
          <Lock size={15} aria-hidden="true" />
          <span>Sign In / Register</span>
        </button>
      </div>
    );
  }

  return (
    <div className="history-page">
      {/* Header Bar */}
      <div className="history-head">
        <div>
          <h2 className="history-title">Conversational History</h2>
          <p className="history-subtitle">
            Persistent sessions and speech turns stored under your account.
          </p>
        </div>

        <div className="history-actions">
          <button
            type="button"
            onClick={loadSessions}
            disabled={isLoading}
            aria-label="Refresh session list"
            className="btn btn-secondary-soft"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} aria-hidden="true" />
            <span>Refresh</span>
          </button>

          {sessions.length > 0 && !confirmPurgeAll && (
            <button
              type="button"
              onClick={() => setConfirmPurgeAll(true)}
              className="btn btn-danger-soft"
            >
              <Trash2 size={14} aria-hidden="true" />
              <span>Delete All My Data</span>
            </button>
          )}

          {confirmPurgeAll && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
              <button
                type="button"
                onClick={handlePurgeAllData}
                disabled={isLoading}
                className="btn btn-danger-solid"
              >
                Confirm Purge All
              </button>
              <button
                type="button"
                onClick={() => setConfirmPurgeAll(false)}
                className="btn btn-secondary-soft"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Notifications */}
      {errorMessage && (
        <div role="alert" className="flash flash-error">
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div role="status" className="flash flash-success">
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
            className="text-btn"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            <span>Back to Sessions List</span>
          </button>

          <div className="detail-card">
            <div className="detail-head">
              <div>
                <div className="detail-id-label">Session ID</div>
                <div className="detail-id-value">{sessionDetail.id}</div>
              </div>
              <div className="detail-side">
                {sessionDetail.primary_language && (
                  <Badge variant="accent">
                    <Globe size={11} style={{ marginRight: '3px' }} aria-hidden="true" />
                    {sessionDetail.primary_language.toUpperCase()}
                  </Badge>
                )}
                <span className="detail-date">
                  {formatDate(sessionDetail.created_at)}
                </span>
              </div>
            </div>

            {/* List of Predictions and Paired Messages */}
            {isLoadingDetail ? (
              <div className="loading-row">
                <Loader2 size={18} className="animate-spin" aria-hidden="true" />
                <span>Loading session details...</span>
              </div>
            ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {sessionDetail.predictions.length === 0 && sessionDetail.messages.length === 0 ? (
                <div className="empty-hint" style={{ padding: '1rem 0' }}>
                  No stored turns found for this session.
                </div>
              ) : (
                sessionDetail.predictions.map((pred, idx) => {
                  const pairedAssistantMsg = sessionDetail.messages.find(
                    (m) => m.prediction_id === pred.id && m.role === 'assistant'
                  );

                  return (
                    <div key={pred.id || idx} className="turn-mini">
                      {/* User Utterance */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <div className="turn-label">
                            <UserIcon size={13} aria-hidden="true" />
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
                              <span className="meta-mono">
                                {Math.round(pred.processing_time_ms)}ms
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="turn-body" style={{ fontSize: '0.95rem', lineHeight: 1.45 }}>
                          {pred.transcript?.text || <span className="empty-hint">-</span>}
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
                          <div className="turn-label assistant" style={{ fontSize: '0.78rem' }}>
                            <Bot size={13} aria-hidden="true" />
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
        <div className="session-list">
          {isLoading ? (
            <div className="loading-row">
              Loading sessions...
            </div>
          ) : sessions.length === 0 ? (
            <div className="empty-state">
              <MessageSquare size={32} className="empty-state-icon" aria-hidden="true" />
              <div className="empty-state-title">
                No saved sessions found
              </div>
              <div className="empty-state-body">
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
                  if (e.repeat) return;
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleOpenSession(sess.id);
                  }
                }}
                className="session-row"
              >
                <div className="session-main">
                  <div className="session-id-row">
                    <span className="mono" style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {sess.id}
                    </span>
                    {sess.primary_language && (
                      <Badge variant="accent">
                        {sess.primary_language.toUpperCase()}
                      </Badge>
                    )}
                  </div>
                  <div className="session-meta">
                    <span className="session-meta-item">
                      <Calendar size={12} aria-hidden="true" />
                      {formatDate(sess.created_at)}
                    </span>
                    <span className="session-meta-item">
                      <MessageSquare size={12} aria-hidden="true" />
                      {sess.turn_count} {sess.turn_count === 1 ? 'turn' : 'turns'}
                    </span>
                  </div>
                </div>

                <div className="session-side">
                  <button
                    type="button"
                    onClick={(e) => handleDeleteSession(sess.id, e)}
                    disabled={deletingSessionId === sess.id}
                    aria-label={`Delete session ${sess.id}`}
                    className="icon-btn danger"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                  <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} aria-hidden="true" />
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

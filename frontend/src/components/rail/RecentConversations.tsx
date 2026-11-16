import React, { useState, useEffect, useCallback } from 'react';
import {
  MessageSquare,
  Globe,
  ChevronRight,
  Lock,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { fetchHistorySessions } from '../../services/api';
import { SessionSummary } from '../../types/history';
import { isAuthError } from '../../lib/httpErrors';
import { Badge } from '../ui/Badge';

export interface RecentConversationsProps {
  token: string | null;
  /** Called when a session row is clicked — parent navigates to detail. */
  onSelectSession: (sessionId: string) => void;
  /** Called by "View All" — parent switches to the Conversations tab. */
  onViewAll: () => void;
  onOpenAuth?: () => void;
  /** Called when a protected request fails with 401/403. */
  onAuthError?: () => void;
}

/** Compact relative-time label for session rows ("5m ago", "2h ago", ...). */
const timeAgo = (isoString: string): string => {
  try {
    const then = new Date(isoString).getTime();
    if (Number.isNaN(then)) return isoString;
    const diffMs = Date.now() - then;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return new Date(isoString).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return isoString;
  }
};

const MAX_VISIBLE = 5;

/**
 * Right-rail "Recent Conversations" panel. Powered entirely by the existing
 * /api/history/sessions endpoint — anonymous users get a sign-in prompt,
 * signed-in users see their real latest sessions.
 */
export const RecentConversations: React.FC<RecentConversationsProps> = ({
  token,
  onSelectSession,
  onViewAll,
  onOpenAuth,
  onAuthError,
}) => {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    if (!token) {
      setSessions([]);
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchHistorySessions(token);
      // Newest activity first; cap the rail to a compact list.
      const sorted = [...data].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      );
      setSessions(sorted.slice(0, MAX_VISIBLE));
    } catch (err: any) {
      if (isAuthError(err)) {
        onAuthError?.();
        return;
      }
      setErrorMessage(err.message || 'Failed to load recent conversations.');
    } finally {
      setIsLoading(false);
    }
  }, [token, onAuthError]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <section className="rail-card" aria-label="Recent conversations">
      <div className="rail-head">
        <h3 className="rail-title">
          <MessageSquare size={15} aria-hidden="true" />
          <span>Recent Conversations</span>
        </h3>
        {token && sessions.length > 0 && (
          <button type="button" className="text-btn" onClick={onViewAll} style={{ fontSize: '0.75rem' }}>
            <span>View all</span>
            <ChevronRight size={13} aria-hidden="true" />
          </button>
        )}
      </div>

      {!token ? (
        <div className="rail-locked">
          <Lock size={18} aria-hidden="true" />
          <p>Sign in to see your conversation history.</p>
          {onOpenAuth && (
            <button type="button" className="btn btn-primary-solid" onClick={onOpenAuth}>
              Sign In
            </button>
          )}
        </div>
      ) : isLoading ? (
        <div className="loading-row" style={{ padding: '1.25rem 0' }}>
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          <span>Loading…</span>
        </div>
      ) : errorMessage ? (
        <div className="flash flash-error" role="alert" style={{ fontSize: '0.78rem' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
            <AlertCircle size={13} aria-hidden="true" />
            {errorMessage}
          </span>
        </div>
      ) : sessions.length === 0 ? (
        <div className="empty-hint" style={{ padding: '0.75rem 0', fontSize: '0.8rem' }}>
          No saved sessions yet — start a conversation while signed in.
        </div>
      ) : (
        <div className="conv-list">
          {sessions.map((sess) => (
            <button
              key={sess.id}
              type="button"
              className="conv-row"
              onClick={() => onSelectSession(sess.id)}
            >
              <span className="conv-icon" aria-hidden="true">
                <MessageSquare size={14} />
              </span>
              <span className="conv-main">
                <span className="conv-top">
                  <span className="conv-id mono">{sess.id}</span>
                  {sess.primary_language && (
                    <Badge variant="accent" style={{ textTransform: 'uppercase', fontSize: '0.62rem', padding: '0.1rem 0.4rem' }}>
                      <Globe size={9} aria-hidden="true" />
                      {sess.primary_language}
                    </Badge>
                  )}
                </span>
                <span className="conv-meta">
                  <span>{timeAgo(sess.updated_at || sess.created_at)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{sess.turn_count} {sess.turn_count === 1 ? 'turn' : 'turns'}</span>
                </span>
              </span>
              <ChevronRight size={15} className="conv-chevron" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </section>
  );
};

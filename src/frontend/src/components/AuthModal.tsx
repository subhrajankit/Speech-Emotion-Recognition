import React, { useState } from 'react';
import { X, ShieldCheck, RefreshCw, CheckCircle2 } from 'lucide-react';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  sessionId: string;
  onNewToken: (token: string, sessionId: string) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  token,
  sessionId,
  onNewToken
}) => {
  const [clientIdInput, setClientIdInput] = useState('web-client');
  const [manualTokenInput, setManualTokenInput] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleGenerateSession = async () => {
    setIsGenerating(true);
    try {
      const host = window.location.hostname || '127.0.0.1';
      const res = await fetch(`http://${host}:8000/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientIdInput, expires_in_minutes: 60 })
      });
      if (res.ok) {
        const data = await res.json();
        onNewToken(data.token, data.session_id);
        setFeedback('New HS256 authenticated session token issued.');
      } else {
        setFeedback('Server returned error issuing token.');
      }
    } catch (err) {
      setFeedback('Failed to reach backend auth endpoint.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleApplyManualToken = () => {
    if (!manualTokenInput.trim()) return;
    onNewToken(manualTokenInput.trim(), `manual_${Date.now().toString(36)}`);
    setFeedback('Manual token attached to connection.');
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <ShieldCheck size={20} style={{ color: 'var(--color-voice)' }} />
            <h3 style={{ fontSize: '1.15rem' }}>Session Authentication</h3>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close modal">
            <X size={16} />
          </button>
        </div>

        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
          SenseAI enforces cryptographic HS256 JWT tokens during WebSocket and WebTransport handshakes.
        </p>

        {/* Current Session Info */}
        <div style={{ background: 'var(--bg-base)', padding: '0.85rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', marginBottom: '1.25rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Active Session ID</div>
          <div className="mono" style={{ fontSize: '0.85rem', color: 'var(--color-signal)' }}>{sessionId || 'Unauthenticated'}</div>
          {token && (
            <div style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: 'var(--text-muted)', wordBreak: 'break-all' }}>
              Token: {token.slice(0, 36)}...
            </div>
          )}
        </div>

        {feedback && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.65rem 0.85rem', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-success)', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem', marginBottom: '1rem' }}>
            <CheckCircle2 size={14} />
            <span>{feedback}</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
              Client Identifier
            </label>
            <input
              type="text"
              className="input-text"
              value={clientIdInput}
              onChange={(e) => setClientIdInput(e.target.value)}
              placeholder="e.g. web-client"
            />
          </div>

          <button className="btn-primary" onClick={handleGenerateSession} disabled={isGenerating}>
            <RefreshCw size={15} className={isGenerating ? 'spin' : ''} />
            <span>Issue New Session Token</span>
          </button>

          <div style={{ textAlign: 'center', fontSize: '0.78rem', color: 'var(--text-muted)', margin: '0.25rem 0' }}>or apply custom JWT</div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              className="input-text"
              value={manualTokenInput}
              onChange={(e) => setManualTokenInput(e.target.value)}
              placeholder="eyJhbGciOiJIUzI1NiIsInR5..."
            />
            <button className="btn-secondary" onClick={handleApplyManualToken}>
              Apply
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

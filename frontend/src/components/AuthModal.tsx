import React, { useState } from 'react';
import { X, Lock, User, UserPlus, LogIn, LogOut, CheckCircle2, AlertCircle, ShieldAlert } from 'lucide-react';
import { loginUser, registerUser, UserResponse } from '../services/api';

export interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string | null;
  currentUser: UserResponse | null;
  onAuthSuccess: (token: string, user: UserResponse) => void;
  onLogout: () => void;
  serverRequiresAuth?: boolean;
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  token,
  currentUser,
  onAuthSuccess,
  onLogout,
  serverRequiresAuth = false,
}) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    const trimmedUser = username.trim();
    if (!trimmedUser || !password) {
      setErrorMessage('Please enter both username and password.');
      return;
    }

    if (mode === 'register' && password !== confirmPassword) {
      setErrorMessage('Passwords do not match.');
      return;
    }

    setIsLoading(true);
    try {
      if (mode === 'register') {
        const registered = await registerUser(trimmedUser, password);
        setSuccessMessage(`Account created for ${registered.username}! Logging in...`);
        // Immediately login
        const loginData = await loginUser(trimmedUser, password);
        onAuthSuccess(loginData.access_token, registered);
        setTimeout(() => {
          onClose();
        }, 800);
      } else {
        const loginData = await loginUser(trimmedUser, password);
        onAuthSuccess(loginData.access_token, {
          id: loginData.user_id,
          username: loginData.username,
          is_active: true,
          created_at: new Date().toISOString(),
        });
        setSuccessMessage(`Signed in as ${loginData.username}`);
        setTimeout(() => {
          onClose();
        }, 500);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogoutClick = () => {
    onLogout();
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setSuccessMessage('Signed out successfully.');
  };

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: '440px',
          width: '92%',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
          padding: '1.75rem',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.4)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--color-voice)',
              }}
            >
              <Lock size={16} />
            </div>
            <h3 id="auth-modal-title" style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>
              {currentUser ? 'User Account' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </h3>
          </div>
          <button
            type="button"
            className="btn-icon"
            onClick={onClose}
            aria-label="Close authentication modal"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '0.3rem',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Server Auth Requirement Note */}
        {serverRequiresAuth && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.6rem 0.85rem',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              color: 'var(--color-danger)',
              fontSize: '0.78rem',
              marginBottom: '1rem',
            }}
          >
            <AlertCircle size={14} style={{ flexShrink: 0 }} />
            <span>This server enforces authentication for all speech sessions.</span>
          </div>
        )}

        {/* Current Authenticated User View */}
        {currentUser && token ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-base)',
                padding: '1rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
                Signed in as
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {currentUser.username}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.4rem', wordBreak: 'break-all' }}>
                Token: {token.slice(0, 20)}...{token.slice(-10)}
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogoutClick}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                padding: '0.65rem 1rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                color: 'var(--color-danger)',
                fontWeight: 600,
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              <LogOut size={16} />
              <span>Sign Out</span>
            </button>
          </div>
        ) : (
          /* Form (Login or Register) */
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {/* Mode Toggle */}
            <div
              role="tablist"
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                backgroundColor: 'var(--bg-base)',
                padding: '3px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'login'}
                onClick={() => {
                  setMode('login');
                  setErrorMessage(null);
                }}
                style={{
                  padding: '0.4rem',
                  fontSize: '0.82rem',
                  fontWeight: mode === 'login' ? 600 : 400,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: mode === 'login' ? 'var(--color-voice)' : 'transparent',
                  color: mode === 'login' ? '#FFFFFF' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                Sign In
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'register'}
                onClick={() => {
                  setMode('register');
                  setErrorMessage(null);
                }}
                style={{
                  padding: '0.4rem',
                  fontSize: '0.82rem',
                  fontWeight: mode === 'register' ? 600 : 400,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: mode === 'register' ? 'var(--color-voice)' : 'transparent',
                  color: mode === 'register' ? '#FFFFFF' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                Register
              </button>
            </div>

            {/* Error / Success Feedback */}
            {errorMessage && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.6rem 0.8rem',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                  color: 'var(--color-danger)',
                  fontSize: '0.8rem',
                }}
              >
                <AlertCircle size={14} style={{ flexShrink: 0 }} />
                <span>{errorMessage}</span>
              </div>
            )}
            {successMessage && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.6rem 0.8rem',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                  color: 'var(--color-success)',
                  fontSize: '0.8rem',
                }}
              >
                <CheckCircle2 size={14} style={{ flexShrink: 0 }} />
                <span>{successMessage}</span>
              </div>
            )}

            {/* Username Input */}
            <div>
              <label
                htmlFor="auth-username-input"
                style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}
              >
                Username
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="auth-username-input"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. subhrajit"
                  style={{
                    width: '100%',
                    padding: '0.6rem 0.85rem 0.6rem 2.2rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-base)',
                    color: 'var(--text-primary)',
                    fontSize: '0.88rem',
                    boxSizing: 'border-box',
                  }}
                />
                <User
                  size={15}
                  style={{
                    position: 'absolute',
                    left: '0.75rem',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--text-muted)',
                  }}
                />
              </div>
            </div>

            {/* Password Input */}
            <div>
              <label
                htmlFor="auth-password-input"
                style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}
              >
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="auth-password-input"
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '0.6rem 0.85rem 0.6rem 2.2rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-base)',
                    color: 'var(--text-primary)',
                    fontSize: '0.88rem',
                    boxSizing: 'border-box',
                  }}
                />
                <Lock
                  size={15}
                  style={{
                    position: 'absolute',
                    left: '0.75rem',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--text-muted)',
                  }}
                />
              </div>
            </div>

            {/* Confirm Password (Register mode only) */}
            {mode === 'register' && (
              <div>
                <label
                  htmlFor="auth-confirm-password-input"
                  style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}
                >
                  Confirm Password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    id="auth-confirm-password-input"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    style={{
                      width: '100%',
                      padding: '0.6rem 0.85rem 0.6rem 2.2rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-subtle)',
                      backgroundColor: 'var(--bg-base)',
                      color: 'var(--text-primary)',
                      fontSize: '0.88rem',
                      boxSizing: 'border-box',
                    }}
                  />
                  <Lock
                    size={15}
                    style={{
                      position: 'absolute',
                      left: '0.75rem',
                      top: '50%',
                      transform: 'translateY(-50%)',
                    }}
                  />
                </div>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                padding: '0.65rem 1rem',
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                backgroundColor: 'var(--color-voice)',
                color: '#FFFFFF',
                fontWeight: 600,
                fontSize: '0.88rem',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                marginTop: '0.35rem',
              }}
            >
              {isLoading ? (
                <span>Processing...</span>
              ) : mode === 'login' ? (
                <>
                  <LogIn size={16} />
                  <span>Sign In</span>
                </>
              ) : (
                <>
                  <UserPlus size={16} />
                  <span>Register Account</span>
                </>
              )}
            </button>
          </form>
        )}

        {/* Security / XSS Tradeoff Note per Requirement 7 */}
        <div
          style={{
            marginTop: '1.25rem',
            paddingTop: '1rem',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.5rem',
            fontSize: '0.72rem',
            color: 'var(--text-muted)',
            lineHeight: 1.45,
          }}
        >
          <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: '2px', color: 'var(--color-signal)' }} />
          <span>
            <strong>XSS Protection Note:</strong> Token is held strictly in-memory. It is never stored in `localStorage` or `sessionStorage` to eliminate cross-site scripting token theft. Reloading the page clears memory and requires signing in again.
          </span>
        </div>
      </div>
    </div>
  );
};

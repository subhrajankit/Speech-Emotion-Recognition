import React, { useEffect, useRef, useState } from 'react';
import { X, Lock, User, UserPlus, LogIn, LogOut, CheckCircle2, AlertCircle, ShieldAlert } from 'lucide-react';
import { loginUser, registerUser, UserResponse } from '../services/api';
import { collectFocusable, isRestorable, nextFocusIndex } from '../lib/focusTrap';

export interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string | null;
  currentUser: UserResponse | null;
  onAuthSuccess: (token: string, user: UserResponse) => void;
  onLogout: () => void;
  serverRequiresAuth?: boolean;
}

export interface AuthFeedbackProps {
  tone: 'error' | 'success';
  children: React.ReactNode;
}

export const AuthFeedback: React.FC<AuthFeedbackProps> = ({ tone, children }) => {
  const isError = tone === 'error';
  return (
    <div
      role={isError ? 'alert' : 'status'}
      className={isError ? 'flash flash-error' : 'flash flash-success'}
      style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
    >
      {isError ? (
        <AlertCircle size={14} style={{ flexShrink: 0 }} aria-hidden="true" />
      ) : (
        <CheckCircle2 size={14} style={{ flexShrink: 0 }} aria-hidden="true" />
      )}
      <span>{children}</span>
    </div>
  );
};

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

  const cardRef = useRef<HTMLDivElement>(null);
  const prevFocusRef = useRef<HTMLElement | null>(null);
  const openSessionRef = useRef(0);
  const wasOpenRef = useRef(false);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Focus management: on open, move focus into the dialog (username input
  // preferred); on close, restore focus to the previously focused element
  // unless the user has deliberately focused something else.
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      openSessionRef.current += 1;
      prevFocusRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const root = cardRef.current;
      const target =
        root?.querySelector<HTMLElement>('#auth-username-input') ??
        (root ? collectFocusable(root)[0] : null) ??
        root;
      target?.focus();
    } else if (!isOpen && wasOpenRef.current) {
      const prev = prevFocusRef.current;
      const active = document.activeElement;
      const focusLeftBehind =
        active === document.body ||
        (cardRef.current !== null && cardRef.current.contains(active));
      if (isRestorable(prev) && focusLeftBehind) {
        prev.focus();
      }
    }
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  // Clean up any pending auto-close timer on unmount.
  useEffect(
    () => () => {
      if (closeTimerRef.current !== null) clearTimeout(closeTimerRef.current);
    },
    []
  );

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

    if (mode === 'register') {
      if (trimmedUser.length < 3) {
        setErrorMessage('Username must be at least 3 characters.');
        return;
      }
      if (password.length < 6) {
        setErrorMessage('Password must be at least 6 characters.');
        return;
      }
      if (password !== confirmPassword) {
        setErrorMessage('Passwords do not match.');
        return;
      }
    }

    setIsLoading(true);
    // Capture the open-session id so a delayed auto-close cannot dismiss a
    // newer modal session if this one was closed and reopened mid-request.
    const session = openSessionRef.current;
    const scheduleAutoClose = (delayMs: number) => {
      if (closeTimerRef.current !== null) clearTimeout(closeTimerRef.current);
      closeTimerRef.current = setTimeout(() => {
        closeTimerRef.current = null;
        if (openSessionRef.current === session) onClose();
      }, delayMs);
    };
    try {
      if (mode === 'register') {
        const registered = await registerUser(trimmedUser, password);
        setSuccessMessage(`Account created for ${registered.username}! Logging in...`);
        // Immediately login
        const loginData = await loginUser(trimmedUser, password);
        onAuthSuccess(loginData.access_token, registered);
        scheduleAutoClose(800);
      } else {
        const loginData = await loginUser(trimmedUser, password);
        onAuthSuccess(loginData.access_token, {
          id: loginData.user_id,
          username: loginData.username,
          is_active: true,
          created_at: new Date().toISOString(),
        });
        setSuccessMessage(`Signed in as ${loginData.username}`);
        scheduleAutoClose(500);
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

  const handleModalKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab') return;
    const root = cardRef.current;
    if (!root) return;
    const items = collectFocusable(root);
    if (items.length === 0) {
      e.preventDefault();
      root.focus();
      return;
    }
    const current = items.indexOf(document.activeElement as HTMLElement);
    const next = nextFocusIndex(current, items.length, e.shiftKey);
    e.preventDefault();
    items[next]?.focus();
  };

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      onKeyDown={handleModalKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div
        ref={cardRef}
        tabIndex={-1}
        className="modal-card auth-card"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="auth-head">
          <div className="auth-title-wrap">
            <div className="auth-icon">
              <Lock size={16} aria-hidden="true" />
            </div>
            <h3 id="auth-modal-title" className="auth-title">
              {currentUser ? 'User Account' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close authentication modal"
            className="auth-close"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* Server Auth Requirement Note */}
        {serverRequiresAuth && (
          <div className="auth-note">
            <AlertCircle size={14} style={{ flexShrink: 0 }} aria-hidden="true" />
            <span>This server enforces authentication for all speech sessions.</span>
          </div>
        )}

        {/* Current Authenticated User View */}
        {currentUser && token ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="user-card">
              <div className="user-card-label">
                Signed in as
              </div>
              <div className="user-card-name">
                {currentUser.username}
              </div>
              <div className="user-card-token">
                Token: {token.slice(0, 20)}...{token.slice(-10)}
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogoutClick}
              className="btn btn-danger-soft btn-block"
            >
              <LogOut size={16} aria-hidden="true" />
              <span>Sign Out</span>
            </button>
          </div>
        ) : (
          /* Form (Login or Register) */
          <form onSubmit={handleSubmit} className="auth-form">
            {/* Mode Toggle */}
            <div
              role="group"
              aria-label="Account mode"
              className="seg-control"
              style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', width: '100%' }}
            >
              <button
                type="button"
                aria-pressed={mode === 'login'}
                onClick={() => {
                  setMode('login');
                  setErrorMessage(null);
                }}
                className={`seg-btn ${mode === 'login' ? 'active' : ''}`}
                style={{ width: '100%' }}
              >
                Sign In
              </button>
              <button
                type="button"
                aria-pressed={mode === 'register'}
                onClick={() => {
                  setMode('register');
                  setErrorMessage(null);
                }}
                className={`seg-btn ${mode === 'register' ? 'active' : ''}`}
                style={{ width: '100%' }}
              >
                Register
              </button>
            </div>

            {/* Error / Success Feedback */}
            {errorMessage && <AuthFeedback tone="error">{errorMessage}</AuthFeedback>}
            {successMessage && <AuthFeedback tone="success">{successMessage}</AuthFeedback>}

            {/* Username Input */}
            <div className="field">
              <label
                htmlFor="auth-username-input"
                className="field-label"
              >
                Username
              </label>
              <div className="input-wrap">
                <input
                  id="auth-username-input"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. subhrajit"
                  className="input-text input-with-icon"
                />
                <User size={15} aria-hidden="true" />
              </div>
            </div>

            {/* Password Input */}
            <div className="field">
              <label
                htmlFor="auth-password-input"
                className="field-label"
              >
                Password
              </label>
              <div className="input-wrap">
                <input
                  id="auth-password-input"
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="input-text input-with-icon"
                />
                <Lock size={15} aria-hidden="true" />
              </div>
            </div>

            {/* Confirm Password (Register mode only) */}
            {mode === 'register' && (
              <div className="field">
                <label
                  htmlFor="auth-confirm-password-input"
                  className="field-label"
                >
                  Confirm Password
                </label>
                <div className="input-wrap">
                  <input
                    id="auth-confirm-password-input"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className="input-text input-with-icon"
                  />
                  <Lock size={15} aria-hidden="true" />
                </div>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="btn btn-primary-solid btn-block"
              style={{ marginTop: '0.35rem' }}
            >
              {isLoading ? (
                <span>Processing...</span>
              ) : mode === 'login' ? (
                <>
                  <LogIn size={16} aria-hidden="true" />
                  <span>Sign In</span>
                </>
              ) : (
                <>
                  <UserPlus size={16} aria-hidden="true" />
                  <span>Register Account</span>
                </>
              )}
            </button>
          </form>
        )}

        {/* Security / XSS Tradeoff Note per Requirement 7 */}
        <div className="auth-footer">
          <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: '2px', color: 'var(--color-signal)' }} aria-hidden="true" />
          <span>
            <strong>XSS Protection Note:</strong> Token is held strictly in-memory. It is never stored in `localStorage` or `sessionStorage` to eliminate cross-site scripting token theft. Reloading the page clears memory and requires signing in again.
          </span>
        </div>
      </div>
    </div>
  );
};

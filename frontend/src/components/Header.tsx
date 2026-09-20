import React from 'react';
import { Radio, Moon, Sun, ShieldCheck } from 'lucide-react';

export type PageId = 'landing' | 'console' | 'history' | 'documents' | 'analytics' | 'settings';

interface HeaderProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  transportMode: 'webtransport' | 'websocket' | 'connecting';
  isConnected: boolean;
  isDark: boolean;
  onToggleTheme: () => void;
  sessionId: string;
  onOpenAuth: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentPage,
  onNavigate,
  transportMode,
  isConnected,
  isDark,
  onToggleTheme,
  sessionId,
  onOpenAuth,
}) => {
  return (
    <header className="site-header">
      <div className="header-inner">
        <div className="brand-badge" onClick={() => onNavigate('landing')} role="button" tabIndex={0}>
          <div className="brand-icon">
            <Radio size={18} strokeWidth={2.5} />
          </div>
          <span>SenseAI</span>
        </div>

        <nav aria-label="Main Navigation">
          <ul className="nav-links">
            <li>
              <button
                className={`nav-btn ${currentPage === 'console' ? 'active' : ''}`}
                onClick={() => onNavigate('console')}
              >
                Console
              </button>
            </li>
            <li>
              <button
                className={`nav-btn ${currentPage === 'history' ? 'active' : ''}`}
                onClick={() => onNavigate('history')}
              >
                History
              </button>
            </li>
            <li>
              <button
                className={`nav-btn ${currentPage === 'documents' ? 'active' : ''}`}
                onClick={() => onNavigate('documents')}
              >
                Knowledge
              </button>
            </li>
            <li>
              <button
                className={`nav-btn ${currentPage === 'analytics' ? 'active' : ''}`}
                onClick={() => onNavigate('analytics')}
              >
                Analytics
              </button>
            </li>
            <li>
              <button
                className={`nav-btn ${currentPage === 'settings' ? 'active' : ''}`}
                onClick={() => onNavigate('settings')}
              >
                Settings
              </button>
            </li>
          </ul>
        </nav>

        <div className="header-controls">
          <div className="transport-pill" title={`Active transport connection: ${transportMode} (${isConnected ? 'Connected' : 'Connecting'})`}>
            <span className={`status-dot ${isConnected ? 'online' : ''}`} />
            <span>{transportMode === 'webtransport' ? 'HTTP/3 QUIC' : transportMode === 'websocket' ? 'WSS Online' : 'Connecting...'}</span>
          </div>

          <button
            className="btn-icon"
            onClick={onToggleTheme}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
          >
            {isDark ? <Sun size={17} /> : <Moon size={17} />}
          </button>

          <button
            className="btn-secondary"
            style={{ padding: '0.4rem 0.85rem', fontSize: '0.82rem', fontFamily: 'var(--font-mono)' }}
            onClick={onOpenAuth}
            title="Manage Session & Auth"
          >
            <ShieldCheck size={14} />
            <span>{sessionId ? sessionId.slice(0, 10) : 'Session Auth'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};

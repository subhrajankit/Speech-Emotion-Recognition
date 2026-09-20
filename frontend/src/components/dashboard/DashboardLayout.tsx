import React from 'react';
import { Radio, Moon, Sun } from 'lucide-react';
import { WebSocketConnectionState } from '../../types/websocket';
import { StatusDot } from '../ui/StatusDot';

export interface DashboardLayoutProps {
  children: React.ReactNode;
  connectionState: WebSocketConnectionState;
  isDark: boolean;
  onToggleTheme: () => void;
  activeTab?: 'voice' | 'history';
  onSelectTab?: (tab: 'voice' | 'history') => void;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  children,
  connectionState,
  isDark,
  onToggleTheme,
  activeTab = 'voice',
  onSelectTab,
}) => {
  const getConnectionLabel = () => {
    switch (connectionState) {
      case 'connected':
        return 'Connected (WebSocket v1)';
      case 'connecting':
        return 'Connecting...';
      case 'reconnecting':
        return 'Reconnecting...';
      case 'error':
        return 'Connection Error';
      case 'disconnected':
      default:
        return 'Disconnected';
    }
  };

  return (
    <div className="app-wrapper">
      {/* Top Header */}
      <header
        style={{
          borderBottom: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-surface)',
          padding: '0.85rem 1.5rem',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}
      >
        <div
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
          }}
        >
          {/* Brand Logo & Name */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div
              style={{
                width: '34px',
                height: '34px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--color-voice)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#FFFFFF',
                boxShadow: '0 2px 8px var(--color-voice-glow)',
              }}
            >
              <Radio size={20} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0, lineHeight: 1.2 }}>
                VoiceSense AI
              </h1>
              <p style={{ fontSize: '0.75rem', margin: 0, color: 'var(--text-muted)' }}>
                Multilingual Speech &amp; Emotion Assistant
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          {onSelectTab && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                backgroundColor: 'var(--bg-surface-elevated)',
                padding: '0.2rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <button
                type="button"
                onClick={() => onSelectTab('voice')}
                style={{
                  padding: '0.35rem 0.85rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  borderRadius: 'var(--radius-sm)',
                  border: 'none',
                  cursor: 'pointer',
                  backgroundColor: activeTab === 'voice' ? 'var(--color-voice)' : 'transparent',
                  color: activeTab === 'voice' ? '#FFFFFF' : 'var(--text-secondary)',
                  transition: 'all 0.15s ease',
                }}
              >
                Voice Console
              </button>
              <button
                type="button"
                onClick={() => onSelectTab('history')}
                style={{
                  padding: '0.35rem 0.85rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  borderRadius: 'var(--radius-sm)',
                  border: 'none',
                  cursor: 'pointer',
                  backgroundColor: activeTab === 'history' ? 'var(--color-voice)' : 'transparent',
                  color: activeTab === 'history' ? '#FFFFFF' : 'var(--text-secondary)',
                  transition: 'all 0.15s ease',
                }}
              >
                History
              </button>
            </div>
          )}

          {/* Connection Status & Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.45rem',
                fontSize: '0.8rem',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-surface-elevated)',
                padding: '0.35rem 0.75rem',
                borderRadius: 'var(--radius-full)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <StatusDot status={connectionState} size={8} pulse={connectionState === 'connecting' || connectionState === 'reconnecting'} />
              <span>{getConnectionLabel()}</span>
            </div>

            <button
              type="button"
              onClick={onToggleTheme}
              aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '34px',
                height: '34px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-surface-elevated)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              {isDark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        {children}
      </main>
    </div>
  );
};

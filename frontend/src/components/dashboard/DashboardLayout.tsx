import React from 'react';
import {
  AudioLines,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Moon,
  Sun,
  User as UserIcon,
  Lock,
} from 'lucide-react';
import { WebSocketConnectionState } from '../../types/websocket';
import { StatusDot } from '../ui/StatusDot';
import { UserResponse } from '../../services/api';

export type DashboardTab = 'voice' | 'history' | 'settings';

export interface DashboardLayoutProps {
  children: React.ReactNode;
  connectionState: WebSocketConnectionState;
  isDark: boolean;
  onToggleTheme: () => void;
  activeTab?: DashboardTab;
  onSelectTab?: (tab: DashboardTab) => void;
  currentUser?: UserResponse | null;
  onOpenAuth?: () => void;
}

const NAV_ITEMS: { id: DashboardTab; label: string; icon: React.ReactNode }[] = [
  { id: 'voice', label: 'Overview', icon: <LayoutDashboard size={18} aria-hidden="true" /> },
  { id: 'history', label: 'Conversations', icon: <MessageSquare size={18} aria-hidden="true" /> },
  { id: 'settings', label: 'Settings', icon: <Settings size={18} aria-hidden="true" /> },
];

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  children,
  connectionState,
  isDark,
  onToggleTheme,
  activeTab = 'voice',
  onSelectTab,
  currentUser,
  onOpenAuth,
}) => {
  const getConnectionLabel = () => {
    switch (connectionState) {
      case 'connected':
        return 'Connected';
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

  const renderNav = (variant: 'sidebar' | 'bottom') => (
    <nav
      className={variant === 'sidebar' ? 'sidebar-nav' : 'bottom-nav'}
      aria-label="Dashboard sections"
    >
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-current={activeTab === item.id ? 'page' : undefined}
          className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
          onClick={() => onSelectTab?.(item.id)}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );

  return (
    <div className="app-shell">
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark" aria-hidden="true">
            <AudioLines size={19} strokeWidth={2.2} />
          </div>
          <div className="brand-text">
            <span className="brand-name">VoiceSense AI</span>
            <span className="brand-tagline">Local voice assistant</span>
          </div>
        </div>

        {renderNav('sidebar')}

        <div className="sidebar-footer">
          <div className="sidebar-status" role="status" title={`WebSocket connection: ${getConnectionLabel()}`}>
            <StatusDot
              status={connectionState}
              size={8}
              pulse={connectionState === 'connecting' || connectionState === 'reconnecting'}
            />
            <span>{getConnectionLabel()}</span>
          </div>

          {onOpenAuth && (
            <button
              type="button"
              onClick={onOpenAuth}
              className="sidebar-user"
              aria-label={currentUser ? `Account: ${currentUser.username}` : 'Sign in or register'}
              style={{ border: 'none', cursor: 'pointer', fontFamily: 'var(--font-main)', width: '100%' }}
            >
              <span className="sidebar-user-icon">
                {currentUser ? <UserIcon size={15} aria-hidden="true" /> : <Lock size={14} aria-hidden="true" />}
              </span>
              <span className="sidebar-user-text">
                <span className="sidebar-user-name">
                  {currentUser ? currentUser.username : 'Guest'}
                </span>
                <span className="sidebar-user-hint">
                  {currentUser ? 'Signed in' : 'Sign in for history'}
                </span>
              </span>
            </button>
          )}

          <div className="sidebar-theme-row">
            <span className="sidebar-theme-label">
              {isDark ? 'Dark theme' : 'Light theme'}
            </span>
            <button
              type="button"
              onClick={onToggleTheme}
              className="theme-toggle"
              aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
              title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {isDark ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="content-shell">
        <main className="main-content content-body">
          {children}
        </main>
      </div>

      {/* Mobile bottom navigation */}
      {renderNav('bottom')}
    </div>
  );
};

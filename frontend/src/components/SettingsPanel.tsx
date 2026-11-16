import React from 'react';
import { Sun, Moon, User as UserIcon, Lock, Settings as SettingsIcon } from 'lucide-react';
import { LanguageSelector, LanguageOption } from './LanguageSelector';
import { UserResponse } from '../services/api';

export interface SettingsPanelProps {
  isDark: boolean;
  onToggleTheme: () => void;
  selectedLanguage: LanguageOption;
  onLanguageChange: (language: LanguageOption, hint: string | null) => void;
  englishOnly?: boolean;
  currentUser?: UserResponse | null;
  onOpenAuth?: () => void;
}

/**
 * Minimal settings view — only surfaces controls that already exist:
 * theme toggle, language selection, and account access. No invented settings.
 */
export const SettingsPanel: React.FC<SettingsPanelProps> = ({
  isDark,
  onToggleTheme,
  selectedLanguage,
  onLanguageChange,
  englishOnly = false,
  currentUser,
  onOpenAuth,
}) => {
  return (
    <div className="dashboard-page" style={{ maxWidth: '720px' }}>
      <div>
        <h2 className="history-title">Settings</h2>
        <p className="history-subtitle">
          Appearance, language and account preferences.
        </p>
      </div>

      {/* Appearance */}
      <section className="surface-card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        <div className="card-title" style={{ fontSize: '0.95rem' }}>
          <Sun size={16} style={{ color: 'var(--color-energy)' }} aria-hidden="true" />
          <span>Appearance</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
              {isDark ? 'Dark theme' : 'Light theme'}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
              {isDark
                ? 'Deep navy premium theme — matches your system or chosen preference.'
                : 'Clean light theme for daytime use.'}
            </div>
          </div>
          <button
            type="button"
            onClick={onToggleTheme}
            className="btn btn-secondary-soft"
            aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            {isDark ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
            <span>{isDark ? 'Switch to Light' : 'Switch to Dark'}</span>
          </button>
        </div>
      </section>

      {/* Speech Language */}
      <section className="surface-card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        <div className="card-title" style={{ fontSize: '0.95rem' }}>
          <SettingsIcon size={16} style={{ color: 'var(--color-voice)' }} aria-hidden="true" />
          <span>Speech Language</span>
        </div>
        <LanguageSelector
          selectedLanguage={selectedLanguage}
          onChange={onLanguageChange}
          englishOnly={englishOnly}
        />
      </section>

      {/* Account */}
      <section className="surface-card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        <div className="card-title" style={{ fontSize: '0.95rem' }}>
          <UserIcon size={16} style={{ color: 'var(--color-purple)' }} aria-hidden="true" />
          <span>Account</span>
        </div>
        {currentUser ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
                {currentUser.username}
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                Signed in — conversation history is persisted to your account.
              </div>
            </div>
            {onOpenAuth && (
              <button type="button" onClick={onOpenAuth} className="btn btn-secondary-soft">
                Manage Account
              </button>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Lock size={14} style={{ color: 'var(--text-muted)' }} aria-hidden="true" />
              <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                Not signed in — history stays session-only.
              </span>
            </div>
            {onOpenAuth && (
              <button type="button" onClick={onOpenAuth} className="btn btn-primary-solid">
                Sign In / Register
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
};

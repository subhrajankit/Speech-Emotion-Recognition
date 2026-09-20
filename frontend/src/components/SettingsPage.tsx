import React, { useState } from 'react';
import { Cpu, Shield, Globe, Trash2, CheckCircle2 } from 'lucide-react';

interface SettingsPageProps {
  llmProvider: string;
  onSelectProvider: (provider: string) => void;
  geminiApiKey: string;
  onSaveGeminiKey: (key: string) => void;
  preferredLanguage: string;
  onSelectLanguage: (lang: string) => void;
  silenceTimeoutMs: number;
  onChangeSilenceTimeout: (val: number) => void;
  onPurgeData: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  llmProvider,
  onSelectProvider,
  geminiApiKey,
  onSaveGeminiKey,
  preferredLanguage,
  onSelectLanguage,
  silenceTimeoutMs,
  onChangeSilenceTimeout,
  onPurgeData,
}) => {
  const [apiKeyInput, setApiKeyInput] = useState(geminiApiKey);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const handleSaveKey = () => {
    onSaveGeminiKey(apiKeyInput);
    setSaveStatus('API key updated.');
    setTimeout(() => setSaveStatus(null), 3000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '820px', margin: '0 auto' }}>
      {/* Header */}
      <div>
        <h2>System & Voice Settings</h2>
        <p style={{ fontSize: '0.9rem', marginTop: '0.25rem' }}>
          Configure inference model providers, acoustic detection thresholds, and privacy rules.
        </p>
      </div>

      {/* Model Provider Section */}
      <div className="panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Cpu size={18} style={{ color: 'var(--color-voice)' }} />
          <h3 style={{ fontSize: '1.05rem' }}>Intelligence & Model Provider</h3>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
          <div
            onClick={() => onSelectProvider('local')}
            style={{
              padding: '1.25rem',
              borderRadius: 'var(--radius-sm)',
              border: llmProvider === 'local' ? '2px solid var(--color-voice)' : '1px solid var(--border-subtle)',
              background: llmProvider === 'local' ? 'var(--color-voice-glow)' : 'var(--bg-base)',
              cursor: 'pointer'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Local Qwen3-1.7B</span>
              {llmProvider === 'local' && <CheckCircle2 size={16} style={{ color: 'var(--color-voice)' }} />}
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              100% private, quantized Q4_K_M running on local device with zero cloud transmission.
            </p>
          </div>

          <div
            onClick={() => onSelectProvider('cloud')}
            style={{
              padding: '1.25rem',
              borderRadius: 'var(--radius-sm)',
              border: llmProvider === 'cloud' ? '2px solid var(--color-energy)' : '1px solid var(--border-subtle)',
              background: llmProvider === 'cloud' ? 'rgba(245, 158, 11, 0.12)' : 'var(--bg-base)',
              cursor: 'pointer'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Google Gemini 3 Flash</span>
              {llmProvider === 'cloud' && <CheckCircle2 size={16} style={{ color: 'var(--color-energy)' }} />}
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Cloud comparison mode via Google AI Studio API for testing latency and frontier reasoning.
            </p>
          </div>
        </div>

        {/* Gemini API Key input if cloud is selected */}
        {llmProvider === 'cloud' && (
          <div style={{ padding: '1rem', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
            <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              Google AI Studio Gemini API Key
            </label>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                type="password"
                className="input-text"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="AIzaSy..."
              />
              <button className="btn-primary" onClick={handleSaveKey}>
                Save Key
              </button>
            </div>
            {saveStatus && (
              <span style={{ fontSize: '0.8rem', color: 'var(--color-success)', marginTop: '0.35rem', display: 'inline-block' }}>
                {saveStatus}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Language & Acoustics */}
      <div className="panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Globe size={18} style={{ color: 'var(--color-signal)' }} />
          <h3 style={{ fontSize: '1.05rem' }}>Language & Voice Activity Detection (VAD)</h3>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              Spoken Language Preference
            </label>
            <select
              className="select-input"
              value={preferredLanguage}
              onChange={(e) => onSelectLanguage(e.target.value)}
            >
              <option value="auto">Automatic Language Detection</option>
              <option value="en">English (SenseVoice)</option>
              <option value="hi">Hindi (IndicConformer)</option>
              <option value="hinglish">Hinglish (Mixed Vernacular)</option>
              <option value="bn">Bengali (বাংলা)</option>
              <option value="ta">Tamil (தமிழ்)</option>
              <option value="te">Telugu (తెలుగు)</option>
              <option value="mr">Marathi (मराठी)</option>
            </select>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Silence Timeout</span>
              <span className="mono">{silenceTimeoutMs} ms</span>
            </div>
            <input
              type="range"
              min="300"
              max="1500"
              step="50"
              value={silenceTimeoutMs}
              onChange={(e) => onChangeSilenceTimeout(Number(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--color-voice)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              <span>Fast (300ms)</span>
              <span>Default (700ms)</span>
              <span>Patient (1500ms)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Privacy & Data Management */}
      <div className="panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Shield size={18} style={{ color: 'var(--color-energy)' }} />
          <h3 style={{ fontSize: '1.05rem' }}>Data Retention & Privacy Controls</h3>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.25rem' }}>Purge Conversation Records</div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', maxWidth: '480px' }}>
              Permanently deletes all encrypted transcripts and emotion logs from the local database. Raw audio is never persisted.
            </p>
          </div>

          <button className="btn-secondary" style={{ color: 'var(--color-danger)' }} onClick={onPurgeData}>
            <Trash2 size={15} />
            <span>Purge All Records</span>
          </button>
        </div>
      </div>
    </div>
  );
};

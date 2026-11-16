import React from 'react';
import { RefreshCw, Activity, Server, AlertTriangle } from 'lucide-react';
import { HealthResponse, ComponentStatus } from '../../types/speech';
import { StatusDot } from '../ui/StatusDot';

export interface ServiceStatusCardProps {
  health: HealthResponse;
  isBackendReachable: boolean;
  isLoading: boolean;
  onRefresh: () => void;
  className?: string;
}

const COMPONENT_LABELS: Record<string, { label: string; description: string }> = {
  asr: { label: 'ASR Engine', description: 'SenseVoice perception' },
  emotion: { label: 'Emotion Recognition', description: 'Acoustic SER analysis' },
  llm: { label: 'LLM Reasoning', description: 'Local Qwen3 inference' },
  rag: { label: 'Knowledge RAG', description: 'Vector retrieval & FAISS' },
  tts: { label: 'Speech Synthesis', description: 'Indic Parler-TTS' },
  db: { label: 'Database & Storage', description: 'Session & transcript store' },
};

export const ServiceStatusCard: React.FC<ServiceStatusCardProps> = ({
  health,
  isBackendReachable,
  isLoading,
  onRefresh,
  className = '',
}) => {
  const getStatusBadgeStyle = (status: ComponentStatus) => {
    switch (status) {
      case 'ok':
        return { bg: 'color-mix(in srgb, var(--color-success) 12%, transparent)', border: 'color-mix(in srgb, var(--color-success) 30%, transparent)', text: 'var(--color-success)', label: 'Operational' };
      case 'degraded':
        return { bg: 'color-mix(in srgb, var(--color-energy) 12%, transparent)', border: 'color-mix(in srgb, var(--color-energy) 30%, transparent)', text: 'var(--color-energy)', label: 'Degraded' };
      case 'unhealthy':
      case 'offline':
        return { bg: 'color-mix(in srgb, var(--color-danger) 12%, transparent)', border: 'color-mix(in srgb, var(--color-danger) 30%, transparent)', text: 'var(--color-danger)', label: 'Offline' };
      case 'not_configured':
      default:
        return { bg: 'var(--bg-surface-hover)', border: 'var(--border-subtle)', text: 'var(--text-muted)', label: 'Not Configured' };
    }
  };

  return (
    <div
      className={`surface-card ${className}`}
      style={{
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
    >
      <div className="card-head">
        <div className="card-title">
          <Activity size={18} style={{ color: 'var(--color-signal)' }} aria-hidden="true" />
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
            Service Subsystems
          </h3>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', color: isBackendReachable ? 'var(--color-success)' : 'var(--color-danger)' }}>
            <StatusDot status={isBackendReachable ? 'ok' : 'unhealthy'} size={7} />
            {isBackendReachable ? 'Backend Online' : 'Backend Down'}
          </span>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="Refresh service health status"
          className="btn btn-secondary-soft"
          style={{ padding: '0.3rem 0.7rem', fontSize: '0.78rem' }}
        >
          <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {!isBackendReachable && (
        <div className="notice notice-warning" style={{ fontSize: '0.8rem' }} role="alert">
          <AlertTriangle size={15} className="notice-icon" aria-hidden="true" />
          <span>Backend at {health.details?.message || '127.0.0.1:8000'} is unreachable. Ensure the FastAPI server is running.</span>
        </div>
      )}

      <div className="subsystem-grid">
        {Object.entries(health.components).map(([key, status]) => {
          const info = COMPONENT_LABELS[key] || { label: key.toUpperCase(), description: '' };
          const badgeStyle = getStatusBadgeStyle(status);

          return (
            <div key={key} className="subsystem-tile">
              <div className="subsystem-top">
                <span className="subsystem-name">
                  {info.label}
                </span>
                <StatusDot status={status} size={7} />
              </div>

              <div className="subsystem-desc">
                {info.description}
              </div>

              <div>
                <span
                  className="status-pill-tag"
                  style={{
                    backgroundColor: badgeStyle.bg,
                    borderColor: badgeStyle.border,
                    color: badgeStyle.text,
                  }}
                >
                  {badgeStyle.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {health.details?.model_version && (
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Server size={13} aria-hidden="true" />
          <span>Active Engine: <strong style={{ color: 'var(--text-secondary)' }}>{health.details.model_version}</strong></span>
        </div>
      )}
    </div>
  );
};

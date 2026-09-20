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
        return { bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.3)', text: 'var(--color-success)', label: 'Operational' };
      case 'degraded':
        return { bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.3)', text: 'var(--color-energy)', label: 'Degraded' };
      case 'unhealthy':
      case 'offline':
        return { bg: 'rgba(239, 68, 68, 0.12)', border: 'rgba(239, 68, 68, 0.3)', text: 'var(--color-danger)', label: 'Offline' };
      case 'not_configured':
      default:
        return { bg: 'var(--bg-surface-hover)', border: 'var(--border-subtle)', text: 'var(--text-muted)', label: 'Not Configured' };
    }
  };

  return (
    <div
      className={`panel ${className}`}
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Activity size={18} style={{ color: 'var(--color-signal)' }} />
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
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
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.35rem',
            background: 'transparent',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-secondary)',
            padding: '0.25rem 0.6rem',
            fontSize: '0.78rem',
            cursor: isLoading ? 'not-allowed' : 'pointer',
          }}
        >
          <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {!isBackendReachable && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.6rem 0.8rem',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.8rem',
            color: 'var(--color-danger)',
          }}
        >
          <AlertTriangle size={15} />
          <span>Backend at {health.details?.message || '127.0.0.1:8000'} is unreachable. Ensure the FastAPI server is running.</span>
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: '0.75rem',
        }}
      >
        {Object.entries(health.components).map(([key, status]) => {
          const info = COMPONENT_LABELS[key] || { label: key.toUpperCase(), description: '' };
          const badgeStyle = getStatusBadgeStyle(status);

          return (
            <div
              key={key}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.35rem',
                padding: '0.75rem',
                backgroundColor: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {info.label}
                </span>
                <StatusDot status={status} size={7} />
              </div>

              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                {info.description}
              </div>

              <div style={{ marginTop: '0.25rem' }}>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '0.15rem 0.45rem',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    backgroundColor: badgeStyle.bg,
                    border: `1px solid ${badgeStyle.border}`,
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
          <Server size={13} />
          <span>Active Engine: <strong style={{ color: 'var(--text-secondary)' }}>{health.details.model_version}</strong></span>
        </div>
      )}
    </div>
  );
};

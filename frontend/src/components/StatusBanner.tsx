import React from 'react';
import { Loader2, Cpu } from 'lucide-react';

export interface StatusBannerProps {
  isLoadingModel: boolean;
  engineName?: string;
}

export const StatusBanner: React.FC<StatusBannerProps> = ({
  isLoadingModel,
  engineName,
}) => {
  if (!isLoadingModel) {
    return null;
  }

  const engineLabel =
    engineName === 'indicconformer'
      ? 'IndicConformer-600m'
      : engineName === 'sensevoice'
      ? 'SenseVoiceSmall'
      : engineName || 'Speech';

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.65rem',
        padding: '0.75rem 1.25rem',
        backgroundColor: 'rgba(245, 158, 11, 0.12)',
        border: '1px solid rgba(245, 158, 11, 0.35)',
        borderRadius: 'var(--radius-md)',
        color: 'var(--text-primary)',
        fontSize: '0.85rem',
        animation: 'pulse 2s infinite ease-in-out',
      }}
    >
      <Loader2 size={16} className="animate-spin" style={{ color: 'var(--color-energy)' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600 }}>
          Loading speech model (first use can take 30 s)...
        </span>
        {engineName && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              backgroundColor: 'var(--bg-surface)',
              padding: '0.1rem 0.4rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.75rem',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <Cpu size={11} />
            {engineLabel}
          </span>
        )}
      </div>
    </div>
  );
};


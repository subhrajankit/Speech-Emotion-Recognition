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
      className="model-loading-banner"
    >
      <Loader2 size={16} className="animate-spin" style={{ color: 'var(--color-energy)', flexShrink: 0 }} aria-hidden="true" />
      <div className="model-loading-inner">
        <span style={{ fontWeight: 600 }}>
          Loading speech model (first use can take 30 s)...
        </span>
        {engineName && (
          <span className="model-engine-chip">
            <Cpu size={11} aria-hidden="true" />
            {engineLabel}
          </span>
        )}
      </div>
    </div>
  );
};

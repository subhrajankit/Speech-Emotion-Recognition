import React from 'react';
import { Clock, Zap } from 'lucide-react';
import { LatencyMetrics } from '../../types/speech';

export interface LatencyCardProps {
  latencies: LatencyMetrics;
  className?: string;
}

export const LatencyCard: React.FC<LatencyCardProps> = ({
  latencies,
  className = '',
}) => {
  const asrMs = latencies.asr_ms ?? 0;
  const totalMs = latencies.total_ms ?? asrMs;

  // Latency budget: ASR budget is 120ms, Total turn budget is 500ms
  const asrPercent = Math.min(100, Math.round((asrMs / 120) * 100));

  return (
    <div
      className={`surface-card ${className}`}
      style={{
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.85rem',
      }}
    >
      <div className="card-head">
        <div className="card-title">
          <Zap size={17} style={{ color: 'var(--color-energy)' }} aria-hidden="true" />
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
            Processing Latency
          </h3>
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Budget: &lt;120ms</span>
      </div>

      <div className="metric-grid">
        <div className="metric-tile">
          <span className="metric-label">ASR Inference</span>
          <div className="metric-value" style={{ color: asrMs > 150 ? 'var(--color-danger)' : 'var(--color-voice)' }}>
            {asrMs > 0 ? `${asrMs}ms` : '—'}
          </div>
          <div className="metric-bar">
            <div
              className="metric-bar-fill"
              style={{
                width: `${asrPercent}%`,
                backgroundColor: asrPercent > 100 ? 'var(--color-danger)' : 'var(--color-voice)',
              }}
            />
          </div>
        </div>

        <div className="metric-tile">
          <span className="metric-label">Total Turn Duration</span>
          <div className="metric-value" style={{ color: totalMs > 500 ? 'var(--color-energy)' : 'var(--color-success)' }}>
            {totalMs > 0 ? `${totalMs}ms` : '—'}
          </div>
          <div className="metric-foot">
            <Clock size={11} aria-hidden="true" />
            <span>End-to-end perception</span>
          </div>
        </div>
      </div>
    </div>
  );
};

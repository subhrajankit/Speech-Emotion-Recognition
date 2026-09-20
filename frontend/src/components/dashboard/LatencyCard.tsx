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
      className={`panel ${className}`}
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.85rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Zap size={17} style={{ color: 'var(--color-energy)' }} />
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Processing Latency
          </h3>
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Budget: &lt;120ms</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
        <div
          style={{
            padding: '0.75rem',
            backgroundColor: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.25rem',
          }}
        >
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>ASR Inference</span>
          <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 700, color: asrMs > 150 ? 'var(--color-danger)' : 'var(--color-voice)' }}>
            {asrMs > 0 ? `${asrMs}ms` : '—'}
          </div>
          <div
            style={{
              width: '100%',
              height: '4px',
              backgroundColor: 'var(--bg-surface-hover)',
              borderRadius: '2px',
              overflow: 'hidden',
              marginTop: '4px',
            }}
          >
            <div
              style={{
                width: `${asrPercent}%`,
                height: '100%',
                backgroundColor: asrPercent > 100 ? 'var(--color-danger)' : 'var(--color-voice)',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
        </div>

        <div
          style={{
            padding: '0.75rem',
            backgroundColor: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.25rem',
          }}
        >
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Total Turn Duration</span>
          <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 700, color: totalMs > 500 ? 'var(--color-energy)' : 'var(--color-success)' }}>
            {totalMs > 0 ? `${totalMs}ms` : '—'}
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              fontSize: '0.68rem',
              color: 'var(--text-muted)',
              marginTop: '4px',
            }}
          >
            <Clock size={11} />
            <span>End-to-end perception</span>
          </div>
        </div>
      </div>
    </div>
  );
};

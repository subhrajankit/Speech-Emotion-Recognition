import React from 'react';
import {
  Wifi,
  Gauge,
  Timer,
  MessageSquare,
  Smile,
  Activity,
} from 'lucide-react';
import { WebSocketConnectionState } from '../../types/websocket';
import { HealthResponse, LatencyMetrics } from '../../types/speech';
import { StatusDot } from '../ui/StatusDot';
import { formatEmotion } from '../../lib/formatters';

export interface InsightsPanelProps {
  connectionState: WebSocketConnectionState;
  latencies: LatencyMetrics;
  /** Turns recorded in the current in-memory session (not lifetime stats). */
  sessionTurns: number;
  latestEmotion?: string | null;
  latestConfidence?: number | null;
  health?: HealthResponse;
  isBackendReachable?: boolean;
  isLoading?: boolean;
}

const CONNECTION_LABELS: Record<WebSocketConnectionState, string> = {
  connected: 'Connected',
  connecting: 'Connecting…',
  reconnecting: 'Reconnecting…',
  error: 'Error',
  disconnected: 'Offline',
};

const dotStatusFor = (state: WebSocketConnectionState) =>
  state === 'connected' ? 'ok' : state === 'error' ? 'unhealthy' : 'degraded';

/**
 * Right-rail "Insights" panel — session-scoped metrics only.
 * Everything shown comes from live app state; nothing is invented or
 * presented as lifetime/historical analytics.
 */
export const InsightsPanel: React.FC<InsightsPanelProps> = ({
  connectionState,
  latencies,
  sessionTurns,
  latestEmotion,
  latestConfidence,
  health,
  isBackendReachable,
  isLoading = false,
}) => {
  const asrMs = latencies.asr_ms;
  const totalMs = latencies.total_ms;

  const healthyCount = health
    ? Object.values(health.components).filter((s) => s === 'ok').length
    : null;
  const totalComponents = health ? Object.keys(health.components).length : 0;

  const rows: {
    icon: React.ReactNode;
    label: string;
    value: string;
    hint?: string;
    tone?: 'ok' | 'warn' | 'muted';
  }[] = [
    {
      icon: <Wifi size={14} aria-hidden="true" />,
      label: 'Connection',
      value: CONNECTION_LABELS[connectionState] ?? connectionState,
      tone: connectionState === 'connected' ? 'ok' : connectionState === 'error' ? 'warn' : 'muted',
    },
    {
      icon: <Gauge size={14} aria-hidden="true" />,
      label: 'ASR latency',
      value: asrMs !== undefined && asrMs > 0 ? `${Math.round(asrMs)} ms` : '—',
      hint: 'last turn',
    },
    {
      icon: <Timer size={14} aria-hidden="true" />,
      label: 'Turn duration',
      value: totalMs !== undefined && totalMs > 0 ? `${Math.round(totalMs)} ms` : '—',
      hint: 'last turn',
    },
    {
      icon: <MessageSquare size={14} aria-hidden="true" />,
      label: 'Session turns',
      value: String(sessionTurns),
      hint: 'this session',
    },
    {
      icon: <Smile size={14} aria-hidden="true" />,
      label: 'Latest emotion',
      value: latestEmotion
        ? `${formatEmotion(latestEmotion)}${
            latestConfidence !== null && latestConfidence !== undefined
              ? ` · ${Math.round(latestConfidence * 100)}%`
              : ''
          }`
        : '—',
      hint: 'this session',
    },
    ...(healthyCount !== null
      ? [
          {
            icon: <Activity size={14} aria-hidden="true" />,
            label: 'Subsystems',
            value: `${healthyCount}/${totalComponents} healthy`,
            hint: isBackendReachable === false ? 'backend unreachable' : undefined,
            tone: (isBackendReachable === false ? 'warn' : 'ok') as 'ok' | 'warn',
          },
        ]
      : []),
  ];

  return (
    <section className="rail-card" aria-label="Session insights">
      <div className="rail-head">
        <h3 className="rail-title">
          <Activity size={15} aria-hidden="true" />
          <span>Insights</span>
        </h3>
        {isLoading && (
          <span className="meta-mono" style={{ fontSize: '0.68rem' }}>updating…</span>
        )}
      </div>

      <div className="insight-list">
        {rows.map((row) => (
          <div key={row.label} className="insight-row">
            <span className="insight-icon" aria-hidden="true">
              {row.icon}
            </span>
            <span className="insight-label">
              {row.label}
              {row.hint && <span className="insight-hint">{row.hint}</span>}
            </span>
            <span
              className={`insight-value ${row.tone === 'warn' ? 'warn' : row.tone === 'ok' ? 'ok' : ''}`}
            >
              {row.label === 'Connection' && (
                <StatusDot status={dotStatusFor(connectionState)} size={7} />
              )}
              {row.value}
            </span>
          </div>
        ))}
      </div>

      <p className="insight-footnote">
        Session-scoped metrics from this browser session — not lifetime statistics.
      </p>
    </section>
  );
};

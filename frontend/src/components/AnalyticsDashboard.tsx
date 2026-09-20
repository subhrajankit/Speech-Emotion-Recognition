import React, { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';

interface StageStats {
  min: number;
  avg: number;
  max: number;
  p95: number;
}

interface BenchmarkSummary {
  count: number;
  stages: Record<string, StageStats>;
}

export interface MetricItem {
  conversation_id?: string;
  transcript?: string;
  intent?: string;
  language?: string;
  audio_received?: string;
  vad: number;
  asr: number;
  emotion: number;
  router: number;
  rag: number;
  llm_ttft: number;
  llm_total: number;
  tts_ttfa: number;
  total: number;
}

interface AnalyticsDashboardProps {
  metrics: MetricItem[];
  summary: BenchmarkSummary | null;
  onRefresh: () => void;
  isRefreshing: boolean;
  onReset: () => void;
}

export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({
  metrics,
  summary,
  onRefresh,
  isRefreshing,
  onReset
}) => {
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      onRefresh();
    }, 4000);
    return () => clearInterval(interval);
  }, [autoRefresh, onRefresh]);

  const stagesBudget = [
    { key: 'vad', label: 'Silero VAD', budget: 15 },
    { key: 'asr', label: 'SenseVoice / Indic ASR', budget: 150 },
    { key: 'emotion', label: 'SER Emotion & Lexicon', budget: 30 },
    { key: 'router', label: 'Intent Gate', budget: 10 },
    { key: 'rag', label: 'FAISS Dense Search', budget: 35 },
    { key: 'llm_ttft', label: 'LLM Time to First Token (TTFT)', budget: 150 },
    { key: 'tts_ttfa', label: 'TTS Time to First Audio (TTFA)', budget: 350 },
    { key: 'total', label: 'End-to-End Voice Turn', budget: 500 },
  ];

  const totalAvg = summary?.stages?.total?.avg || (metrics.length > 0 ? metrics[0].total : 0);
  const ttftAvg = summary?.stages?.llm_ttft?.avg || (metrics.length > 0 ? metrics[0].llm_ttft : 0);
  const ttfaAvg = summary?.stages?.tts_ttfa?.avg || (metrics.length > 0 ? metrics[0].tts_ttfa : 0);
  const totalCount = summary?.count || metrics.length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '1080px', margin: '0 auto' }}>
      {/* Dashboard Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2>Telemetry & Pipeline Benchmarks</h2>
          <p style={{ fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Empirical latency measurements captured across all pipeline stages.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (4s)
          </label>

          <button className="btn-secondary" onClick={onRefresh} disabled={isRefreshing}>
            <RefreshCw size={15} className={isRefreshing ? 'spin' : ''} />
            <span>Refresh</span>
          </button>

          <button className="btn-secondary" onClick={onReset} style={{ color: 'var(--color-danger)' }}>
            <span>Clear Metrics</span>
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        <div className="panel" style={{ padding: '1.25rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Average Total Turn</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: totalAvg > 500 ? 'var(--color-energy)' : 'var(--color-success)' }}>
            {totalAvg ? `${totalAvg.toFixed(1)} ms` : '--'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>P95 SLA: &lt; 500 ms</div>
        </div>

        <div className="panel" style={{ padding: '1.25rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Average LLM TTFT</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--color-voice)' }}>
            {ttftAvg ? `${ttftAvg.toFixed(1)} ms` : '--'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Target: &lt; 150 ms</div>
        </div>

        <div className="panel" style={{ padding: '1.25rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Average TTS TTFA</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--color-signal)' }}>
            {ttfaAvg ? `${ttfaAvg.toFixed(1)} ms` : '--'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>First Audio Chunk SLA: &lt; 350 ms</div>
        </div>

        <div className="panel" style={{ padding: '1.25rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Recorded Utterances</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {totalCount}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Ring buffer capacity: 100 turns</div>
        </div>
      </div>

      {/* Stage Latency vs SLA Budget Chart */}
      <div className="panel">
        <h3 style={{ fontSize: '1.1rem', marginBottom: '1.25rem' }}>Stage Latency vs Target SLA Budget</h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {stagesBudget.map((stage) => {
            const stats = summary?.stages?.[stage.key];
            const avgVal = stats?.avg || 0;
            const p95Val = stats?.p95 || 0;
            const percentage = Math.min(100, (avgVal / stage.budget) * 100);
            const isOverBudget = avgVal > stage.budget;

            return (
              <div key={stage.key}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem', fontSize: '0.85rem' }}>
                  <span>{stage.label}</span>
                  <div className="mono" style={{ fontSize: '0.8rem', color: isOverBudget ? 'var(--color-danger)' : 'var(--text-muted)' }}>
                    <span>Avg: <strong style={{ color: isOverBudget ? 'var(--color-danger)' : 'var(--text-primary)' }}>{avgVal.toFixed(1)}ms</strong></span>
                    <span style={{ margin: '0 0.5rem' }}>·</span>
                    <span>P95: {p95Val.toFixed(1)}ms</span>
                    <span style={{ margin: '0 0.5rem' }}>·</span>
                    <span>Budget: {stage.budget}ms</span>
                  </div>
                </div>

                <div style={{ width: '100%', height: '8px', background: 'var(--bg-base)', borderRadius: 'var(--radius-full)', overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${percentage}%`,
                      backgroundColor: isOverBudget ? 'var(--color-danger)' : stage.key === 'total' ? 'var(--color-success)' : 'var(--color-voice)',
                      borderRadius: 'var(--radius-full)',
                      transition: 'width 0.3s ease'
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recent Requests Data Table */}
      <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-subtle)' }}>
          <h3 style={{ fontSize: '1rem' }}>Recent Voice Turns Telemetry</h3>
        </div>

        {metrics.length === 0 ? (
          <div style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            No telemetry records in memory. Perform a voice turn to capture per-stage latencies.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.82rem' }}>
              <thead>
                <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'uppercase' }}>
                  <th style={{ padding: '0.65rem 1rem' }}>Time</th>
                  <th style={{ padding: '0.65rem 1rem' }}>Intent</th>
                  <th style={{ padding: '0.65rem 0.75rem' }}>VAD</th>
                  <th style={{ padding: '0.65rem 0.75rem' }}>ASR</th>
                  <th style={{ padding: '0.65rem 0.75rem' }}>SER</th>
                  <th style={{ padding: '0.65rem 0.75rem' }}>TTFT</th>
                  <th style={{ padding: '0.65rem 0.75rem' }}>TTFA</th>
                  <th style={{ padding: '0.65rem 1rem' }}>Total</th>
                  <th style={{ padding: '0.65rem 1.25rem' }}>Transcript Preview</th>
                </tr>
              </thead>
              <tbody>
                {metrics.slice(0, 15).map((m, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.65rem 1rem', fontFamily: 'var(--font-mono)' }}>
                      {m.audio_received ? m.audio_received.slice(11, 19) : '--'}
                    </td>
                    <td style={{ padding: '0.65rem 1rem', textTransform: 'capitalize' }}>
                      {m.intent}
                    </td>
                    <td style={{ padding: '0.65rem 0.75rem', fontFamily: 'var(--font-mono)' }}>{m.vad?.toFixed(0)}ms</td>
                    <td style={{ padding: '0.65rem 0.75rem', fontFamily: 'var(--font-mono)' }}>{m.asr?.toFixed(0)}ms</td>
                    <td style={{ padding: '0.65rem 0.75rem', fontFamily: 'var(--font-mono)' }}>{m.emotion?.toFixed(0)}ms</td>
                    <td style={{ padding: '0.65rem 0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--color-voice)' }}>{m.llm_ttft?.toFixed(0)}ms</td>
                    <td style={{ padding: '0.65rem 0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--color-signal)' }}>{m.tts_ttfa?.toFixed(0)}ms</td>
                    <td style={{ padding: '0.65rem 1rem', fontFamily: 'var(--font-mono)', fontWeight: 600, color: m.total > 500 ? 'var(--color-energy)' : 'var(--text-primary)' }}>
                      {m.total?.toFixed(0)}ms
                    </td>
                    <td style={{ padding: '0.65rem 1.25rem', color: 'var(--text-secondary)', maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.transcript || '...'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

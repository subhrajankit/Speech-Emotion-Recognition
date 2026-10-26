import React, { useState } from 'react';
import { Mic, Shield, HeartHandshake, Languages, Sparkles } from 'lucide-react';
import { WaveformVisualizer } from './WaveformVisualizer';

interface LandingPageProps {
  onStartConsole: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onStartConsole }) => {
  const [demoState, setDemoState] = useState<'idle' | 'listening' | 'speaking'>('idle');
  const [activeScenario, setActiveScenario] = useState<number>(0);

  const scenarios = [
    {
      title: 'Empathetic De-escalation',
      prompt: '"I have been trying to resolve this bug for four hours and nothing works."',
      userEmotion: 'Frustrated / High Arousal (-0.6, +0.8)',
      assistantTone: 'Calm, gentle, reassuring voice delivery',
      reply: '"Take a breath. Let\'s step through the pipeline together and pinpoint where the state drops."'
    },
    {
      title: 'Vernacular Code-Switching',
      prompt: '"Mera order abhi tak deliver nahi hua, can you track it?"',
      userEmotion: 'Anxious / Hinglish detection',
      assistantTone: 'Warm natural Hinglish cadence',
      reply: '"Main abhi aapke shipment status ko check karke update deta hoon."'
    },
    {
      title: 'Local Knowledge Grounding',
      prompt: '"What does the company warranty say about water damage?"',
      userEmotion: 'Neutral / Factual RAG lookup',
      assistantTone: 'Concise grounded citation',
      reply: '"Based on warranty_terms.txt: Liquid ingress is covered under tier-2 extended protection."'
    }
  ];

  const handleRunDemo = (idx: number) => {
    setActiveScenario(idx);
    setDemoState('listening');
    setTimeout(() => {
      setDemoState('speaking');
      setTimeout(() => {
        setDemoState('idle');
      }, 4000);
    }, 1500);
  };

  return (
    <div className="landing-container" style={{ display: 'flex', flexDirection: 'column', gap: '3.5rem' }}>
      {/* Hero Section */}
      <section style={{ textAlign: 'center', padding: '2rem 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.5rem' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-surface)', padding: '0.35rem 0.85rem', borderRadius: 'var(--radius-full)', border: '1px solid var(--border-subtle)', fontSize: '0.85rem', color: 'var(--color-signal)' }}>
          <Sparkles size={14} />
          <span>Local Voice Intelligence · Zero Cloud Dependency</span>
        </div>

        <h1 style={{ maxWidth: '800px', fontSize: 'clamp(2rem, 5vw, 3.25rem)', fontWeight: 800 }}>
          Intelligence that listens, feels, and speaks locally.
        </h1>

        <p style={{ maxWidth: '620px', fontSize: '1.1rem', color: 'var(--text-secondary)' }}>
          A private, multilingual voice assistant powered by on-device speech models, acoustic emotion recognition, and sub-500ms streaming speech synthesis.
        </p>

        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', justifyContent: 'center', marginTop: '0.5rem' }}>
          <button className="btn-primary" style={{ padding: '0.8rem 1.8rem', fontSize: '1rem' }} onClick={onStartConsole}>
            <Mic size={18} />
            <span>Open Voice Console</span>
          </button>
        </div>

        {/* Interactive Hero Acoustic Moment */}
        <div className="panel" style={{ width: '100%', maxWidth: '780px', marginTop: '1.5rem', padding: '1.5rem', textAlign: 'left' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Interactive Acoustic Resonance Demo
            </span>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {scenarios.map((s, i) => (
                <button
                  key={i}
                  className={`nav-btn ${activeScenario === i ? 'active' : ''}`}
                  style={{ fontSize: '0.78rem', padding: '0.3rem 0.65rem' }}
                  onClick={() => handleRunDemo(i)}
                >
                  {s.title}
                </button>
              ))}
            </div>
          </div>

          <div style={{ background: 'var(--bg-base)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', marginBottom: '1rem' }}>
            <WaveformVisualizer state={demoState} height={80} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={{ padding: '0.85rem', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>User Spoken Audio</div>
              <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)', fontStyle: 'italic' }}>{scenarios[activeScenario].prompt}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--color-energy)', marginTop: '0.5rem' }}>State: {scenarios[activeScenario].userEmotion}</div>
            </div>

            <div style={{ padding: '0.85rem', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Assistant Speech Response</div>
              <div style={{ fontSize: '0.9rem', color: 'var(--color-signal)' }}>{scenarios[activeScenario].reply}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>Delivery: {scenarios[activeScenario].assistantTone}</div>
            </div>
          </div>
        </div>
      </section>

      {/* Core Architectural Pillars */}
      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
        <div className="panel">
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-sm)', background: 'var(--color-voice-glow)', color: 'var(--color-voice)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <Shield size={22} />
          </div>
          <h3 style={{ marginBottom: '0.5rem' }}>100% Local Privacy</h3>
          <p style={{ fontSize: '0.9rem' }}>
            Your voice audio never leaves your device. Raw PCM buffers are cleared from RAM immediately after transcription. Zero telemetry leakage or unauthorized cloud recording.
          </p>
        </div>

        <div className="panel">
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-sm)', background: 'rgba(245, 158, 11, 0.15)', color: 'var(--color-energy)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <HeartHandshake size={22} />
          </div>
          <h3 style={{ marginBottom: '0.5rem' }}>Acoustic Emotion Awareness</h3>
          <p style={{ fontSize: '0.9rem' }}>
            Blends acoustic SER signals with conversational sentiment to understand your emotional state, modulating vocal speed, pitch, and timbre for empathetic de-escalation.
          </p>
        </div>

        <div className="panel">
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-sm)', background: 'var(--color-signal-glow)', color: 'var(--color-signal)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <Languages size={22} />
          </div>
          <h3 style={{ marginBottom: '0.5rem' }}>Indic Vernacular & Code-Mixing</h3>
          <p style={{ fontSize: '0.9rem' }}>
            Native dual-ASR architecture routing English, Hindi, and 21 official Indian languages with specialized heuristics for spontaneous Hinglish code-switching.
          </p>
        </div>
      </section>
    </div>
  );
};

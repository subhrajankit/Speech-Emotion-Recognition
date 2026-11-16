import React, { useEffect, useRef } from 'react';

export interface WaveformVisualizerProps {
  state: 'idle' | 'listening' | 'thinking' | 'speaking';
  audioLevel?: number; // 0.0 to 1.0
  height?: number;
  className?: string;
}

type VisualState = WaveformVisualizerProps['state'];

// Resolve theme CSS custom properties once per theme change (cached by the
// data-theme attribute value) so canvas colors track dark/light automatically.
let cachedThemeKey: string | null = null;
let cachedPalette: Record<VisualState, string> | null = null;

const FALLBACK_PALETTE: Record<VisualState, string> = {
  idle: '#3B82F6',
  listening: '#06B6D4',
  thinking: '#F59E0B',
  speaking: '#3B82F6',
};

function getStatePalette(): Record<VisualState, string> {
  if (typeof document === 'undefined') return FALLBACK_PALETTE;
  const themeKey = document.documentElement.getAttribute('data-theme') || 'dark';
  if (cachedPalette && cachedThemeKey === themeKey) return cachedPalette;

  const styles = getComputedStyle(document.documentElement);
  const read = (token: string, fallback: string) => {
    const value = styles.getPropertyValue(token).trim();
    return value || fallback;
  };

  cachedThemeKey = themeKey;
  cachedPalette = {
    idle: read('--color-voice', FALLBACK_PALETTE.idle),
    listening: read('--color-signal', FALLBACK_PALETTE.listening),
    thinking: read('--color-energy', FALLBACK_PALETTE.thinking),
    speaking: read('--color-voice', FALLBACK_PALETTE.speaking),
  };
  return cachedPalette;
}

export const WaveformVisualizer: React.FC<WaveformVisualizerProps> = ({
  state,
  audioLevel = 0,
  height = 96,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const phaseRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Check prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    window.addEventListener('resize', resize);

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const width = rect.width;
      const h = height;

      ctx.clearRect(0, 0, width, h);

      const centerY = h / 2;
      phaseRef.current += prefersReducedMotion ? 0.005 : 0.04;

      // Theme-aware stroke color resolved from design tokens
      const baseColor = getStatePalette()[state];

      // Draw multi-layer harmonic waves
      const wavesCount = state === 'idle' ? 2 : 4;

      for (let i = 0; i < wavesCount; i++) {
        ctx.beginPath();
        const wavePhase = phaseRef.current + i * 0.8;
        const opacity = 1 - i * 0.22;

        ctx.strokeStyle = baseColor;
        ctx.globalAlpha = opacity;
        ctx.lineWidth = i === 0 ? 2.5 : 1.5;

        for (let x = 0; x < width; x += 3) {
          const normX = x / width;
          // Gaussian envelope pinning ends to center line
          const envelope = Math.sin(normX * Math.PI);

          let amp = 8;
          if (state === 'idle') {
            amp = 6 * Math.sin(normX * 4 + wavePhase) * envelope;
          } else if (state === 'listening') {
            const dynamicEnergy = Math.max(0.15, audioLevel * 1.5);
            amp = (20 * dynamicEnergy + 5) * Math.sin(normX * 8 + wavePhase) * envelope;
          } else if (state === 'thinking') {
            amp =
              (8 + 4 * Math.sin(phaseRef.current * 2)) *
              Math.sin(normX * 6 + wavePhase) *
              envelope;
          } else if (state === 'speaking') {
            amp =
              24 *
              (0.4 + 0.6 * Math.sin(phaseRef.current * 3)) *
              Math.sin(normX * 7 + wavePhase) *
              envelope;
          }

          const y = centerY + amp;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      animFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resize);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [state, audioLevel, height]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{
        width: '100%',
        height: `${height}px`,
        display: 'block',
      }}
    />
  );
};

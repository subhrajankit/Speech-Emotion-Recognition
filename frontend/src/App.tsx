import { useState, useEffect, useCallback } from 'react';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { MicrophoneControl } from './components/audio/MicrophoneControl';
import { WaveformVisualizer } from './components/audio/WaveformVisualizer';
import { AudioPlayer } from './components/audio/AudioPlayer';
import { EmotionBadge } from './components/emotion/EmotionBadge';
import { TranscriptView } from './components/transcript/TranscriptView';
import { ResponseView } from './components/transcript/ResponseView';
import { ServiceStatusCard } from './components/dashboard/ServiceStatusCard';
import { LatencyCard } from './components/dashboard/LatencyCard';
import { ConversationHistory } from './components/ConversationHistory';
import { Alert } from './components/ui/Alert';

import { useWebSocket } from './hooks/useWebSocket';
import { useAudioCapture } from './hooks/useAudioCapture';
import { useAudioPlayback } from './hooks/useAudioPlayback';
import { useHealthStatus } from './hooks/useHealthStatus';
import { useConversationHistory } from './stores/conversationStore';
import { SpeechResultMessage, VadMessage, ErrorMessage } from './types/websocket';
import { LatencyMetrics } from './types/speech';

export function App() {
  const [activeTab, setActiveTab] = useState<'voice' | 'history'>('voice');
  const [isDark, setIsDark] = useState<boolean>(true);

  // Spoken Perception State
  const [transcript, setTranscript] = useState<string>('');
  const [detectedLanguage, setDetectedLanguage] = useState<string>('unknown');
  const [emotion, setEmotion] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [latencies, setLatencies] = useState<LatencyMetrics>({});
  const [audioEvents, setAudioEvents] = useState<string[]>([]);
  const [vadHasSpeech, setVadHasSpeech] = useState<boolean>(false);
  const [activeAlert, setActiveAlert] = useState<{ variant: 'danger' | 'warning' | 'info'; message: string } | null>(null);

  // Store & Health Hooks
  const { items: historyItems, addItem, clearHistory, syncWithBackend } = useConversationHistory();
  const { health, isBackendReachable, isLoading: isHealthLoading, refresh: refreshHealth } = useHealthStatus();
  const { isPlaying, enqueueChunk, stopPlayback } = useAudioPlayback();

  // Theme synchronization
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark((prev) => !prev);
  };

  // Handle incoming WebSocket Speech Result
  const handleSpeechResult = useCallback(
    (result: SpeechResultMessage) => {
      setTranscript(result.transcript);
      setDetectedLanguage(result.language);
      setEmotion(result.emotion);
      setConfidence(result.confidence);
      setLatencies({
        asr_ms: result.processing_time_ms,
        total_ms: result.processing_time_ms,
      });
      setAudioEvents(result.audio_events || []);
      setVadHasSpeech(false);

      if (result.transcript && result.transcript.trim().length > 0) {
        addItem({
          transcript: result.transcript,
          language: result.language,
          emotion: result.emotion,
          confidence: result.confidence,
          processing_time_ms: result.processing_time_ms,
          audioEvents: result.audio_events,
        });
      }
    },
    [addItem]
  );

  // Handle VAD State changes from server
  const handleVadState = useCallback((vad: VadMessage) => {
    setVadHasSpeech(vad.state === 'speech_start');
  }, []);

  // Handle server errors
  const handleServerError = useCallback((err: ErrorMessage) => {
    setActiveAlert({
      variant: 'danger',
      message: `[${err.code}] ${err.message}`,
    });
  }, []);

  // WebSocket hook
  const {
    connectionState,
    isServerReady,
    lastError,
    sendAudioFrame,
    sendStop,
  } = useWebSocket({
    onSpeechResult: handleSpeechResult,
    onVadState: handleVadState,
    onError: handleServerError,
    onBinaryMessage: enqueueChunk,
  });

  // Audio Capture hook
  const {
    isRecording,
    audioLevel,
    errorMessage: audioError,
    toggleRecording,
    stopRecording,
  } = useAudioCapture({
    onAudioChunk: (chunk: ArrayBuffer) => {
      sendAudioFrame(chunk);
    },
    onError: (_type, msg) => {
      setActiveAlert({
        variant: 'danger',
        message: msg,
      });
    },
  });

  // Toggle recording handler with protocol stop framing
  const handleToggleRecording = () => {
    if (isRecording) {
      stopRecording();
      sendStop();
    } else {
      setActiveAlert(null);
      toggleRecording();
    }
  };

  // Derive visual pipeline state for visualizer
  let visualState: 'idle' | 'listening' | 'thinking' | 'speaking' = 'idle';
  if (isPlaying) {
    visualState = 'speaking';
  } else if (isRecording) {
    visualState = 'listening';
  }

  const isAssistantConfigured =
    health.components.llm === 'ok' && health.components.tts === 'ok';

  return (
    <DashboardLayout
      connectionState={connectionState}
      isDark={isDark}
      onToggleTheme={toggleTheme}
      activeTab={activeTab}
      onSelectTab={setActiveTab}
    >
      {/* Active Error / Alert Notice */}
      {(activeAlert || audioError || lastError) && (
        <div style={{ marginBottom: '1.25rem' }}>
          <Alert
            variant="danger"
            onDismiss={() => {
              setActiveAlert(null);
            }}
          >
            {activeAlert?.message || audioError || lastError}
          </Alert>
        </div>
      )}

      {/* Main Tab: Voice Console */}
      {activeTab === 'voice' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '960px', margin: '0 auto' }}>
          {/* Top Row: Waveform Visualizer & Central Mic Portal */}
          <div
            className="panel"
            style={{
              position: 'relative',
              overflow: 'hidden',
              padding: '2.5rem 1.5rem',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '1.5rem',
            }}
          >
            {/* Live Audio Waveform Canvas */}
            <div style={{ width: '100%', maxWidth: '640px' }}>
              <WaveformVisualizer
                state={visualState}
                audioLevel={audioLevel}
                height={100}
              />
            </div>

            {/* Microphone Control Button */}
            <MicrophoneControl
              isRecording={isRecording}
              onToggle={handleToggleRecording}
              disabled={connectionState !== 'connected' || !isServerReady}
              isConnecting={connectionState === 'connecting' || connectionState === 'reconnecting'}
              speechDetected={vadHasSpeech}
            />

            {/* Audio Playback Controls if active */}
            <AudioPlayer isPlaying={isPlaying} onStop={stopPlayback} />

            {/* Emotion & Perception Pill Ribbon */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <EmotionBadge emotion={emotion} confidence={confidence} />
            </div>
          </div>

          {/* Middle Row: Live Transcript & AI Response */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.25rem' }}>
            <TranscriptView
              transcript={transcript}
              detectedLanguage={detectedLanguage}
              latencyMs={latencies.asr_ms}
              audioEvents={audioEvents}
              isListening={isRecording}
            />

            <ResponseView
              responseText=""
              isThinking={false}
              isAssistantConfigured={isAssistantConfigured}
              totalLatencyMs={latencies.total_ms}
            />
          </div>

          {/* Bottom Row: Service Subsystems & Latency Breakdown */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.25rem' }}>
            <ServiceStatusCard
              health={health}
              isBackendReachable={isBackendReachable}
              isLoading={isHealthLoading}
              onRefresh={refreshHealth}
            />

            <LatencyCard latencies={latencies} />
          </div>
        </div>
      )}

      {/* Secondary Tab: Conversation History */}
      {activeTab === 'history' && (
        <ConversationHistory
          history={historyItems}
          onRefresh={syncWithBackend}
          onClearHistory={clearHistory}
        />
      )}
    </DashboardLayout>
  );
}

export default App;

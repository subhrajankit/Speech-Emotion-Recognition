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
import { LanguageSelector, LanguageOption } from './components/LanguageSelector';
import { StatusBanner } from './components/StatusBanner';
import { AuthModal } from './components/AuthModal';
import { MultiSegmentTurns } from './components/MultiSegmentTurns';
import { Alert } from './components/ui/Alert';

import { useWebSocket } from './hooks/useWebSocket';
import { useAudioCapture } from './hooks/useAudioCapture';
import { useAudioPlayback } from './hooks/useAudioPlayback';
import { useHealthStatus } from './hooks/useHealthStatus';
import { useConversationHistory } from './stores/conversationStore';
import { isAuthRequired } from './lib/env';
import { formatErrorMessage } from './lib/formatters';
import { UserResponse } from './services/api';
import {
  SpeechResultMessage,
  VadMessage,
  StatusMessage,
  LlmDeltaMessage,
  LlmDoneMessage,
  ErrorMessage,
} from './types/websocket';
import { LatencyMetrics } from './types/speech';

export function App() {
  const [activeTab, setActiveTab] = useState<'voice' | 'history'>('voice');
  const [isDark, setIsDark] = useState<boolean>(true);

  // Authentication State (in-memory only for XSS protection)
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserResponse | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [serverRequiresAuth, setServerRequiresAuth] = useState<boolean>(isAuthRequired());

  // Language Selection State
  const [selectedLanguage, setSelectedLanguage] = useState<LanguageOption>('auto');
  const [languageHint, setLanguageHint] = useState<string | null>(null);

  // Model Loading Status Banner State
  const [isLoadingModel, setIsLoadingModel] = useState<boolean>(false);
  const [loadingEngineName, setLoadingEngineName] = useState<string | undefined>(undefined);

  // Perception State
  const [transcript, setTranscript] = useState<string>('');
  const [detectedLanguage, setDetectedLanguage] = useState<string>('unknown');
  const [emotion, setEmotion] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [latencies, setLatencies] = useState<LatencyMetrics>({});
  const [audioEvents, setAudioEvents] = useState<string[]>([]);
  const [vadHasSpeech, setVadHasSpeech] = useState<boolean>(false);

  // Assistant Response State
  const [liveAssistantText, setLiveAssistantText] = useState<string>('');
  const [liveAssistantSources, setLiveAssistantSources] = useState<any[]>([]);
  const [isThinking, setIsThinking] = useState<boolean>(false);
  const [assistantErrorCode, setAssistantErrorCode] = useState<string | null>(null);
  const [assistantErrorMessage, setAssistantErrorMessage] = useState<string | null>(null);

  // Alerts
  const [activeAlert, setActiveAlert] = useState<{ variant: 'danger' | 'warning' | 'info'; message: string } | null>(null);

  // Conversation turns store
  const {
    items: turns,
    addSpeechResult,
    appendLlmDelta,
    completeLlmTurn,
    setAssistantError,
    clearHistory,
  } = useConversationHistory();

  // Health and Playback
  const { health, isBackendReachable, isLoading: isHealthLoading, refresh: refreshHealth } = useHealthStatus();
  const { isPlaying, enqueueChunk, stopPlayback } = useAudioPlayback();

  // Theme synchronization
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark((prev) => !prev);
  };

  // Check if server auth is required on initial mount
  useEffect(() => {
    if (isAuthRequired() && !authToken) {
      setIsAuthModalOpen(true);
    }
  }, [authToken]);

  // Handle incoming speech result
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
      setLiveAssistantText('');
      setLiveAssistantSources([]);
      setAssistantErrorCode(null);
      setAssistantErrorMessage(null);
      setIsThinking(true);

      const segIdx = result.debug?.segment_index;
      addSpeechResult({
        transcript: result.transcript,
        language: result.language,
        emotion: result.emotion,
        confidence: result.confidence,
        processing_time_ms: result.processing_time_ms,
        audioEvents: result.audio_events,
        segmentIndex: segIdx,
      });
    },
    [addSpeechResult]
  );

  // Handle VAD State changes from server
  const handleVadState = useCallback((vad: VadMessage) => {
    setVadHasSpeech(vad.state === 'speech_start');
  }, []);

  // Handle lazy loading status events
  const handleStatus = useCallback((statusMsg: StatusMessage) => {
    if (statusMsg.state === 'loading_model') {
      setIsLoadingModel(true);
      setLoadingEngineName(statusMsg.engine);
    } else if (statusMsg.state === 'model_ready') {
      setIsLoadingModel(false);
      setLoadingEngineName(undefined);
    }
  }, []);

  // Handle LLM token delta streaming
  const handleLlmDelta = useCallback(
    (msg: LlmDeltaMessage) => {
      setIsThinking(false);
      setLiveAssistantText((prev) => prev + msg.delta);
      appendLlmDelta(msg.delta);
    },
    [appendLlmDelta]
  );

  // Handle LLM done
  const handleLlmDone = useCallback(
    (msg: LlmDoneMessage) => {
      setIsThinking(false);
      setLiveAssistantText(msg.text);
      setLiveAssistantSources(msg.sources || []);
      completeLlmTurn(msg.text, msg.sources);
    },
    [completeLlmTurn]
  );

  // Handle server errors
  const handleServerError = useCallback(
    (err: ErrorMessage) => {
      setIsThinking(false);
      const friendlyMsg = formatErrorMessage(err.code, err.message);

      // Assistant-specific errors (LLM or TTS)
      if (
        err.code === 'llm_unavailable' ||
        err.code === 'llm_bad_response' ||
        err.code === 'tts_unavailable'
      ) {
        setAssistantErrorCode(err.code);
        setAssistantErrorMessage(friendlyMsg);
        setAssistantError(err.code);
        return;
      }

      // Authentication errors
      if (err.code === 'AUTH_REQUIRED' || err.code === 'AUTH_FAILED') {
        setServerRequiresAuth(true);
        setIsAuthModalOpen(true);
        setActiveAlert({
          variant: 'warning',
          message: friendlyMsg,
        });
        return;
      }

      // Other errors (rate limits, buffer overflow, etc.)
      setActiveAlert({
        variant: 'danger',
        message: friendlyMsg,
      });
    },
    [setAssistantError]
  );

  // WebSocket hook
  const {
    connectionState,
    isServerReady,
    lastError,
    sendStart,
    sendAudioFrame,
    sendStop,
  } = useWebSocket({
    languageHint,
    authToken,
    onSpeechResult: handleSpeechResult,
    onVadState: handleVadState,
    onStatus: handleStatus,
    onLlmDelta: handleLlmDelta,
    onLlmDone: handleLlmDone,
    onError: handleServerError,
    onBinaryMessage: enqueueChunk,
  });

  // Handle language switch
  const handleLanguageChange = (lang: LanguageOption, hint: string | null) => {
    setSelectedLanguage(lang);
    setLanguageHint(hint);
    // Notify server of changed language_hint
    sendStart({ language_hint: hint, auth_token: authToken });
  };

  // Handle authentication success
  const handleAuthSuccess = (token: string, user: UserResponse) => {
    setAuthToken(token);
    setCurrentUser(user);
    // Re-handshake with auth_token in start frame
    sendStart({ auth_token: token, language_hint: languageHint });
  };

  // Handle logout
  const handleLogout = () => {
    setAuthToken(null);
    setCurrentUser(null);
    sendStart({ auth_token: null, language_hint: languageHint });
  };

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

  // Visual state for visualizer
  let visualState: 'idle' | 'listening' | 'thinking' | 'speaking' = 'idle';
  if (isPlaying) {
    visualState = 'speaking';
  } else if (isRecording) {
    visualState = 'listening';
  } else if (isThinking) {
    visualState = 'thinking';
  }

  const isAssistantConfigured =
    health.components.llm === 'ok' && health.components.tts !== 'disabled';
  const isAssistantUnavailable =
    health.components.llm === 'unavailable' || assistantErrorCode === 'llm_unavailable';

  return (
    <DashboardLayout
      connectionState={connectionState}
      isDark={isDark}
      onToggleTheme={toggleTheme}
      activeTab={activeTab}
      onSelectTab={setActiveTab}
      currentUser={currentUser}
      onOpenAuth={() => setIsAuthModalOpen(true)}
    >
      {/* Model Loading Status Banner per Requirement 3 */}
      <StatusBanner isLoadingModel={isLoadingModel} engineName={loadingEngineName} />

      {/* Active Alert Banner */}
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
          {/* Top Panel: Visualizer, Language Selector & Microphone Controls */}
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
            {/* Language Selector per Requirement 1 */}
            <LanguageSelector
              selectedLanguage={selectedLanguage}
              onChange={handleLanguageChange}
              disabled={isRecording}
            />

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

            {/* Audio Playback Controls & Voice Replies Off notice per Requirement 6 */}
            <AudioPlayer
              isPlaying={isPlaying}
              onStop={stopPlayback}
              ttsStatus={health.components.tts}
            />

            {/* Emotion & Perception Ribbon with Null-Safe display per Requirement 5 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <EmotionBadge emotion={emotion} confidence={confidence} />
            </div>
          </div>

          {/* Active Live Utterance View: User Speech & AI Response */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.25rem' }}>
            <TranscriptView
              transcript={transcript}
              detectedLanguage={detectedLanguage}
              latencyMs={latencies.asr_ms}
              audioEvents={audioEvents}
              isListening={isRecording}
            />

            <ResponseView
              responseText={liveAssistantText}
              isThinking={isThinking}
              isAssistantConfigured={isAssistantConfigured}
              isAssistantUnavailable={isAssistantUnavailable}
              errorCode={assistantErrorCode}
              errorMessage={assistantErrorMessage}
              totalLatencyMs={latencies.total_ms}
              sources={liveAssistantSources}
            />
          </div>

          {/* Multi-Segment Utterance Rows per Requirement 2 */}
          <MultiSegmentTurns turns={turns} />

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

      {/* Secondary Tab: Persistent Conversation History */}
      {activeTab === 'history' && (
        <ConversationHistory
          token={authToken}
          onOpenAuth={() => setIsAuthModalOpen(true)}
          onClearLocalHistory={clearHistory}
        />
      )}

      {/* Authentication Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        token={authToken}
        currentUser={currentUser}
        onAuthSuccess={handleAuthSuccess}
        onLogout={handleLogout}
        serverRequiresAuth={serverRequiresAuth}
      />
    </DashboardLayout>
  );
}

export default App;

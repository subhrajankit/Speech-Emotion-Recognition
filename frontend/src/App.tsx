import { useState, useEffect, useCallback, useRef, CSSProperties } from 'react';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { AudioPlayer } from './components/audio/AudioPlayer';
import { VoiceStage } from './components/voice/VoiceStage';
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
import { FirstRunGuidance } from './components/FirstRunGuidance';
import { SettingsPanel } from './components/SettingsPanel';
import { RecentConversations } from './components/rail/RecentConversations';
import { InsightsPanel } from './components/rail/InsightsPanel';
import { Alert } from './components/ui/Alert';

import { useWebSocket } from './hooks/useWebSocket';
import { useAudioCapture } from './hooks/useAudioCapture';
import { useAudioPlayback } from './hooks/useAudioPlayback';
import { useHealthStatus } from './hooks/useHealthStatus';
import { useTheme } from './hooks/useTheme';
import { useConversationHistory } from './stores/conversationStore';
import { isAuthRequired, isAsrEnglishOnly } from './lib/env';
import { formatErrorMessage } from './lib/formatters';
import {
  createRecordingController,
  RecordingController,
} from './lib/recordingController';
import { deriveAssistantStatus } from './lib/assistantStatus';
import { isConnectionLostState } from './lib/connectionLoss';
import { hasSpeechTranscript, isNoSpeechStatus, noSpeechNoticeFor } from './lib/speechResult';
import { resolveDisplayEmotion } from './lib/emotionDisplay';
import { announcementTextFor, createAnnouncer, LiveAnnouncement } from './lib/announcements';
import { isUnexpectedCaptureTermination } from './lib/captureFailure';
import { micPhase, micToggleAction } from './lib/micControl';
import { discardAlertFor, sameAlertMessage } from './lib/utteranceDiscard';
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

/** Visually-hidden styling for the screen-reader live region (no sr-only utility exists). */
const SR_ONLY_STYLE: CSSProperties = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

export function App() {
  const [activeTab, setActiveTab] = useState<'voice' | 'history' | 'settings'>('voice');
  const [historyFocusRequest, setHistoryFocusRequest] = useState<{ sessionId: string; nonce: number } | null>(null);
  // Theme state: persisted in localStorage, falls back to OS preference.
  // The hook applies data-theme to <html> itself (synchronously on first
  // render, then on every change).
  const { isDark, toggleTheme } = useTheme();

  // Authentication State (in-memory only for XSS protection)
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserResponse | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [serverRequiresAuth, setServerRequiresAuth] = useState<boolean>(isAuthRequired());
  const asrEnglishOnly = isAsrEnglishOnly();

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
  // Wall-clock microphone-active elapsed time for the recording timer.
  // NOTE: this is total recording time, not per-utterance duration — the
  // server's 30s cap resets per VAD segment and is not exposed to the client.
  const [recordingElapsedSec, setRecordingElapsedSec] = useState<number>(0);

  // Assistant Response State
  const [liveAssistantText, setLiveAssistantText] = useState<string>('');
  const [liveAssistantSources, setLiveAssistantSources] = useState<any[]>([]);
  const [isThinking, setIsThinking] = useState<boolean>(false);
  const [assistantErrorCode, setAssistantErrorCode] = useState<string | null>(null);
  const [assistantErrorMessage, setAssistantErrorMessage] = useState<string | null>(null);

  // Alerts
  const [activeAlert, setActiveAlert] = useState<{ variant: 'danger' | 'warning' | 'info'; message: string } | null>(null);
  // Non-error notice shown when ASR returns an empty transcript (e.g. silence).
  const [noSpeechNotice, setNoSpeechNotice] = useState<string | null>(null);
  // Single polite live-region announcement for screen readers (Chunk 9.5B).
  // Driven imperatively from event handlers — never from derived state.
  const [announcement, setAnnouncement] = useState<LiveAnnouncement | null>(null);

  // Conversation turns store
  const {
    items: turns,
    addSpeechResult,
    appendLlmDelta,
    completeLlmTurn,
    setAssistantError,
    cancelActiveStream,
    clearHistory,
  } = useConversationHistory();

  // Tracks the last authenticated user id across token clears so an account
  // switch (including login-as-different-user after an auth failure) can be
  // detected and the previous account's live UI state discarded.
  const lastUserIdRef = useRef<string | null>(null);

  // Screen-reader announcer: fresh id per announcement so identical text in
  // distinct turns still produces a new live-region node.
  const announcerRef = useRef<ReturnType<typeof createAnnouncer> | null>(null);
  if (announcerRef.current === null) {
    announcerRef.current = createAnnouncer();
  }
  const pushAnnouncement = useCallback((text: string | null) => {
    const next = announcerRef.current?.announce(text);
    if (next) setAnnouncement(next);
  }, []);

  // Health and Playback
  const { health, isBackendReachable, isLoading: isHealthLoading, refresh: refreshHealth } = useHealthStatus();
  const { isPlaying, enqueueChunk, stopPlayback } = useAudioPlayback();

  // Check if server auth is required on initial mount
  useEffect(() => {
    if (isAuthRequired() && !authToken) {
      setIsAuthModalOpen(true);
    }
  }, [authToken]);

  // Handle incoming speech result
  const handleSpeechResult = useCallback(
    (result: SpeechResultMessage) => {
      // Empty/whitespace transcripts carry no usable speech: do not create a
      // turn or activate thinking — the server sends no llm_done for them,
      // which would leave both stuck forever.
      if (!hasSpeechTranscript(result.transcript)) {
        setNoSpeechNotice(noSpeechNoticeFor('no_speech'));
        return;
      }
      setNoSpeechNotice(noSpeechNoticeFor('valid_result'));
      setTranscript(result.transcript);
      setDetectedLanguage(result.language);
      // EMO_UNKNOWN/UNK raw tags surface as "Unknown"; absent metadata stays "-".
      const displayEmotion = resolveDisplayEmotion(result.emotion, result.debug?.raw_tags);
      setEmotion(displayEmotion);
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
        emotion: displayEmotion,
        confidence: result.confidence,
        processing_time_ms: result.processing_time_ms,
        audioEvents: result.audio_events,
        segmentIndex: segIdx,
      });
      // Announce the stable transcript once (ASR returns complete text).
      pushAnnouncement(
        announcementTextFor({ type: 'speech_result', transcript: result.transcript })
      );
    },
    [addSpeechResult, pushAnnouncement]
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
    } else if (isNoSpeechStatus(statusMsg.state)) {
      // Server confirmed no speech: show the same non-error notice the
      // empty-transcript guard uses. No turn, no thinking state.
      setNoSpeechNotice(noSpeechNoticeFor('no_speech'));
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
      // Announce the completed response once — never per llm_delta.
      pushAnnouncement(announcementTextFor({ type: 'llm_done', text: msg.text }));
    },
    [completeLlmTurn, pushAnnouncement]
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

      // Discard-and-continue errors (duration cap / buffer overflow): the
      // server dropped only the current utterance — capture, socket, and
      // controller all stay live. Surface a warning, never stop recording,
      // and dedupe repeated identical frames so they don't re-announce.
      const discardAlert = discardAlertFor(err.code, err.message);
      if (discardAlert) {
        setActiveAlert((prev) =>
          sameAlertMessage(prev, discardAlert) ? prev : discardAlert
        );
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

  // WebSocket policy rejection (close 1008): the token we sent was refused.
  // Clear dead credentials, open the auth modal, and let the hook's single
  // deferred reconnect re-establish an anonymous (or re-authenticated) socket.
  const handleWsAuthRejected = useCallback(() => {
    setAuthToken(null);
    setCurrentUser(null);
    setIsAuthModalOpen(true);
    setActiveAlert({
      variant: 'warning',
      message:
        'Authentication was rejected by the server — your session may have expired. Please sign in again.',
    });
  }, []);

  // WebSocket hook
  const {
    connectionState,
    isServerReady,
    lastError,
    sendStart,
    sendAudioFrame,
    sendStop,
    reconnect,
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
    onAuthRejected: handleWsAuthRejected,
  });

  // Handle language switch
  const handleLanguageChange = (lang: LanguageOption, hint: string | null) => {
    setSelectedLanguage(lang);
    setLanguageHint(hint);
    // Notify server of changed language_hint
    sendStart({ language_hint: hint, auth_token: authToken });
  };

  // Reset all live voice/perception state belonging to the previous account.
  // Never fabricates assistant completions — cancelActiveStream only clears
  // the streaming flag; clearHistory drops in-memory turns entirely.
  const resetLiveConversation = () => {
    clearHistory();
    cancelActiveStream();
    setTranscript('');
    setDetectedLanguage('unknown');
    setEmotion(null);
    setConfidence(null);
    setLatencies({});
    setAudioEvents([]);
    setVadHasSpeech(false);
    setLiveAssistantText('');
    setLiveAssistantSources([]);
    setIsThinking(false);
    setAssistantErrorCode(null);
    setAssistantErrorMessage(null);
    setNoSpeechNotice(noSpeechNoticeFor('reset'));
    setAnnouncement(null);
  };

  // Handle authentication success
  const handleAuthSuccess = (token: string, user: UserResponse) => {
    // Account switch: discard the previous account's live turns/state so they
    // cannot appear under the new account. Same-account re-login keeps them.
    const isDifferentAccount =
      lastUserIdRef.current !== null && lastUserIdRef.current !== user.id;
    lastUserIdRef.current = user.id;
    if (isDifferentAccount) {
      resetLiveConversation();
    }
    setAuthToken(token);
    setCurrentUser(user);
    // Re-handshake with auth_token in start frame
    sendStart({ auth_token: token, language_hint: languageHint });
    // If the socket was torn down by a 1008 rejection there is nothing to
    // re-handshake on — establish a fresh connection instead.
    if (connectionState === 'disconnected' || connectionState === 'error') {
      reconnect();
    }
  };

  // Centralized REST auth recovery: a 401/403 from any protected history call
  // clears the dead in-memory credentials, opens the auth modal, and lets the
  // existing !token gate in ConversationHistory clear stale history.
  const handleHistoryAuthError = useCallback(() => {
    setAuthToken(null);
    setCurrentUser(null);
    setIsAuthModalOpen(true);
    setActiveAlert({
      variant: 'warning',
      message:
        'Your session expired or access is no longer authorized. Please sign in again.',
    });
  }, []);

  // Handle logout
  const handleLogout = () => {
    lastUserIdRef.current = null;
    resetLiveConversation();
    setAuthToken(null);
    setCurrentUser(null);
    sendStart({ auth_token: null, language_hint: languageHint });
    if (connectionState === 'disconnected' || connectionState === 'error') {
      reconnect();
    }
  };

  // Declared before useAudioCapture so the capture onError path can reach the
  // controller when a track ends unexpectedly mid-recording.
  const recordingControllerRef = useRef<RecordingController | null>(null);
  // Mirrors controller.isStarting() for render: true while a `start` frame was
  // sent and capture is still initializing (permission prompt / pipeline).
  const [isMicStarting, setIsMicStarting] = useState(false);
  // Guards setIsMicStarting against firing after App unmounts.
  const isMountedRef = useRef(true);
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Audio Capture hook
  const {
    isRecording,
    audioLevel,
    errorMessage: audioError,
    startRecording,
    stopRecording,
  } = useAudioCapture({
    onAudioChunk: (chunk: ArrayBuffer) => {
      sendAudioFrame(chunk);
    },
    onError: (type, msg) => {
      setActiveAlert({
        variant: 'danger',
        message: msg,
      });
      // Unexpected mid-recording track termination: release the controller's
      // active/starting state and send the normal stop frame (no-op on a dead
      // socket). Idempotent — stop() emits cleanup/frames only once, and the
      // capture layer nulls track.onended during cleanup so ordinary user
      // stops can never reach this branch.
      if (isUnexpectedCaptureTermination(type)) {
        recordingControllerRef.current?.stop();
      }
    },
  });

  // Recording session controller: guarantees a fresh `start` frame is sent
  // before capture on every recording start (including restarts after `stop`),
  // exactly once per session, and only while the socket is connected+ready.
  const readinessRef = useRef({ connectionState, isServerReady });
  readinessRef.current = { connectionState, isServerReady };

  if (recordingControllerRef.current === null) {
    recordingControllerRef.current = createRecordingController({
      isReady: () => {
        const r = readinessRef.current;
        return r.connectionState === 'connected' && r.isServerReady;
      },
      // sendStart() with no overrides resolves language_hint/auth_token from the
      // hook's latest options, identical to the initial-connect handshake.
      sendStartFrame: () => sendStart(),
      sendStopFrame: () => sendStop(),
      startCapture: (shouldAbort) => startRecording({ shouldAbort }),
      stopCapture: () => stopRecording(),
      onSessionStart: () => {
        // A genuinely new recording session supersedes the previous live
        // result: clear it so a stale transcript/emotion/latency cannot be
        // mistaken for the new utterance's output while ASR is pending.
        setTranscript('');
        setEmotion(null);
        setLatencies({});
      },
      onStateChange: () => {
        if (isMountedRef.current) {
          setIsMicStarting(recordingControllerRef.current?.isStarting() ?? false);
        }
      },
      onNotReady: () =>
        setActiveAlert({
          variant: 'warning',
          message:
            'Still connecting to the speech server. Please wait a moment and try again.',
        }),
    });
  }

  // Recording elapsed timer: ticks only while capture is active and resets
  // on stop, disconnect, or auth loss (all of which clear isRecording).
  useEffect(() => {
    if (!isRecording) {
      setRecordingElapsedSec(0);
      return;
    }
    setRecordingElapsedSec(0);
    const id = window.setInterval(() => {
      setRecordingElapsedSec((s) => s + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [isRecording]);

  // Toggle recording handler with protocol stop framing. While capture is
  // still starting (permission prompt / pipeline init), the same control
  // cancels the pending start — the controller's epoch guard tears down
  // whatever the in-flight capture produces.
  const handleToggleRecording = () => {
    const ctl = recordingControllerRef.current;
    const phase = micPhase(isRecording, ctl?.isStarting() ?? false);
    if (micToggleAction(phase) === 'stop') {
      ctl?.stop();
      return;
    }
    setActiveAlert(null);
    // A fresh recording attempt supersedes any previous no-speech notice.
    setNoSpeechNotice(noSpeechNoticeFor('recording_start'));
    void ctl?.start();
  };

  // Stop capture and finalize interrupted turns on genuine connection loss.
  // The server discards in-flight audio and cancels LLM/TTS work on socket
  // close, so continuing to capture would imply audio is being processed when
  // it is not. 'connecting'/'connected' transitions never trigger this.
  const cancelActiveStreamRef = useRef(cancelActiveStream);
  cancelActiveStreamRef.current = cancelActiveStream;

  // Mirrors whether an assistant response is genuinely in flight
  // (pre-first-delta thinking OR mid-stream turn) for interruption notices.
  const responseInProgressRef = useRef(false);
  responseInProgressRef.current =
    isThinking || (turns.length > 0 && turns[0].isStreaming === true);

  useEffect(() => {
    if (!isConnectionLostState(connectionState)) return;

    const ctl = recordingControllerRef.current;
    const wasRecording = !!ctl && (ctl.isActive() || ctl.isStarting());
    if (wasRecording) {
      ctl.stop();
      setActiveAlert({
        variant: 'warning',
        message:
          'Connection lost — recording stopped. Press Start Listening to resume after reconnecting.',
      });
    }

    // Any in-flight LLM stream died with the socket; finalize the turn without
    // fabricating a completion and clear the thinking indicator.
    const wasResponding = responseInProgressRef.current;
    cancelActiveStreamRef.current();
    setIsThinking(false);
    if (wasResponding) {
      pushAnnouncement(announcementTextFor({ type: 'interrupted' }));
    }
  }, [connectionState, pushAnnouncement]);

  // Microphone privacy boundary: whenever the session becomes unauthenticated
  // (logout, REST 401/403 recovery, WS 1008 rejection), any active or pending
  // capture must stop. Routes through the controller so its epoch guard also
  // invalidates an in-flight getUserMedia/pipeline start. Idempotent with the
  // connection-loss effect above — repeated stop() calls emit no duplicate
  // frames. Never fires on login (authToken transitions null -> token).
  useEffect(() => {
    if (authToken !== null) return;
    const ctl = recordingControllerRef.current;
    if (ctl && (ctl.isActive() || ctl.isStarting())) {
      ctl.stop();
    }
  }, [authToken]);

  // Visual state for visualizer
  let visualState: 'idle' | 'listening' | 'thinking' | 'speaking' = 'idle';
  if (isPlaying) {
    visualState = 'speaking';
  } else if (isRecording) {
    visualState = 'listening';
  } else if (isThinking) {
    visualState = 'thinking';
  }

  // Text-assistant availability depends on LLM health only; TTS state is
  // surfaced independently via AudioPlayer's "voice replies are off" notice.
  const assistantStatus = deriveAssistantStatus(health.components);
  const isAssistantUnavailable =
    assistantStatus.isAssistantUnavailable || assistantErrorCode === 'llm_unavailable';

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
      {/* Single polite live region for screen-reader turn announcements.
          Visually hidden; announces completed transcripts/replies once,
          never per-token deltas. */}
      <div aria-live="polite" role="status" style={SR_ONLY_STYLE}>
        {announcement && <span key={announcement.id}>{announcement.text}</span>}
      </div>

      {/* Model Loading Status Banner per Requirement 3 */}
      <StatusBanner isLoadingModel={isLoadingModel} engineName={loadingEngineName} />

      {/* Active Alert Banner */}
      {(activeAlert || audioError || lastError) && (
        <div className="alert-wrap">
          <Alert
            variant={activeAlert?.variant ?? 'danger'}
            onDismiss={() => {
              setActiveAlert(null);
            }}
          >
            {activeAlert?.message || audioError || lastError}
          </Alert>
        </div>
      )}

      {/* No-speech notice (non-error, dismissible) */}
      {noSpeechNotice && (
        <div className="alert-wrap">
          <Alert
            variant="info"
            dismissLabel="Dismiss no-speech notice"
            onDismiss={() => setNoSpeechNotice(noSpeechNoticeFor('dismiss'))}
          >
            {noSpeechNotice}
          </Alert>
        </div>
      )}

      {/* Main Tab: Voice Console — center stage + right rail */}
      {activeTab === 'voice' && (
        <div className="dashboard-page console-layout">
          <div className="console-main">
          <FirstRunGuidance isRecording={isRecording} />
          {/* Premium central voice stage: orb mic + waveform + suggested actions */}
          <VoiceStage
            visualState={visualState}
            audioLevel={audioLevel}
            isRecording={isRecording}
            onToggleRecording={handleToggleRecording}
            micDisabled={connectionState !== 'connected' || !isServerReady}
            isConnecting={connectionState === 'connecting' || connectionState === 'reconnecting'}
            isStarting={isMicStarting}
            modalOpen={isAuthModalOpen}
            speechDetected={vadHasSpeech}
            elapsedSeconds={recordingElapsedSec}
            selectedLanguage={selectedLanguage}
            onLanguageChange={handleLanguageChange}
            englishOnly={asrEnglishOnly}
          />

          {/* Language selector notes, emotion ribbon & audio playback */}
          <div className="voice-extras">
            <LanguageSelector
              selectedLanguage={selectedLanguage}
              onChange={handleLanguageChange}
              disabled={isRecording || isMicStarting}
              englishOnly={asrEnglishOnly}
            />

            {/* Emotion & Perception Ribbon with Null-Safe display per Requirement 5 */}
            <div className="emotion-ribbon">
              <EmotionBadge emotion={emotion} confidence={confidence} />
            </div>

            {/* Audio Playback Controls & Voice Replies Off notice per Requirement 6 */}
            <AudioPlayer
              isPlaying={isPlaying}
              onStop={stopPlayback}
              ttsStatus={health.components.tts}
            />
          </div>

          {/* Active Live Utterance View: User Speech & AI Response */}
          <div className="grid-cards">
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
              isAssistantAvailable={assistantStatus.isTextAssistantAvailable}
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
          <div className="grid-cards">
            <ServiceStatusCard
              health={health}
              isBackendReachable={isBackendReachable}
              isLoading={isHealthLoading}
              onRefresh={refreshHealth}
            />

            <LatencyCard latencies={latencies} />
          </div>
          </div>

          {/* Right rail: recent conversations + session insights */}
          <aside className="console-rail">
            <RecentConversations
              token={authToken}
              onSelectSession={(sessionId) => {
                setActiveTab('history');
                setHistoryFocusRequest({ sessionId, nonce: Date.now() });
              }}
              onViewAll={() => setActiveTab('history')}
              onOpenAuth={() => setIsAuthModalOpen(true)}
              onAuthError={handleHistoryAuthError}
            />
            <InsightsPanel
              connectionState={connectionState}
              latencies={latencies}
              sessionTurns={turns.length}
              latestEmotion={emotion}
              latestConfidence={confidence}
              health={health}
              isBackendReachable={isBackendReachable}
              isLoading={isHealthLoading}
            />
          </aside>
        </div>
      )}

      {/* Secondary Tab: Persistent Conversation History */}
      {activeTab === 'history' && (
        <div className="dashboard-page">
          <ConversationHistory
            token={authToken}
            onOpenAuth={() => setIsAuthModalOpen(true)}
            onClearLocalHistory={clearHistory}
            onAuthError={handleHistoryAuthError}
            openSessionRequest={historyFocusRequest}
          />
        </div>
      )}

      {/* Settings Tab: minimal preferences view (theme, language, account) */}
      {activeTab === 'settings' && (
        <SettingsPanel
          isDark={isDark}
          onToggleTheme={toggleTheme}
          selectedLanguage={selectedLanguage}
          onLanguageChange={handleLanguageChange}
          englishOnly={asrEnglishOnly}
          currentUser={currentUser}
          onOpenAuth={() => setIsAuthModalOpen(true)}
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

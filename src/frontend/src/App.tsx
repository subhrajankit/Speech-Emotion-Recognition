import { useState, useEffect, useRef } from 'react';
import { Header, PageId } from './components/Header';
import { LandingPage } from './components/LandingPage';
import { VoiceConsole, PipelineStage } from './components/VoiceConsole';
import { ConversationHistory, EmotionRecord } from './components/ConversationHistory';
import { DocumentManager } from './components/DocumentManager';
import { AnalyticsDashboard, MetricItem } from './components/AnalyticsDashboard';
import { SettingsPage } from './components/SettingsPage';
import { AuthModal } from './components/AuthModal';

interface LatencyMetrics {
  asr_ms?: number;
  emotion_ms?: number;
  rag_ms?: number;
  llm_ms?: number;
  tts_ms?: number;
  ttft_ms?: number;
  ttfa_ms?: number;
  total_ms?: number;
}

interface AudioContextData {
  language?: string;
  script?: string;
  mixed_language?: boolean;
  confidence?: number;
  model_used?: string;
}

interface EmotionData {
  primary?: string;
  confidence?: number;
  valence?: number;
  arousal?: number;
  lexical_polarity?: number;
}

interface BenchmarkSummary {
  count: number;
  stages: Record<string, { min: number; avg: number; max: number; p95: number }>;
}

type TransportMode = 'webtransport' | 'websocket' | 'connecting';

export function App() {
  const [currentPage, setCurrentPage] = useState<PageId>('console');
  const [isDark, setIsDark] = useState<boolean>(true);
  const [isAuthOpen, setIsAuthOpen] = useState<boolean>(false);
  const [sessionId, setSessionId] = useState<string>('sess_default');
  const [authToken, setAuthToken] = useState<string>('');

  // Transport & Audio State
  const [isConnected, setIsConnected] = useState(false);
  const [transportMode, setTransportMode] = useState<TransportMode>('connecting');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);

  // Spoken Conversation State
  const [transcript, setTranscript] = useState('');
  const [responseText, setResponseText] = useState('');
  const [latencies, setLatencies] = useState<LatencyMetrics>({});
  const [audioContext, setAudioContext] = useState<AudioContextData | null>(null);
  const [emotion, setEmotion] = useState<EmotionData | null>(null);
  const [intentCategory, setIntentCategory] = useState<string>('chat');
  const [llmProvider, setLlmProvider] = useState<'local' | 'cloud'>('local');
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined);

  // Settings State
  const [geminiApiKey, setGeminiApiKey] = useState('');
  const [preferredLanguage, setPreferredLanguage] = useState('auto');
  const [silenceTimeoutMs, setSilenceTimeoutMs] = useState(700);

  // Telemetry & History State
  const [benchmarkMetrics, setBenchmarkMetrics] = useState<MetricItem[]>([]);
  const [benchmarkSummary, setBenchmarkSummary] = useState<BenchmarkSummary | null>(null);
  const [isRefreshingBenchmarks, setIsRefreshingBenchmarks] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<EmotionRecord[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);

  // Transport References
  const socketRef = useRef<WebSocket | null>(null);
  const webTransportRef = useRef<any | null>(null);
  const streamAWriterRef = useRef<any | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const scriptNodeRef = useRef<ScriptProcessorNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingChunkRef = useRef<boolean>(false);
  const playbackContextRef = useRef<AudioContext | null>(null);

  // Theme management
  const toggleTheme = () => {
    const nextTheme = !isDark;
    setIsDark(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme ? 'dark' : 'light');
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  // Compute Active Orchestrated Stage
  let activeStage: PipelineStage = 'idle';
  if (isRecording) activeStage = 'listening';
  else if (isProcessing) activeStage = 'thinking';
  else if (isPlaying) activeStage = 'speaking';

  // Issue or fetch JWT token
  const fetchSessionToken = async (): Promise<string> => {
    try {
      const host = window.location.hostname || '127.0.0.1';
      const res = await fetch(`http://${host}:8000/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: 'vite-web-client' })
      });
      if (res.ok) {
        const data = await res.json();
        setAuthToken(data.token);
        setSessionId(data.session_id);
        return data.token;
      }
    } catch (e) {
      console.warn('[Security] Could not fetch session auth token:', e);
    }
    return '';
  };

  // Playback Audio Queue
  const enqueueAudioChunk = async (chunk: ArrayBuffer) => {
    audioQueueRef.current.push(chunk);
    if (!isPlayingChunkRef.current) {
      playNextChunk();
    }
  };

  const playNextChunk = async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingChunkRef.current = false;
      setIsPlaying(false);
      return;
    }

    isPlayingChunkRef.current = true;
    setIsPlaying(true);
    const chunk = audioQueueRef.current.shift();
    if (!chunk) return;

    try {
      if (!playbackContextRef.current || playbackContextRef.current.state === 'closed') {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        playbackContextRef.current = new AudioCtx();
      }

      if (playbackContextRef.current.state === 'suspended') {
        await playbackContextRef.current.resume();
      }

      const audioBuffer = await playbackContextRef.current.decodeAudioData(chunk.slice(0));
      const source = playbackContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(playbackContextRef.current.destination);
      source.onended = () => {
        playNextChunk();
      };
      source.start();
    } catch (e) {
      console.warn('Could not decode audio chunk for playback:', e);
      playNextChunk();
    }
  };

  // Server Event Handler
  const handleServerEvent = (data: any) => {
    if (data.type === 'llm_start') {
      setIsProcessing(false);
      setResponseText('');
    } else if (data.type === 'sentence_start') {
      setResponseText(prev => prev ? `${prev} ${data.text}` : data.text);
    } else if (data.type === 'turn_complete' || data.type === 'complete' || data.type === 'result') {
      setIsProcessing(false);
      if (data.transcript) setTranscript(data.transcript);
      if (data.response_text) setResponseText(data.response_text);
      if (data.latencies) setLatencies(data.latencies);
      if (data.context) setAudioContext(data.context);
      if (data.emotion) setEmotion(data.emotion);
      if (data.intent) setIntentCategory(data.intent.category || 'chat');
      fetchBenchmarkData();
      fetchHistory();
    } else if (data.type === 'metadata') {
      if (data.transcript) setTranscript(data.transcript);
      if (data.context) setAudioContext(data.context);
      if (data.emotion) setEmotion(data.emotion);
      if (data.intent) setIntentCategory(data.intent.category || 'chat');
    } else if (data.type === 'error') {
      setErrorMessage(data.message || 'An error occurred during voice turn processing.');
      setIsProcessing(false);
      setIsRecording(false);
    }
  };

  // Connect WebSocket Fallback
  const connectWebSocket = async (explicitToken?: string) => {
    const token = explicitToken || authToken || await fetchSessionToken();
    const host = window.location.hostname || '127.0.0.1';
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    const wsUrl = `ws://${host}:8000/ws/voice${query}`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      setIsConnected(true);
      setTransportMode('websocket');
    };

    ws.onclose = () => {
      setIsConnected(false);
      setTransportMode('connecting');
      setTimeout(() => connectWebSocket(), 3000);
    };

    ws.onerror = (err) => {
      console.warn('[Transport] WebSocket connection error:', err);
    };

    ws.onmessage = async (event) => {
      if (typeof event.data === 'string') {
        try {
          const data = JSON.parse(event.data);
          handleServerEvent(data);
        } catch (e) {
          console.error('Failed to parse text message:', e);
        }
      } else if (event.data instanceof ArrayBuffer) {
        enqueueAudioChunk(event.data);
      }
    };

    socketRef.current = ws;
  };

  // Connect WebTransport with auto-fallback
  const initiateTransport = async () => {
    const hasWebTransport = typeof window !== 'undefined' && 'WebTransport' in window;
    if (!hasWebTransport) {
      connectWebSocket();
      return;
    }

    try {
      const wtHost = window.location.hostname || '127.0.0.1';
      const token = authToken || await fetchSessionToken();
      const query = token ? `?token=${encodeURIComponent(token)}` : '';
      const wtUrl = `https://${wtHost}:8000/wt${query}`;

      const WTConstructor = (window as any).WebTransport;
      const wt = new WTConstructor(wtUrl);

      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), 2000)
      );

      await Promise.race([wt.ready, timeoutPromise]);
      webTransportRef.current = wt;
      setTransportMode('webtransport');
      setIsConnected(true);

      const streamA = await wt.createUnidirectionalStream();
      streamAWriterRef.current = streamA.getWriter();
    } catch {
      connectWebSocket();
    }
  };

  // Fetch benchmark metrics
  const fetchBenchmarkData = async () => {
    setIsRefreshingBenchmarks(true);
    try {
      const host = window.location.hostname || '127.0.0.1';
      const [metricsRes, summaryRes] = await Promise.all([
        fetch(`http://${host}:8000/api/benchmark/metrics?limit=30`),
        fetch(`http://${host}:8000/api/benchmark/summary`)
      ]);
      if (metricsRes.ok && summaryRes.ok) {
        const metrics = await metricsRes.json();
        const summary = await summaryRes.json();
        setBenchmarkMetrics(metrics);
        setBenchmarkSummary(summary);
      }
    } catch (err) {
      console.debug('Failed to fetch benchmark data:', err);
    } finally {
      setIsRefreshingBenchmarks(false);
    }
  };

  // Fetch conversation history
  const fetchHistory = async () => {
    setIsHistoryLoading(true);
    try {
      const host = window.location.hostname || '127.0.0.1';
      const convId = sessionId ? `conv_${sessionId}` : 'default_session';
      const res = await fetch(`http://${host}:8000/api/emotion/history/${convId}?limit=25`);
      if (res.ok) {
        const data = await res.json();
        setConversationHistory(data);
      }
    } catch (err) {
      console.debug('Failed to fetch conversation history:', err);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  const handleResetBenchmarks = async () => {
    try {
      const host = window.location.hostname || '127.0.0.1';
      await fetch(`http://${host}:8000/api/benchmark/reset`, { method: 'POST' });
      fetchBenchmarkData();
    } catch (err) {
      console.error('Failed to reset benchmarks:', err);
    }
  };

  // Recording Management
  const startRecording = async () => {
    setErrorMessage(undefined);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });
      micStreamRef.current = stream;

      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      const ctx = new AudioContextClass({ sampleRate: 16000 });
      audioContextRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);

      // ScriptProcessorNode fallback for 16kHz PCM downsampling
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      scriptNodeRef.current = processor;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        let sum = 0;
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          sum += Math.abs(s);
        }
        setAudioLevel(Math.min(1.0, (sum / inputData.length) * 5));

        // Send audio chunk
        if (transportMode === 'webtransport' && streamAWriterRef.current) {
          streamAWriterRef.current.write(pcm16.buffer).catch(() => {});
        } else if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(pcm16.buffer);
        }
      };

      source.connect(processor);
      processor.connect(ctx.destination);

      setIsRecording(true);
      setTranscript('');
      setResponseText('');
    } catch (err) {
      console.error('Microphone access denied:', err);
      setErrorMessage('Microphone access was denied. Please allow audio access in your browser settings.');
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    setIsProcessing(true);

    if (scriptNodeRef.current) {
      scriptNodeRef.current.disconnect();
      scriptNodeRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach(t => t.stop());
      micStreamRef.current = null;
    }
    setAudioLevel(0);

    // Emit end-of-utterance signal
    const endMsg = JSON.stringify({ type: 'control', action: 'end_of_utterance' });
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(endMsg);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleProviderSelect = (provider: string) => {
    const prov = provider as 'local' | 'cloud';
    setLlmProvider(prov);
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ action: 'set_llm_provider', provider: prov }));
    }
  };

  useEffect(() => {
    initiateTransport();
    fetchBenchmarkData();
    fetchHistory();

    return () => {
      if (socketRef.current) socketRef.current.close();
      if (webTransportRef.current) {
        try { webTransportRef.current.close(); } catch {}
      }
      stopRecording();
    };
  }, []);

  return (
    <div className="app-wrapper">
      <Header
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        transportMode={transportMode}
        isConnected={isConnected}
        isDark={isDark}
        onToggleTheme={toggleTheme}
        sessionId={sessionId}
        onOpenAuth={() => setIsAuthOpen(true)}
      />

      <main className="main-content">
        {currentPage === 'landing' && (
          <LandingPage onStartConsole={() => setCurrentPage('console')} />
        )}

        {currentPage === 'console' && (
          <VoiceConsole
            stage={activeStage}
            isRecording={isRecording}
            onToggleRecording={toggleRecording}
            transcript={transcript}
            responseText={responseText}
            audioLevel={audioLevel}
            detectedLanguage={audioContext?.language || 'en'}
            primaryEmotion={emotion?.primary || 'neutral'}
            valence={emotion?.valence || 0.0}
            arousal={emotion?.arousal || 0.0}
            intentCategory={intentCategory}
            llmProvider={llmProvider}
            latencies={latencies}
            errorMessage={errorMessage}
            onClearError={() => setErrorMessage(undefined)}
          />
        )}

        {currentPage === 'history' && (
          <ConversationHistory
            history={conversationHistory}
            onRefresh={fetchHistory}
            isLoading={isHistoryLoading}
            onClearHistory={() => setConversationHistory([])}
          />
        )}

        {currentPage === 'documents' && (
          <DocumentManager />
        )}

        {currentPage === 'analytics' && (
          <AnalyticsDashboard
            metrics={benchmarkMetrics}
            summary={benchmarkSummary}
            onRefresh={fetchBenchmarkData}
            isRefreshing={isRefreshingBenchmarks}
            onReset={handleResetBenchmarks}
          />
        )}

        {currentPage === 'settings' && (
          <SettingsPage
            llmProvider={llmProvider}
            onSelectProvider={handleProviderSelect}
            geminiApiKey={geminiApiKey}
            onSaveGeminiKey={setGeminiApiKey}
            preferredLanguage={preferredLanguage}
            onSelectLanguage={setPreferredLanguage}
            silenceTimeoutMs={silenceTimeoutMs}
            onChangeSilenceTimeout={setSilenceTimeoutMs}
            onPurgeData={() => {
              setConversationHistory([]);
              handleResetBenchmarks();
            }}
          />
        )}
      </main>

      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        token={authToken}
        sessionId={sessionId}
        onNewToken={(t, s) => {
          setAuthToken(t);
          setSessionId(s);
          if (socketRef.current) socketRef.current.close();
          connectWebSocket(t);
        }}
      />
    </div>
  );
}

/**
 * VoiceSense AI — Typed WebSocket Hook (Protocol v1)
 * Handles connection lifecycle, exponential backoff, in-frame authentication,
 * language hints, and typed server event dispatch.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { getWsUrl } from '../lib/env';
import {
  WebSocketConnectionState,
  ServerMessage,
  SpeechResultMessage,
  VadMessage,
  StatusMessage,
  LlmDeltaMessage,
  LlmDoneMessage,
  RagSourcesMessage,
  TtsChunkMessage,
  TtsDoneMessage,
  ErrorMessage,
} from '../types/websocket';
import {
  parseServerMessage,
  createStartMessage,
  createStopMessage,
  createPingMessage,
} from '../services/protocol';

export interface UseWebSocketOptions {
  languageHint?: string | null;
  authToken?: string | null;
  sessionId?: string | null;
  onSpeechResult?: (result: SpeechResultMessage) => void;
  onVadState?: (vad: VadMessage) => void;
  onStatus?: (status: StatusMessage) => void;
  onLlmDelta?: (delta: LlmDeltaMessage) => void;
  onLlmDone?: (done: LlmDoneMessage) => void;
  onRagSources?: (sources: RagSourcesMessage) => void;
  onTtsChunk?: (chunk: TtsChunkMessage) => void;
  onTtsDone?: (done: TtsDoneMessage) => void;
  onError?: (err: ErrorMessage) => void;
  onBinaryMessage?: (buffer: ArrayBuffer) => void;
  onReady?: () => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const [connectionState, setConnectionState] =
    useState<WebSocketConnectionState>('disconnected');
  const [isServerReady, setIsServerReady] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const isManuallyClosedRef = useRef(false);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const cleanupSocket = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.onopen = null;
      socketRef.current.onclose = null;
      socketRef.current.onerror = null;
      socketRef.current.onmessage = null;
      if (
        socketRef.current.readyState === WebSocket.OPEN ||
        socketRef.current.readyState === WebSocket.CONNECTING
      ) {
        socketRef.current.close();
      }
      socketRef.current = null;
    }
  }, []);

  const sendStart = useCallback(
    (overrideOptions?: {
      language_hint?: string | null;
      auth_token?: string | null;
      session_id?: string | null;
    }) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        const lang =
          overrideOptions?.language_hint !== undefined
            ? overrideOptions.language_hint
            : optionsRef.current.languageHint;
        const token =
          overrideOptions?.auth_token !== undefined
            ? overrideOptions.auth_token
            : optionsRef.current.authToken;
        const sessId =
          overrideOptions?.session_id !== undefined
            ? overrideOptions.session_id
            : optionsRef.current.sessionId;

        const startMsg = createStartMessage({
          sample_rate: 16000,
          encoding: 'pcm_s16le',
          language_hint: lang,
          auth_token: token,
          session_id: sessId,
        });
        socketRef.current.send(JSON.stringify(startMsg));
      }
    },
    []
  );

  const connect = useCallback(() => {
    cleanupSocket();
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setConnectionState((prev) => (prev === 'disconnected' ? 'connecting' : 'reconnecting'));
    setLastError(null);

    // Strict Phase 9 rule: NO token in URL query parameter. Authentication is in-frame.
    const wsUrl = getWsUrl();

    try {
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        setConnectionState('connected');
        reconnectAttemptRef.current = 0;
        setLastError(null);

        // Send Protocol v1 start handshake with in-frame auth_token and language_hint
        const startMsg = createStartMessage({
          sample_rate: 16000,
          encoding: 'pcm_s16le',
          language_hint: optionsRef.current.languageHint ?? null,
          auth_token: optionsRef.current.authToken ?? null,
          session_id: optionsRef.current.sessionId ?? null,
        });
        ws.send(JSON.stringify(startMsg));
      };

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          const message: ServerMessage | null = parseServerMessage(event.data);
          if (!message) return;

          switch (message.type) {
            case 'ready':
              setIsServerReady(true);
              optionsRef.current.onReady?.();
              break;

            case 'vad':
              optionsRef.current.onVadState?.(message);
              break;

            case 'status':
              optionsRef.current.onStatus?.(message);
              break;

            case 'speech_result':
              optionsRef.current.onSpeechResult?.(message);
              break;

            case 'llm_delta':
              optionsRef.current.onLlmDelta?.(message);
              break;

            case 'llm_done':
              optionsRef.current.onLlmDone?.(message);
              break;

            case 'rag_sources':
              optionsRef.current.onRagSources?.(message);
              break;

            case 'tts_chunk':
              optionsRef.current.onTtsChunk?.(message);
              break;

            case 'tts_done':
              optionsRef.current.onTtsDone?.(message);
              break;

            case 'error':
              if (message.code !== 'llm_unavailable' && message.code !== 'tts_unavailable') {
                setLastError(`[${message.code}] ${message.message}`);
              }
              optionsRef.current.onError?.(message);
              break;

            case 'pong':
              // Keepalive acknowledged
              break;

            default:
              break;
          }
        } else if (event.data instanceof ArrayBuffer) {
          optionsRef.current.onBinaryMessage?.(event.data);
        }
      };

      ws.onerror = (evt) => {
        console.debug('[WebSocket] Connection error event:', evt);
      };

      ws.onclose = (event) => {
        setIsServerReady(false);
        socketRef.current = null;

        if (isManuallyClosedRef.current) {
          setConnectionState('disconnected');
          return;
        }

        setConnectionState('reconnecting');
        if (event.code === 1008) {
          setLastError('Authentication policy violation (close code 1008). Sign-in required.');
        }

        // Exponential backoff: min 1s, max 10s
        const backoffMs = Math.min(
          1000 * Math.pow(1.5, reconnectAttemptRef.current),
          10000
        );
        reconnectAttemptRef.current += 1;

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, backoffMs);
      };

      socketRef.current = ws;
    } catch (err: any) {
      setConnectionState('error');
      setLastError(err?.message || 'WebSocket initialization failed.');
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    }
  }, [cleanupSocket]);

  const sendAudioFrame = useCallback((buffer: ArrayBuffer) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(buffer);
      return true;
    }
    return false;
  }, []);

  const sendStop = useCallback(() => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(createStopMessage()));
    }
  }, []);

  const sendPing = useCallback(() => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(createPingMessage()));
    }
  }, []);

  const disconnect = useCallback(() => {
    isManuallyClosedRef.current = true;
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    cleanupSocket();
    setConnectionState('disconnected');
    setIsServerReady(false);
  }, [cleanupSocket]);

  useEffect(() => {
    isManuallyClosedRef.current = false;
    connect();

    return () => {
      isManuallyClosedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      cleanupSocket();
    };
  }, [connect, cleanupSocket]);

  return {
    connectionState,
    isServerReady,
    lastError,
    sendStart,
    sendAudioFrame,
    sendStop,
    sendPing,
    reconnect: connect,
    disconnect,
  };
}

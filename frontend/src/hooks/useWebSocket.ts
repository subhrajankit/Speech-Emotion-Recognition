/**
 * VoiceSense AI — Typed WebSocket Hook (Protocol v1)
 * Handles connect, reconnect with exponential backoff, typed protocol v1 framing,
 * and safe ignoring of reserved/unknown message types.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { getWsUrl, isAuthRequired } from '../lib/env';
import {
  WebSocketConnectionState,
  ServerMessage,
  SpeechResultMessage,
  VadMessage,
  ErrorMessage,
} from '../types/websocket';
import {
  parseServerMessage,
  createStartMessage,
  createStopMessage,
  createPingMessage,
} from '../services/protocol';
import { fetchAuthToken } from '../services/api';

export interface UseWebSocketOptions {
  onSpeechResult?: (result: SpeechResultMessage) => void;
  onVadState?: (vad: VadMessage) => void;
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

  const connect = useCallback(async () => {
    cleanupSocket();
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setConnectionState((prev) => (prev === 'disconnected' ? 'connecting' : 'reconnecting'));
    setLastError(null);

    let tokenParam = '';
    if (isAuthRequired()) {
      const token = await fetchAuthToken();
      if (token) {
        tokenParam = `?token=${encodeURIComponent(token)}`;
      }
    }

    const wsUrl = `${getWsUrl()}${tokenParam}`;

    try {
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        setConnectionState('connected');
        reconnectAttemptRef.current = 0;
        setLastError(null);

        // Send Protocol v1 start handshake
        const startMsg = createStartMessage();
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

            case 'speech_result':
              optionsRef.current.onSpeechResult?.(message);
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
              // Reserved messages (llm_delta, tts_chunk, etc.) are safely ignored
              console.debug('[WebSocket] Handled reserved/pass-through message:', message.type);
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
          setLastError('Authentication policy violation (close code 1008).');
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
    sendAudioFrame,
    sendStop,
    sendPing,
    reconnect: connect,
    disconnect,
  };
}

/**
 * VoiceSense AI — Service Health Poller Hook
 * Polls GET /api/health and reports subsystem status (asr, emotion, llm, rag, tts, db).
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { HealthResponse } from '../types/speech';
import { fetchHealth } from '../services/api';

const DEFAULT_OFFLINE_HEALTH: HealthResponse = {
  status: 'unhealthy',
  components: {
    asr: 'offline',
    emotion: 'offline',
    llm: 'offline',
    rag: 'offline',
    tts: 'offline',
    db: 'offline',
  },
  details: {
    message: 'Backend server is unreachable.',
  },
};

export function useHealthStatus(pollIntervalMs = 5000) {
  const [health, setHealth] = useState<HealthResponse>(DEFAULT_OFFLINE_HEALTH);
  const [isLoading, setIsLoading] = useState(true);
  const [isBackendReachable, setIsBackendReachable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);

  const checkHealth = useCallback(async () => {
    try {
      const data = await fetchHealth();
      if (!isMountedRef.current) return;
      setHealth(data);
      setIsBackendReachable(true);
      setError(null);
    } catch (err: any) {
      if (!isMountedRef.current) return;
      setHealth(DEFAULT_OFFLINE_HEALTH);
      setIsBackendReachable(false);
      setError(err?.message || 'Backend connection failed.');
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    checkHealth();

    const interval = setInterval(checkHealth, pollIntervalMs);
    return () => {
      isMountedRef.current = false;
      clearInterval(interval);
    };
  }, [checkHealth, pollIntervalMs]);

  return {
    health,
    isLoading,
    isBackendReachable,
    error,
    refresh: checkHealth,
  };
}

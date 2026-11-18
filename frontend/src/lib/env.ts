/**
 * VoiceSense AI — Environment Variables
 * Strict retrieval from Vite env (import.meta.env) with sensible local defaults.
 */

export const getApiUrl = (): string => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (typeof window !== 'undefined' && window.location) {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname || '127.0.0.1';
    return `${protocol}//${hostname}:8000`;
  }
  return 'http://127.0.0.1:8000';
};

export const getWsUrl = (): string => {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  if (typeof window !== 'undefined' && window.location) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const hostname = window.location.hostname || '127.0.0.1';
    return `${protocol}//${hostname}:8000/ws/speech`;
  }
  return 'ws://127.0.0.1:8000/ws/speech';
};

export const isAuthRequired = (): boolean => {
  return import.meta.env.VITE_AUTH_REQUIRED === 'true';
};

export const isAsrEnglishOnly = (): boolean => {
  return import.meta.env.VITE_ASR_ENGLISH_ONLY?.toLowerCase() !== 'false';
};

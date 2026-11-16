/**
 * VoiceSense AI — Environment Variables
 * Strict retrieval from Vite env (import.meta.env) with sensible local defaults.
 */

export const getApiUrl = (): string => {
  return import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
};

export const getWsUrl = (): string => {
  return import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/speech';
};

export const isAuthRequired = (): boolean => {
  return import.meta.env.VITE_AUTH_REQUIRED === 'true';
};

export const isAsrEnglishOnly = (): boolean => {
  return import.meta.env.VITE_ASR_ENGLISH_ONLY?.toLowerCase() !== 'false';
};

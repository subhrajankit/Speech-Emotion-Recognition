/**
 * VoiceSense AI — Null-Safe Display & Error Message Formatters
 * Pure utility functions.
 */

/**
 * Format emotion string with null-safe fallback.
 * Requirement 5: emotion/confidence null shows "-"; never "null" or NaN.
 */
export function formatEmotion(emotion: unknown): string {
  if (emotion === null || emotion === undefined || emotion === '' || emotion === 'null') {
    return '-';
  }
  const str = String(emotion).trim();
  if (str === '' || str.toLowerCase() === 'null') {
    return '-';
  }
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Format confidence number as percentage or null-safe fallback "-".
 * Requirement 5: emotion/confidence null shows "-"; never "null" or NaN.
 */
export function formatConfidence(confidence: unknown): string {
  if (confidence === null || confidence === undefined || confidence === 'null') {
    return '-';
  }
  const num = typeof confidence === 'number' ? confidence : Number(confidence);
  if (Number.isNaN(num) || !Number.isFinite(num)) {
    return '-';
  }
  return `${Math.round(num * 100)}%`;
}

/**
 * Maps protocol error codes to user-friendly messages.
 * Requirement 4: INFERENCE_ERROR, llm_unavailable, llm_bad_response,
 * tts_unavailable, rate limits, auth errors.
 */
export function formatErrorMessage(code: string, rawMessage?: string): string {
  switch (code) {
    case 'INFERENCE_ERROR':
      return 'Speech recognition error. Please check your audio input and try speaking again.';

    case 'llm_unavailable':
      return 'AI reasoning assistant is currently offline. Speech transcription and emotion analysis remain active.';

    case 'llm_bad_response':
      return 'The AI assistant generated an invalid or incomplete response. Please try repeating your query.';

    case 'tts_unavailable':
      return 'Voice reply synthesis is unavailable on this server. Text replies remain fully active.';

    case 'RATE_LIMIT_EXCEEDED':
      return 'Speech rate limit exceeded (maximum 20 utterances per minute). Please wait a moment before speaking.';

    case 'AUDIO_DURATION_LIMIT_EXCEEDED':
      return 'Speech duration limit exceeded (maximum 30 seconds per turn). Please keep utterances concise.';

    case 'AUTH_REQUIRED':
      return 'Authentication required. Please sign in or register to enable history persistence.';

    case 'AUTH_FAILED':
      return 'Authentication failed or token expired. Please sign in again.';

    case 'BUFFER_OVERFLOW':
      return 'Audio transmission buffer limit exceeded. Please restart the audio stream.';

    case 'UNAUTHORIZED':
    case 'FORBIDDEN':
      return 'Access denied. Please check your account credentials.';

    default:
      if (rawMessage && rawMessage.trim()) {
        return rawMessage.trim();
      }
      return `An unexpected error occurred (${code}).`;
  }
}


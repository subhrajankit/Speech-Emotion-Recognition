/**
 * Guards for incoming speech_result transcripts.
 *
 * The server emits a speech_result even when ASR finds no speech (empty
 * transcript, language "unknown"). Such results must not create conversation
 * turns or activate the assistant thinking state.
 */

export const NO_SPEECH_MESSAGE = 'No speech detected. Try speaking a little louder.';

/**
 * Returns true only when the transcript is a string containing non-whitespace
 * text. Missing, null, or non-string values are treated as no speech.
 */
export function hasSpeechTranscript(transcript: unknown): transcript is string {
  return typeof transcript === 'string' && transcript.trim().length > 0;
}

/**
 * Server `status` event state emitted when ASR confirms no speech
 * (speech_socket.py). Distinct from loading_model/model_ready statuses.
 */
export const NO_SPEECH_STATUS_STATE = 'no_speech';

export function isNoSpeechStatus(state: unknown): boolean {
  return state === NO_SPEECH_STATUS_STATE;
}

/**
 * Events that determine the no-speech notice state. Every event maps to an
 * absolute next value — unrelated WebSocket statuses never reach this
 * function, so they cannot clear the notice.
 */
export type NoSpeechNoticeEvent =
  | 'no_speech' // server status:no_speech or an empty speech_result transcript
  | 'valid_result' // non-empty speech_result arrived
  | 'recording_start' // user initiated a new recording attempt
  | 'dismiss' // user dismissed the notice
  | 'reset'; // logout / account switch / conversation reset

/**
 * Pure transition for the no-speech notice. Only 'no_speech' shows the
 * message; every other event clears it.
 */
export function noSpeechNoticeFor(event: NoSpeechNoticeEvent): string | null {
  return event === 'no_speech' ? NO_SPEECH_MESSAGE : null;
}

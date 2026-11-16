# 06 — Frontend Deep Dive

Stack: **React 18 + TypeScript + Vite**, Tailwind CSS, Vitest (24 test files).
Dev server `http://127.0.0.1:5173`, proxies/points at the FastAPI backend via
build-time env (`VITE_API_URL`, `VITE_WS_URL`, `VITE_AUTH_REQUIRED`,
`VITE_ASR_ENGLISH_ONLY` — see `src/lib/env.ts`).

## 1. Application shell (`src/App.tsx`)

`App` is the composition root. It owns all cross-cutting state and wires hooks:

- **Tabs**: `voice` | `history` | `settings`.
- **Auth state (in-memory only, never localStorage — XSS defense)**:
  `authToken`, `currentUser`, `isAuthModalOpen`, `serverRequiresAuth`.
  `lastUserIdRef` detects account switches → `resetLiveConversation()` wipes
  the previous user's live turns.
- **Perception state**: `transcript`, `detectedLanguage`, `emotion`,
  `confidence`, `latencies`, `audioEvents`, `vadHasSpeech`, `recordingElapsedSec`.
- **Assistant state**: `liveAssistantText`, `liveAssistantSources`,
  `isThinking`, `assistantErrorCode/Message`.
- **Notices**: `activeAlert` (danger/warning/info), `noSpeechNotice`,
  `announcement` (screen-reader live region with fresh node ids).
- **Model loading banner**: `isLoadingModel`/`loadingEngineName` from server
  `status` frames.

Message flow in `App`:

```text
useWebSocket callbacks ──► handleSpeechResult / handleVadState /
  handleStatus / handleLlmDelta / handleLlmDone / handleServerError /
  onBinaryMessage(→ enqueueChunk for TTS playback) / onAuthRejected
useAudioCapture.onAudioChunk ──► sendAudioFrame (binary WS)
recordingController ──► guarantees one `start` frame per session, sends
  `stop` on toggle, handles abort during permission prompt
useConversationHistory (store) ──► turns list rendered by
  TranscriptView / ResponseView / MultiSegmentTurns
```

Notable handlers:
- `handleSpeechResult` — guards empty transcripts (no turn, no stuck
  "thinking"), resolves display emotion (`EMO_UNKNOWN`→"Unknown"), adds a turn,
  announces to screen readers.
- `handleLlmDelta/Done` — accumulates streamed text, completes the turn,
  announces once at completion (never per-token).
- `handleServerError` — routes codes: auth errors → modal; assistant errors
  (`llm_*`, `tts_*`) → inline assistant error; discard-and-continue codes
  (duration cap/buffer overflow) → deduped warning, recording continues.
- `handleWsAuthRejected` — close-1008 path: clears dead credentials, opens
  auth modal; hook performs exactly one deferred anonymous reconnect.

## 2. WebSocket client (`src/hooks/useWebSocket.ts` + `src/services/protocol.ts`)

- Connects on mount to `getWsUrl()` (`ws://127.0.0.1:8000/ws/speech`).
- `ws.onopen` → immediately sends the `start` frame with `sample_rate`,
  `encoding`, `language_hint`, `auth_token`, `session_id` — **auth is in-frame,
  never in the URL** (comment in code: "Strict Phase 9 rule: NO token in URL
  query parameter").
- `parseServerMessage()` (`services/protocol.ts`) is a pure, typed parser for
  all 12 server message types + `RESERVED_MESSAGE_TYPES` guard.
- Reconnect: exponential backoff `min(1000 * 1.5^n, 10000)` ms; manual close →
  no reconnect; close 1008 → auth-rejection path (notify once, one deferred
  reconnect, then silent stop — `src/lib/wsClosePolicy.ts` decides).
- Exposes: `connectionState` (disconnected/connecting/connected/reconnecting/
  error), `isServerReady`, `sendStart/sendAudioFrame/sendStop/sendPing`,
  `reconnect`, `disconnect`.

## 3. Audio capture (`src/hooks/useAudioCapture.ts` + `src/lib/capturePipeline.ts` + `public/audio-processor.js`)

- `getUserMedia` → `AudioContext` → **AudioWorklet** (`audio-processor.js`)
  downsamples any device rate to **16 kHz mono PCM16**; `ScriptProcessorNode`
  fallback for old browsers.
- Emits `ArrayBuffer` chunks → `sendAudioFrame`.
- `classifyCaptureError()` maps `NotAllowedError`→permission_denied,
  `NotFoundError`→no_device, else unknown — surfaced as alerts.
- Abort-safe: `attemptRef` epoch guards async pipeline continuations so a
  cancelled start can't leak tracks/contexts into a newer attempt.
- Track `onended` mid-recording → `isUnexpectedCaptureTermination` →
  controller `stop()` releases state cleanly.

## 4. Audio playback (`src/hooks/useAudioPlayback.ts`)

- `onBinaryMessage` (binary WS frames) → WAV chunks queued → Web Audio
  API playback; `isPlaying` state; `stopPlayback` on new turns.
- Only active when the server actually sends `tts_chunk` (TTS disabled by
  default, so usually idle).

## 5. State store (`src/stores/conversationStore.ts`)

Custom hook-based store (no external state lib) for conversation turns:

```text
items: Turn[]  — each turn: speech result + streaming assistant text +
                 sources + status
addSpeechResult(turn)      appendLlmDelta(delta)     completeLlmTurn(text,sources)
setAssistantError(code)    cancelActiveStream()      clearHistory()
```

Turns are what `TranscriptView`/`ResponseView`/`MultiSegmentTurns` render —
multi-segment support shows each VAD utterance as its own turn with
`debug.segment_index` badges.

## 6. `src/lib/` — pure, unit-tested helpers (~20 modules)

Each exists because a real bug or requirement demanded it — good viva material:

| Module | Job |
|---|---|
| `env.ts` | Reads `VITE_*` build-time config (`getApiUrl`, `getWsUrl`, `isAuthRequired`, `isAsrEnglishOnly`) |
| `recordingController.ts` | State machine guaranteeing **exactly one `start` frame per recording session**, sent only when socket connected+ready; epoch-guarded abort; `isStarting()` for UI |
| `protocol.ts` (services) | Wire codec (see §2) |
| `wsClosePolicy.ts` | Maps close codes → manual / auth_rejected_notify / auth_rejected_silent / reconnect |
| `speechResult.ts` | `hasSpeechTranscript`, `noSpeechNoticeFor`, `isNoSpeechStatus` — the no-speech UX contract |
| `emotionDisplay.ts` | Maps raw emotion + `debug.raw_tags` → badge label ("Unknown" vs "-") |
| `announcements.ts` | Screen-reader live-region text per event type; fresh ids per announcement |
| `captureFailure.ts`, `connectionLoss.ts`, `utteranceDiscard.ts`, `assistantStatus.ts`, `micControl.ts` | Derive UI states/alerts from failure modes without fabricating state |
| `formatters.ts`, `httpErrors.ts`, `audio-utils.ts`, `requestSequencer.ts`, `focusTrap.ts`, `spaceShortcut.ts`, `onboarding.ts` | Misc UX: error text, typed HTTP errors, WAV utils, request ordering, a11y focus, spacebar-to-talk, first-run guide |

## 7. Components (`src/components/`)

Grouped by feature; all presentational + wired in `App.tsx`:

- **Voice**: `VoiceConsole`, `voice/VoiceStage`, `audio/MicrophoneControl`,
  `audio/WaveformVisualizer`, `audio/AudioPlayer` — mic button, level meter,
  recording timer, playback.
- **Transcript/response**: `transcript/TranscriptView`,
  `transcript/ResponseView`, `MultiSegmentTurns` — user/assistant turns,
  streaming text, RAG source badges, latency chips.
- **Emotion**: `emotion/EmotionBadge` — normalized emotion pill.
- **Status**: `StatusBanner` (model loading), `StatusDot`, `Alert`,
  `dashboard/ServiceStatusCard`, `dashboard/LatencyCard`,
  `dashboard/DashboardLayout`.
- **Auth/history**: `AuthModal` (login/register), `ConversationHistory`
  (session list + detail + delete-my-data), `DocumentManager` (RAG uploads —
  UI for the knowledge base), `rail/RecentConversations`,
  `rail/InsightsPanel`.
- **Pages/misc**: `LandingPage`, `Header`, `LanguageSelector` (Auto/English;
  Hindi only when multilingual build flag), `SettingsPage`,
  `SettingsPanel`, `FirstRunGuidance`, `ui/{Alert,Badge,StatusDot}`.

## 8. Testing (`src/tests/`)

24 Vitest files — every `lib/` helper, `protocol.ts` round-trips, the
conversation store, and key components (`auth-modal`, `language-selector`,
`microphone-control`, `first-run-guidance`, `emotion-display`, `alert`).
Run: `cd frontend && npm test -- --run && npx tsc --noEmit && npm run lint &&
npm run build`.

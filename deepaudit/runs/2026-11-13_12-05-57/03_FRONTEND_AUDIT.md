# 03 — Frontend Audit (`frontend/`, React 18 + TS + Vite)

## Entry & structure

`main.tsx` → `App.tsx` (445 lines) → `DashboardLayout` with two tabs: `voice` (console) and `history`. No router library — tab state only. `index.html` + `public/audio-processor.js` (AudioWorklet).

## Verified wiring

| Feature | Evidence | Status |
|---|---|---|
| Mic capture | `hooks/useAudioCapture.ts` — getUserMedia (mono, EC/NS/AGC), AudioWorklet `/audio-processor.js` → PCM16, ScriptProcessor fallback, RMS level, permission/device/disconnect errors, full cleanup | VERIFIED (code+tests) |
| WS client | `hooks/useWebSocket.ts` — reconnect w/ exp backoff (1.5^n, cap 10s), in-frame `auth_token`/`language_hint` in `start` frame (no token in URL — good), binary `arraybuffer`, typed dispatch for ready/vad/status/speech_result/llm_*/tts_*/error/pong | VERIFIED |
| Protocol | `services/protocol.ts` — `createStartMessage`, `createStopMessage`, `createPingMessage`, `parseServerMessage` | VERIFIED (17 Vitest tests) |
| REST | `services/api.ts` — health, register/login/me, history sessions/detail/delete/purge; Bearer tokens | VERIFIED |
| State | `stores/conversationStore.ts` — turns, `addSpeechResult`, `appendLlmDelta`, `completeLlmTurn`, `setAssistantError`, `clearHistory` | VERIFIED (store tests) |
| Env | `lib/env.ts` — `getApiUrl`/`getWsUrl`/`isAuthRequired` from `VITE_*` | VERIFIED |
| Health polling | `hooks/useHealthStatus.ts` → `GET /api/health` → `ServiceStatusCard`, `LatencyCard` | VERIFIED |
| Auth UI | `AuthModal.tsx` (491 lines) — register/login, in-memory token only (no localStorage — XSS-safe) | VERIFIED |
| History UI | `ConversationHistory.tsx` — fetch sessions/detail, delete, purge; renders real DB data | VERIFIED |
| TTS playback | `useAudioPlayback.ts` + `AudioPlayer` — enqueues binary WS chunks | VERIFIED (code path; runtime unverified) |
| Language selector | `LanguageSelector.tsx` — sends `language_hint` on change via `sendStart` | VERIFIED |

## Findings

1. **Dead components (confirmed no importer):** `AnalyticsDashboard.tsx` (238 lines), `DocumentManager.tsx` (207), `SettingsPage.tsx` (194 — contains Gemini API-key field), `LandingPage.tsx` (146), `Header.tsx` (110), `VoiceConsole.tsx` (176), `components/WaveformVisualizer.tsx` (1-line re-export). Only referenced by each other, never by `App.tsx`/`DashboardLayout`. **The dashboard analytics, document upload UI, settings, and landing page do not exist in the running app.** Severity: Medium.
2. `App.tsx:236,244,251` — `sendStart` on language change/auth/logout re-sends `start` without resetting server segmenter state semantics; acceptable but note each `start` resets VAD segmenter server-side.
3. `handleLanguageChange` calls `sendStart` even when socket not open — silently no-ops; language hint applied on next connect via optionsRef. OK.
4. Token kept in React state only — page refresh logs user out (intentional, documented as XSS protection). Trade-off noted.
5. `frontend/src/components/ui/` — `Alert`, `Badge`, `StatusDot` used; no other ui files exist.
6. No upload-audio-file UI anywhere — `/api/speech/upload` and `/api/predict` have **no frontend caller**. REST prediction endpoints are orphaned from the UI.
7. `vite.config.ts`, `tsconfig`, `package.json` standard; `npm run build` verified previously (1,901 modules). `dist/` committed (build artifact in repo — minor hygiene).
8. `src/frontend/` is a full older duplicate of the app (dead, quarantined).

## Audio interface specifics

- MIME/encoding: raw PCM16 mono 16kHz frames — matches backend `pcm_s16le` expectation. AudioWorklet does resampling; ScriptProcessor path calls `resampleTo16kPCM16` (`lib/audio-utils.ts`).
- No file-size limit needed (streaming); server enforces 5MB buffer + 30s utterance cap.
- Mic errors mapped to user-facing messages; mid-stream `track.onended` handled.
- Browser compat: AudioWorklet with ScriptProcessor fallback; `webkitAudioContext` handled.

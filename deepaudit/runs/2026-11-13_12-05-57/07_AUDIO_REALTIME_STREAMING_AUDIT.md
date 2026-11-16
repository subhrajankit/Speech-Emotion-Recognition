# 07 — Audio & Real-Time Streaming Audit

## Implementation level achieved: utterance-level streaming (level 4 of 6)

NOT continuous/frame-level SER. Pipeline: mic → PCM16 16kHz mono frames → WS binary → server VAD segmenter → on silence-timeout (700ms) → batch ASR+SER on the complete utterance → LLM stream → TTS sentence stream.

## Capture (frontend)

- `useAudioCapture.ts`: getUserMedia mono + EC/NS/AGC; AudioWorklet `public/audio-processor.js` preferred, ScriptProcessorNode fallback; both emit PCM16; `calculateRMS` drives waveform; errors: permission_denied/no_device/disconnected/unknown; `track.onended` mid-stream handled; full teardown on unmount.
- `lib/audio-utils.ts` `resampleTo16kPCM16` used only on ScriptProcessor path (AudioWorklet handles its own resample — verify inside audio-processor.js; not read in depth, flagged).

## Transport (`speech_socket.py`)

- Protocol v1: `start{sample_rate,encoding,language_hint,auth_token,session_id}` → `ready`; binary PCM16 frames; `stop` flushes; `ping`→`pong` (fast-path in `_message_pump`, lines 289-319, prevents uvicorn read-pausing).
- `VADSpeechSegmenter` (`ai/preprocessing/vad.py:196-308`): 512-sample frames, 250ms pre-padding ring, 700ms silence timeout → returns complete utterance; `flush()` on stop.
- Server VAD: Silero ONNX 32ms frames, stateful context; **silent fallback to RMS-energy heuristic** if ONNX missing/fails (`vad.py:84-86,101-104`) — degrades gracefully but changes behavior silently.
- Limits: 5MB/connection buffer, 30s max utterance, 20 utterances/min/session — all enforced, errors framed as JSON.

## Inference scheduling

- `transcribe_pcm16_bytes` → int16→float32 → `transcribe_array` → router → `asyncio.to_thread(engine.transcribe)` under `Semaphore(INFERENCE_CONCURRENCY_LIMIT=2)`; lazy engine load with `loading_model`/`model_ready` status events.
- Fallback: if routed engine fails → default SenseVoice (`speech_service.py:226-250`).

## Response path

`speech_result` (full SpeechResult + debug) → `handle_llm_turn` task → `rag_sources`?/`status rag_fallback` → `llm_delta`* → `llm_done` → `tts_chunk` header + binary WAV per sentence → `tts_done`. Barge-in: new turn cancels `active_llm_task`. History persisted in `finally` via `create_task` (fault-isolated).

## Findings

1. **Not real-time SER**: emotion is computed once per completed utterance, batch-style. No streaming partial results, no smoothing/windowing, no continuous emotion trace. Matches "near-real-time" only at utterance granularity.
2. **VAD inside engine too**: `SenseVoiceSpeechEngine.transcribe` re-runs `vad.analyze` on the already-VAD-segmented utterance — double VAD (redundant but harmless; segmenter already gated).
3. **Resampling quality**: `ai/preprocessing/audio.py:30-47` uses `np.interp` linear resampling for uploads — adequate for ASR but below polyphase quality; WebSocket path bypasses it (PCM assumed 16k).
4. Encoding assumption: WS binary treated as PCM16 regardless of declared `encoding` field — `encoding` from start frame is stored but never validated/used (`speech_socket.py:252,402`). Minor protocol gap.
5. `sample_rate` from start frame is trusted; segmenter math assumes PCM16 (÷2 hardcoded at lines 443,563) — a client declaring 8kHz would still be processed as 16k PCM. Low severity (own client only).
6. TTS audio is WAV-per-sentence; frontend `enqueueChunk` appends — gap/ordering handled by sentence_index; playback unverified at runtime.
7. No jitter buffer / sequence enforcement needed (TCP-like WS ordering guaranteed).

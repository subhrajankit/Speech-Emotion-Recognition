# 01 — Product Requirements Document (PRD)

## Project: SenseAI Voice Assistant

---

## 1. Executive Summary & Vision

SenseAI is a next-generation, private-by-design voice assistant operating entirely on consumer/prosumer local hardware. It combines state-of-the-art multilingual speech recognition, real-time emotion and audio event understanding, lightweight high-performance LLM reasoning, and expressive, emotion-conditioned text-to-speech synthesis.

Unlike cloud-dependent voice assistants (Alexa, Siri, Google Assistant) that compromise data privacy and impose recurring API costs or network latency, SenseAI delivers zero cloud egress, sub-second perceived response times, and native multilingual fluency across global languages and 22 scheduled Indian languages (plus Hinglish).

---

## 2. Target Users & Personas

### 2.1 Privacy-Conscious Individuals & Developers
- **Profile**: Engineers, privacy advocates, home automation enthusiasts.
- **Needs**: Complete assurance that voice recordings and private conversations never leave their local network or machine.
- **Pain Points**: Cloud vendor snooping, unpredictable cloud outages, vendor lock-in.

### 2.2 Multilingual & Indic Language Speakers
- **Profile**: Multilingual households, Indian vernacular users, and code-switching speakers (e.g., Hinglish).
- **Needs**: Natural understanding and conversational responses in native languages without awkward phonetic failures or forced English phrasing.
- **Pain Points**: Existing voice assistants fail dramatically on code-mixed speech, Indian accents, and non-English vernaculars.

### 2.3 Air-Gapped & Offline Organizations
- **Profile**: Healthcare clinics, defense/legal environments, field researchers, and maritime/remote deployments.
- **Needs**: Full speech-to-text, document retrieval (RAG), and vocal synthesis with zero internet connectivity.
- **Pain Points**: Cloud-only AI services cannot be certified for air-gapped compliance.

---

## 3. Product & User-Facing Goals

1. **True Conversational Flow**: End-to-end voice loop with natural turn-taking, fast voice activity detection, and streaming audio playback.
2. **Emotional & Acoustic Intelligence**: The assistant perceives emotional states (happy, angry, sad, neutral) and acoustic cues (laughter, sighs, coughing), adapting its response tone, phrasing, and vocal inflection accordingly.
3. **Indic Language First-Class Citizenship**: High-accuracy recognition and natural sounding speech for Hindi and all 21 other scheduled Indian languages, with robust heuristic handling for mixed Hinglish dialogue.
4. **Context-Aware Grounding (RAG)**: Users can query private local documents via vector search with factual, cited answers when explicitly requested.
5. **Zero Telemetry / Absolute Privacy**: No audio, transcripts, or vector queries are transmitted over the public internet.

---

## 4. User Journey & Core User Experience

1. **Initiation**: User opens the web client (React/Vite). The UI displays microphone status, audio visualizer, and connection health.
2. **Speaking**: User speaks in any supported language (e.g., English, Hindi, Hinglish, Mandarin, Japanese).
3. **Visual Feedback**: The interface visualizes incoming audio waves and instantly flags speech activity using real-time Silero VAD.
4. **Live Perception**: Transcribed text, detected speech emotion, and detected audio events (e.g., `[laughter]`, `[sigh]`) appear in real-time.
5. **Response Playback**: Assistant streams spoken audio back using Indic Parler-TTS, matching the conversational sentiment with natural pacing and emotion-appropriate inflection.
6. **Transcript & Context History**: Conversation history and emotion trajectories are visibly tracked in the session drawer for user review.

---

## 5. Success Criteria & Key Performance Indicators (KPIs)

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| **Local Privacy Guarantee** | 100% | Zero outbound network packets during active voice sessions (enforced via local binding). |
| **First-Audio-Out Latency (GPU)** | < 800 ms | Time from end of user speech (VAD silence trigger) to first synthesized audio chunk delivered to frontend. |
| **First-Audio-Out Latency (CPU)** | < 1,800 ms | Same as above under quantized CPU execution mode. |
| **ASR Word Error Rate (WER)** | < 10% (Global), < 15% (Indic/Hinglish) | Measured across test benchmark sets (Common Voice, Kathbath). |
| **Emotion Classification Accuracy** | > 80% macro-F1 | Evaluated on standard SER benchmark datasets against human ground truth. |
| **Turn-Taking Fluidity** | < 300 ms false barge-in | VAD silence hangover accurately differentiates mid-sentence pauses from turn completion. |

---

## 6. Out-of-Scope (OOS) for Initial Releases

The following capabilities are deliberately excluded from early development phases:

- **No Cloud Fallbacks or Cloud APIs**: No optional OpenAI, Google Speech, or ElevenLabs connectors. Pure local execution only.
- **No Complex Orchestration Clusters**: No Kubernetes, Kafka message buses, Redis clusters, or distributed multi-node LLM serving.
- **No WebTransport before Phase 9**: WebSocket is the strictly mandated transport for MVP. WebTransport/HTTP3 is evaluated only in Phase 9.
- **No Continuous RAG Ingestion by Default**: RAG is strictly intent-gated. The assistant will not perform vector lookups on standard conversational small-talk.
- **No Smart Home Device Control Mesh**: Home Assistant / Matter / Zigbee integrations are deferred until after the core conversational loop stabilizes.
- **No Multi-User Voiceprint Biometrics**: Voice recognition will treat the active speaker as the primary session user without acoustic biometric profiling in the initial releases.

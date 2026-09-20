# 04 — Data Model & Context Specifications

## Project: SenseAI Voice Assistant

This document defines the core data schemas, linguistic context payloads, and database entity models utilized across the SenseAI voice pipeline.

---

## 1. Speech Context Object (`AudioContext`)

The `AudioContext` object is emitted by the `LanguageRouter` in the ASR perception stage and passed through the downstream Intent Router, LLM reasoner, and TTS synthesizers.

### JSON Schema Specification

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AudioContext",
  "type": "object",
  "required": [
    "language",
    "script",
    "mixed_language",
    "transcript",
    "confidence",
    "model_used"
  ],
  "properties": {
    "language": {
      "type": "string",
      "description": "ISO language code ('en', 'hi', 'zh', 'ja', 'ko', 'yue') or 'hinglish'",
      "examples": ["en", "hi", "hinglish", "zh"]
    },
    "script": {
      "type": "string",
      "enum": ["latin", "devanagari", "hanzi", "japanese", "hangul", "unknown"],
      "description": "Primary orthographic script of the transcription"
    },
    "mixed_language": {
      "type": "boolean",
      "description": "True if code-switching or mixed linguistic patterns are detected"
    },
    "transcript": {
      "type": "string",
      "description": "Cleaned recognized text"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Posterior confidence score from ASR / heuristic classification"
    },
    "model_used": {
      "type": "string",
      "enum": ["sensevoice", "indicconformer", "hinglish_heuristic", "none"],
      "description": "Underlying engine that produced or finalized the transcription"
    }
  }
}
```

### Python DataClass Definition

```python
from dataclasses import dataclass, asdict
from typing import Dict, Any

@dataclass
class AudioContext:
    language: str           # 'en', 'hi', 'hinglish', etc.
    script: str             # 'latin', 'devanagari', etc.
    mixed_language: bool    # True when code-mixing is present
    transcript: str         # Recognized text
    confidence: float       # Confidence score [0.0 - 1.0]
    model_used: str         # 'sensevoice', 'indicconformer', 'hinglish_heuristic'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
```

---

## 2. WebSocket Streaming Message Protocols

### 2.1 Server-to-Client `result` Frame

Emitted after speech segmentation, transcription, reasoning, and synthesis:

```json
{
  "type": "result",
  "transcript": "bhai what is the plan aaj ka?",
  "response_text": "Aaj ka plan simple hai: complete Phase 3 testing and verify everything locally.",
  "latencies": {
    "asr_ms": 112.5,
    "llm_ms": 184.2,
    "tts_ms": 230.1,
    "total_ms": 526.8
  },
  "context": {
    "language": "hinglish",
    "script": "latin",
    "mixed_language": true,
    "transcript": "bhai what is the plan aaj ka?",
    "confidence": 0.72,
    "model_used": "hinglish_heuristic"
  }
}
```

---

## 3. Database Entities (Dev SQLite / Prod PostgreSQL)

### 3.1 `sessions` Table
- `id`: UUID (Primary Key)
- `created_at`: TIMESTAMP WITH TIME ZONE
- `updated_at`: TIMESTAMP WITH TIME ZONE
- `primary_language`: VARCHAR(16)

### 3.2 `utterances` Table
- `id`: UUID (Primary Key)
- `session_id`: UUID (Foreign Key -> sessions.id)
- `user_transcript`: TEXT
- `assistant_response`: TEXT
- `language`: VARCHAR(16)
- `script`: VARCHAR(32)
- `mixed_language`: BOOLEAN
- `asr_confidence`: FLOAT
- `created_at`: TIMESTAMP WITH TIME ZONE

### 3.3 Audio Persistence Invariant
- Raw audio buffers (`.wav`, `.pcm`, `.mp3`) are NEVER stored in database tables or file system caches.
- Processing occurs entirely in transient memory buffers purged immediately upon utterance completion.

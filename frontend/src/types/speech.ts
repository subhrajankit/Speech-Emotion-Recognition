/**
 * VoiceSense AI — Domain Speech & Perception Types
 */

export type ComponentStatus =
  | 'ok'
  | 'degraded'
  | 'unhealthy'
  | 'not_configured'
  | 'offline';

export interface HealthComponents {
  asr: ComponentStatus;
  emotion: ComponentStatus;
  llm: ComponentStatus;
  rag: ComponentStatus;
  tts: ComponentStatus;
  db: ComponentStatus;
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'unhealthy';
  components: HealthComponents;
  details?: {
    model_version?: string;
    concurrency_limit?: number;
    [key: string]: any;
  };
}

export interface SpeechResult {
  transcript: string;
  language: string;
  emotion: string | null;
  confidence: number | null;
  processing_time_ms: number;
  model_version?: string;
  audio_events?: string[];
  segments?: any[];
  debug?: Record<string, any>;
}

export interface LatencyMetrics {
  asr_ms?: number;
  total_ms?: number;
}

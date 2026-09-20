/**
 * VoiceSense AI — Conversation History Types
 */

export interface HistoryItem {
  id: string;
  timestamp: number;
  transcript: string;
  language: string;
  emotion: string | null;
  confidence: number | null;
  processing_time_ms: number;
  audioEvents?: string[];
}

/**
 * VoiceSense AI — Conversation History Store
 * In-memory store supporting multi-segment utterance rows, streaming assistant replies,
 * and isolated speech/LLM error handling.
 */

import { useState, useEffect } from 'react';
import { HistoryItem } from '../types/history';

export interface UtteranceTurn extends HistoryItem {
  assistantText?: string;
  isStreaming?: boolean;
  sources?: any[];
  assistantError?: string | null;
}

type Listener = (items: UtteranceTurn[]) => void;

class ConversationStore {
  private items: UtteranceTurn[] = [];
  private listeners: Set<Listener> = new Set();
  private maxItems = 100;
  private activeTurnId: string | null = null;

  public getItems(): UtteranceTurn[] {
    return [...this.items];
  }

  public getActiveTurnId(): string | null {
    return this.activeTurnId;
  }

  /**
   * Adds an utterance row for a new speech segment.
   * Requirement 2: each speech_result is its own utterance row (segment_index from debug when present).
   */
  public addSpeechResult(payload: {
    transcript: string;
    language: string;
    emotion: string | null;
    confidence: number | null;
    processing_time_ms: number;
    audioEvents?: string[];
    segmentIndex?: number;
    id?: string;
  }): UtteranceTurn {
    const turnId =
      payload.id ||
      `turn_${Date.now()}_seg${payload.segmentIndex ?? 1}_${Math.random().toString(36).slice(2, 6)}`;

    const newTurn: UtteranceTurn = {
      id: turnId,
      timestamp: Date.now(),
      transcript: payload.transcript.trim(),
      language: payload.language,
      emotion: payload.emotion,
      confidence: payload.confidence,
      processing_time_ms: payload.processing_time_ms,
      audioEvents: payload.audioEvents,
      segmentIndex: payload.segmentIndex,
      assistantText: '',
      isStreaming: true,
      sources: [],
      assistantError: null,
    };

    this.activeTurnId = turnId;
    this.items = [newTurn, ...this.items].slice(0, this.maxItems);
    this.notify();
    return newTurn;
  }

  /**
   * Appends an incoming LLM token delta to the active turn.
   */
  public appendLlmDelta(delta: string, turnId?: string): void {
    const targetId = turnId || this.activeTurnId;
    if (!targetId) return;

    const item = this.items.find((i) => i.id === targetId);
    if (item) {
      item.assistantText = (item.assistantText || '') + delta;
      item.isStreaming = true;
      this.notify();
    }
  }

  /**
   * Finalizes the LLM reply for the active turn.
   */
  public completeLlmTurn(text: string, sources?: any[], turnId?: string): void {
    const targetId = turnId || this.activeTurnId;
    if (!targetId) return;

    const item = this.items.find((i) => i.id === targetId);
    if (item) {
      item.assistantText = text || item.assistantText || '';
      item.isStreaming = false;
      if (sources && sources.length > 0) {
        item.sources = sources;
      }
      this.notify();
    }
  }

  /**
   * Sets assistant error on turn while leaving transcript & emotion intact.
   * Requirement 4: Transcript and emotion must still render when the LLM or TTS fails.
   */
  public setAssistantError(errorMsg: string, turnId?: string): void {
    const targetId = turnId || this.activeTurnId;
    if (!targetId) return;

    const item = this.items.find((i) => i.id === targetId);
    if (item) {
      item.assistantError = errorMsg;
      item.isStreaming = false;
      this.notify();
    }
  }

  /**
   * Marks the active turn as no longer streaming without fabricating a
   * completion — used when the connection drops mid-response. Preserves the
   * transcript, emotion, and any partial assistant text already received.
   * Returns true when a streaming turn was actually finalized.
   */
  public cancelActiveStream(): boolean {
    if (!this.activeTurnId) return false;
    const item = this.items.find((i) => i.id === this.activeTurnId);
    if (!item || !item.isStreaming) return false;
    item.isStreaming = false;
    this.notify();
    return true;
  }

  /**
   * Backwards compatible addItem method.
   */
  public addItem(
    item: Omit<HistoryItem, 'id' | 'timestamp'> & { id?: string; timestamp?: number }
  ): UtteranceTurn {
    return this.addSpeechResult({
      transcript: item.transcript,
      language: item.language,
      emotion: item.emotion,
      confidence: item.confidence,
      processing_time_ms: item.processing_time_ms,
      audioEvents: item.audioEvents,
      id: item.id,
      segmentIndex: item.segmentIndex,
    });
  }

  public clear(): void {
    this.items = [];
    this.activeTurnId = null;
    this.notify();
  }

  public subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.getItems());
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    const current = this.getItems();
    this.listeners.forEach((listener) => listener(current));
  }
}

export const conversationStore = new ConversationStore();

/**
 * React hook to bind components to conversationStore updates.
 */
export function useConversationHistory() {
  const [items, setItems] = useState<UtteranceTurn[]>(conversationStore.getItems());

  useEffect(() => {
    return conversationStore.subscribe(setItems);
  }, []);

  return {
    items,
    addSpeechResult: (payload: Parameters<ConversationStore['addSpeechResult']>[0]) =>
      conversationStore.addSpeechResult(payload),
    appendLlmDelta: (delta: string, turnId?: string) =>
      conversationStore.appendLlmDelta(delta, turnId),
    completeLlmTurn: (text: string, sources?: any[], turnId?: string) =>
      conversationStore.completeLlmTurn(text, sources, turnId),
    setAssistantError: (errorMsg: string, turnId?: string) =>
      conversationStore.setAssistantError(errorMsg, turnId),
    cancelActiveStream: () => conversationStore.cancelActiveStream(),
    addItem: (item: Omit<HistoryItem, 'id' | 'timestamp'>) =>
      conversationStore.addItem(item),
    clearHistory: () => conversationStore.clear(),
  };
}

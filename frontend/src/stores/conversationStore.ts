/**
 * VoiceSense AI — Conversation History Store
 * In-memory store with observer pattern and a clear seam for Phase 9 backend sync.
 */

import { useState, useEffect } from 'react';
import { HistoryItem } from '../types/history';
import { fetchRemoteHistory } from '../services/api';

type Listener = (items: HistoryItem[]) => void;

class ConversationStore {
  private items: HistoryItem[] = [];
  private listeners: Set<Listener> = new Set();
  private maxItems = 100;

  public getItems(): HistoryItem[] {
    return [...this.items];
  }

  public addItem(item: Omit<HistoryItem, 'id' | 'timestamp'> & { id?: string; timestamp?: number }): HistoryItem {
    const newItem: HistoryItem = {
      id: item.id || `turn_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      timestamp: item.timestamp || Date.now(),
      transcript: item.transcript.trim(),
      language: item.language,
      emotion: item.emotion,
      confidence: item.confidence,
      processing_time_ms: item.processing_time_ms,
      audioEvents: item.audioEvents,
    };

    // Prepend new item (newest first)
    this.items = [newItem, ...this.items].slice(0, this.maxItems);
    this.notify();
    return newItem;
  }

  public clear(): void {
    this.items = [];
    this.notify();
  }

  public subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.getItems());
    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Phase 9 Seam: Sync with /api/history when backend endpoint is available.
   */
  public async syncWithBackend(): Promise<void> {
    const remote = await fetchRemoteHistory();
    if (remote && Array.isArray(remote)) {
      this.items = remote;
      this.notify();
    }
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
  const [items, setItems] = useState<HistoryItem[]>(conversationStore.getItems());

  useEffect(() => {
    return conversationStore.subscribe(setItems);
  }, []);

  return {
    items,
    addItem: (item: Omit<HistoryItem, 'id' | 'timestamp'>) => conversationStore.addItem(item),
    clearHistory: () => conversationStore.clear(),
    syncWithBackend: () => conversationStore.syncWithBackend(),
  };
}

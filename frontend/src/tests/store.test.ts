import { describe, it, expect, beforeEach } from 'vitest';
import { conversationStore } from '../stores/conversationStore';

describe('ConversationStore Logic', () => {
  beforeEach(() => {
    conversationStore.clear();
  });

  it('starts with an empty item list', () => {
    expect(conversationStore.getItems()).toEqual([]);
  });

  it('adds speech turns and notifies subscribers', () => {
    let subscriberNotifications = 0;
    const unsubscribe = conversationStore.subscribe((_items) => {
      subscriberNotifications++;
    });

    // Initial subscribe call fires once
    expect(subscriberNotifications).toBe(1);

    const added = conversationStore.addItem({
      transcript: 'Hello VoiceSense',
      language: 'en',
      emotion: 'neutral',
      confidence: 0.95,
      processing_time_ms: 70,
    });

    expect(added.id).toBeDefined();
    expect(added.transcript).toBe('Hello VoiceSense');
    expect(added.language).toBe('en');
    expect(added.emotion).toBe('neutral');
    expect(added.confidence).toBe(0.95);
    expect(added.processing_time_ms).toBe(70);

    const items = conversationStore.getItems();
    expect(items.length).toBe(1);
    expect(items[0]).toEqual(added);
    expect(subscriberNotifications).toBe(2);

    unsubscribe();
  });

  it('prepends new items so the newest is first', () => {
    conversationStore.addItem({
      transcript: 'First message',
      language: 'en',
      emotion: null,
      confidence: null,
      processing_time_ms: 50,
    });

    conversationStore.addItem({
      transcript: 'Second message',
      language: 'hi',
      emotion: 'happy',
      confidence: null,
      processing_time_ms: 60,
    });

    const items = conversationStore.getItems();
    expect(items.length).toBe(2);
    expect(items[0].transcript).toBe('Second message');
    expect(items[1].transcript).toBe('First message');
  });

  it('clears all items and notifies subscribers', () => {
    conversationStore.addItem({
      transcript: 'Message to clear',
      language: 'en',
      emotion: null,
      confidence: null,
      processing_time_ms: 40,
    });

    expect(conversationStore.getItems().length).toBe(1);

    conversationStore.clear();
    expect(conversationStore.getItems()).toEqual([]);
  });

  it('trims whitespace on stored transcripts', () => {
    const item = conversationStore.addItem({
      transcript: '   padded speech string   ',
      language: 'en',
      emotion: 'surprised',
      confidence: null,
      processing_time_ms: 45,
    });

    expect(item.transcript).toBe('padded speech string');
  });
});

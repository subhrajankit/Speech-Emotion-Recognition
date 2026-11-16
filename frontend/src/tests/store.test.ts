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

  it('clear() also resets the active turn pointer so no stale turn can be targeted', () => {
    conversationStore.addSpeechResult({
      transcript: 'Turn to wipe',
      language: 'en',
      emotion: 'happy',
      confidence: null,
      processing_time_ms: 50,
      segmentIndex: 1,
    });
    conversationStore.appendLlmDelta('partial');

    conversationStore.clear();

    // A subsequent delta must not resurrect or append to the wiped turn.
    conversationStore.appendLlmDelta('ghost text');
    expect(conversationStore.getItems()).toEqual([]);
    expect(conversationStore.getActiveTurnId()).toBeNull();
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

  describe('Multi-Segment Turns & Assistant Reply Streaming', () => {
    it('records each speech_result as an individual utterance row with segment_index', () => {
      const seg1 = conversationStore.addSpeechResult({
        transcript: 'First utterance segment',
        language: 'hi',
        emotion: 'happy',
        confidence: null,
        processing_time_ms: 80,
        segmentIndex: 1,
      });

      const seg2 = conversationStore.addSpeechResult({
        transcript: 'Second utterance segment',
        language: 'hi',
        emotion: 'neutral',
        confidence: null,
        processing_time_ms: 95,
        segmentIndex: 2,
      });

      const items = conversationStore.getItems();
      expect(items.length).toBe(2);
      expect(items[0].id).toBe(seg2.id);
      expect(items[0].segmentIndex).toBe(2);
      expect(items[1].id).toBe(seg1.id);
      expect(items[1].segmentIndex).toBe(1);
    });

    it('streams LLM tokens into the active turn via appendLlmDelta and completeLlmTurn', () => {
      conversationStore.addSpeechResult({
        transcript: 'Tell me a joke',
        language: 'en',
        emotion: 'happy',
        confidence: 0.9,
        processing_time_ms: 65,
        segmentIndex: 1,
      });

      conversationStore.appendLlmDelta('Why did the chicken ');
      conversationStore.appendLlmDelta('cross the road?');

      let current = conversationStore.getItems()[0];
      expect(current.assistantText).toBe('Why did the chicken cross the road?');
      expect(current.isStreaming).toBe(true);

      const citations = [{ doc_name: 'jokes.md', chunk_id: 'c1', score: 0.99 }];
      conversationStore.completeLlmTurn('Why did the chicken cross the road? To get to the other side.', citations);

      current = conversationStore.getItems()[0];
      expect(current.assistantText).toBe('Why did the chicken cross the road? To get to the other side.');
      expect(current.isStreaming).toBe(false);
      expect(current.sources).toEqual(citations);
    });

    it('preserves user transcript and emotion when assistant encounters an error', () => {
      const turn = conversationStore.addSpeechResult({
        transcript: 'What is the refund policy?',
        language: 'en',
        emotion: 'sad',
        confidence: null,
        processing_time_ms: 72,
        segmentIndex: 1,
      });

      // LLM fails
      conversationStore.setAssistantError('llm_unavailable');

      const updated = conversationStore.getItems()[0];
      expect(updated.id).toBe(turn.id);
      // User transcript and emotion remain fully intact
      expect(updated.transcript).toBe('What is the refund policy?');
      expect(updated.emotion).toBe('sad');
      expect(updated.confidence).toBeNull();
      // Assistant error recorded
      expect(updated.assistantError).toBe('llm_unavailable');
      expect(updated.isStreaming).toBe(false);
    });
  });

  describe('cancelActiveStream — connection-loss finalization', () => {
    it('clears isStreaming while preserving transcript, emotion, and partial reply', () => {
      conversationStore.addSpeechResult({
        transcript: 'What is the refund policy?',
        language: 'en',
        emotion: 'sad',
        confidence: null,
        processing_time_ms: 72,
        segmentIndex: 1,
      });

      conversationStore.appendLlmDelta('Partial reply that was cut off');
      expect(conversationStore.getItems()[0].isStreaming).toBe(true);

      const cancelled = conversationStore.cancelActiveStream();
      expect(cancelled).toBe(true);

      const turn = conversationStore.getItems()[0];
      expect(turn.isStreaming).toBe(false);
      expect(turn.transcript).toBe('What is the refund policy?');
      expect(turn.emotion).toBe('sad');
      expect(turn.assistantText).toBe('Partial reply that was cut off');
      // No fabricated completion or error was injected.
      expect(turn.assistantError).toBeNull();
    });

    it('no-ops safely when there is no active turn', () => {
      expect(conversationStore.cancelActiveStream()).toBe(false);
      expect(conversationStore.getItems()).toEqual([]);
    });

    it('no-ops when the active turn is not streaming', () => {
      conversationStore.addSpeechResult({
        transcript: 'Done turn',
        language: 'en',
        emotion: null,
        confidence: null,
        processing_time_ms: 50,
        segmentIndex: 1,
      });
      conversationStore.completeLlmTurn('Full reply.');

      expect(conversationStore.cancelActiveStream()).toBe(false);
      const turn = conversationStore.getItems()[0];
      expect(turn.isStreaming).toBe(false);
      expect(turn.assistantText).toBe('Full reply.');
    });
  });
});

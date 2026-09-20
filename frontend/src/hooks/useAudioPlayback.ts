/**
 * VoiceSense AI — Web Audio Playback Queue
 * Stays idle in Phase 3 until Phase 8 sends tts_chunk frames.
 */

import { useState, useRef, useCallback, useEffect } from 'react';

export function useAudioPlayback() {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      audioContextRef.current = new AudioCtx();
    }
    return audioContextRef.current;
  }, []);

  const playNext = useCallback(async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }

    const chunk = audioQueueRef.current.shift();
    if (!chunk) {
      playNext();
      return;
    }

    try {
      const ctx = getAudioContext();
      if (ctx.state === 'suspended') {
        await ctx.resume();
      }

      // decodeAudioData consumes chunk; slice to make an isolated copy
      const audioBuffer = await ctx.decodeAudioData(chunk.slice(0));
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      currentSourceRef.current = source;

      source.onended = () => {
        currentSourceRef.current = null;
        playNext();
      };

      isPlayingRef.current = true;
      setIsPlaying(true);
      source.start();
    } catch (err) {
      console.warn('[AudioPlayback] Failed to decode audio chunk:', err);
      // Advance to next chunk on decode failure
      playNext();
    }
  }, [getAudioContext]);

  const enqueueChunk = useCallback(
    (chunk: ArrayBuffer) => {
      audioQueueRef.current.push(chunk);
      if (!isPlayingRef.current) {
        playNext();
      }
    },
    [playNext]
  );

  const stopPlayback = useCallback(() => {
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop();
      } catch {
        // Ignore if already stopped
      }
      currentSourceRef.current = null;
    }
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    setIsPlaying(false);
  }, []);

  useEffect(() => {
    return () => {
      stopPlayback();
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, [stopPlayback]);

  return {
    isPlaying,
    enqueueChunk,
    stopPlayback,
  };
}

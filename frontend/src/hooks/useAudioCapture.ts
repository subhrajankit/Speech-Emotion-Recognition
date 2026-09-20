/**
 * VoiceSense AI — Audio Capture Hook
 * getUserMedia + AudioWorklet downsampling to 16 kHz mono signed 16-bit PCM.
 * Handles permission denied, no device, and mid-stream disconnect.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { resampleTo16kPCM16, calculateRMS } from '../lib/audio-utils';

export type AudioCaptureErrorType =
  | 'permission_denied'
  | 'no_device'
  | 'disconnected'
  | 'unknown';

export interface UseAudioCaptureOptions {
  onAudioChunk?: (chunk: ArrayBuffer) => void;
  onError?: (type: AudioCaptureErrorType, message: string) => void;
}

export function useAudioCapture(options: UseAudioCaptureOptions = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorType, setErrorType] = useState<AudioCaptureErrorType | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const scriptNodeRef = useRef<ScriptProcessorNode | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const cleanup = useCallback(() => {
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.disconnect();
      } catch (e) {
        console.debug('[AudioCapture] Disconnect error (ignored):', e);
      }
      workletNodeRef.current = null;
    }

    if (scriptNodeRef.current) {
      try {
        scriptNodeRef.current.disconnect();
      } catch (e) {
        console.debug('[AudioCapture] Disconnect error (ignored):', e);
      }
      scriptNodeRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => {
        track.onended = null;
        track.stop();
      });
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    setIsRecording(false);
    setAudioLevel(0);
  }, []);

  const startRecording = useCallback(async () => {
    cleanup();
    setErrorMessage(null);
    setErrorType(null);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      const msg = 'Audio recording is not supported in this browser environment.';
      setErrorType('unknown');
      setErrorMessage(msg);
      optionsRef.current.onError?.('unknown', msg);
      return false;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;
    } catch (err: any) {
      let type: AudioCaptureErrorType = 'unknown';
      let msg = 'Could not access the microphone.';

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        type = 'permission_denied';
        msg = 'Microphone permission was denied. Please allow microphone access.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        type = 'no_device';
        msg = 'No audio recording device was found on this system.';
      }

      setErrorType(type);
      setErrorMessage(msg);
      optionsRef.current.onError?.(type, msg);
      return false;
    }

    // Monitor for mid-stream hardware or permission disconnection
    const audioTrack = stream.getAudioTracks()[0];
    if (audioTrack) {
      audioTrack.onended = () => {
        cleanup();
        const type: AudioCaptureErrorType = 'disconnected';
        const msg = 'Microphone was disconnected during active recording.';
        setErrorType(type);
        setErrorMessage(msg);
        optionsRef.current.onError?.(type, msg);
      };
    }

    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);

      // Try AudioWorklet first
      let workletSupported = false;
      if (audioCtx.audioWorklet) {
        try {
          await audioCtx.audioWorklet.addModule('/audio-processor.js');
          const workletNode = new AudioWorkletNode(audioCtx, 'pcm16-worklet-processor');
          workletNode.port.onmessage = (e) => {
            const buffer: ArrayBuffer = e.data;
            if (buffer && buffer.byteLength > 0) {
              const pcmView = new Int16Array(buffer);
              setAudioLevel(calculateRMS(pcmView));
              optionsRef.current.onAudioChunk?.(buffer);
            }
          };
          source.connect(workletNode);
          workletNode.connect(audioCtx.destination);
          workletNodeRef.current = workletNode;
          workletSupported = true;
        } catch (workletErr) {
          console.warn('[AudioCapture] AudioWorklet setup failed, falling back to ScriptProcessor:', workletErr);
        }
      }

      // Fallback: ScriptProcessorNode
      if (!workletSupported) {
        const scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);
        scriptNode.onaudioprocess = (audioProcessingEvent) => {
          const inputData = audioProcessingEvent.inputBuffer.getChannelData(0);
          setAudioLevel(calculateRMS(inputData));

          const pcm16 = resampleTo16kPCM16(inputData, audioCtx.sampleRate);
          if (pcm16.length > 0) {
            optionsRef.current.onAudioChunk?.(pcm16.buffer as ArrayBuffer);
          }
        };
        source.connect(scriptNode);
        scriptNode.connect(audioCtx.destination);
        scriptNodeRef.current = scriptNode;
      }

      setIsRecording(true);
      return true;
    } catch (err: any) {
      cleanup();
      const msg = `Failed to initialize audio processing pipeline: ${err?.message || err}`;
      setErrorType('unknown');
      setErrorMessage(msg);
      optionsRef.current.onError?.('unknown', msg);
      return false;
    }
  }, [cleanup]);

  const stopRecording = useCallback(() => {
    cleanup();
  }, [cleanup]);

  const toggleRecording = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    isRecording,
    audioLevel,
    errorMessage,
    errorType,
    startRecording,
    stopRecording,
    toggleRecording,
    clearError: () => {
      setErrorMessage(null);
      setErrorType(null);
    },
  };
}

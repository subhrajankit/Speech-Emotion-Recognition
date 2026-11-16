/**
 * VoiceSense AI — Audio Capture Hook
 * getUserMedia + AudioWorklet downsampling to 16 kHz mono signed 16-bit PCM.
 * Handles permission denied, no device, mid-stream disconnect, and
 * controller-driven cancellation of pending starts.
 *
 * The capture pipeline itself lives in lib/capturePipeline.ts (injectable,
 * unit-testable); this hook owns React state and error surfacing.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import {
  startCapturePipeline,
  CaptureSession,
  CaptureStream,
} from '../lib/capturePipeline';

export type AudioCaptureErrorType =
  | 'permission_denied'
  | 'no_device'
  | 'disconnected'
  | 'unknown';

export interface UseAudioCaptureOptions {
  onAudioChunk?: (chunk: ArrayBuffer) => void;
  onError?: (type: AudioCaptureErrorType, message: string) => void;
}

export interface StartRecordingOptions {
  /**
   * Reports whether the recording start was cancelled while pending (e.g. the
   * recording controller's epoch changed). Checked after the permission
   * prompt resolves and again before going live: on abort, granted tracks are
   * released immediately and no AudioContext/worklet/audio is produced.
   */
  shouldAbort?: () => boolean;
}

function classifyCaptureError(err: any): { type: AudioCaptureErrorType; message: string } {
  if (err?.name === 'NotAllowedError' || err?.name === 'PermissionDeniedError') {
    return {
      type: 'permission_denied',
      message: 'Microphone permission was denied. Please allow microphone access.',
    };
  }
  if (err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError') {
    return {
      type: 'no_device',
      message: 'No audio recording device was found on this system.',
    };
  }
  return { type: 'unknown', message: 'Could not access the microphone.' };
}

export function useAudioCapture(options: UseAudioCaptureOptions = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorType, setErrorType] = useState<AudioCaptureErrorType | null>(null);

  const sessionRef = useRef<CaptureSession | null>(null);
  // Incremented by every cleanup()/new start: an async pipeline continuation
  // from an older attempt sees isStale()===true and cannot touch resources
  // belonging to a newer attempt.
  const attemptRef = useRef(0);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const cleanup = useCallback(() => {
    attemptRef.current += 1;
    sessionRef.current?.cleanup();
    sessionRef.current = null;
    setIsRecording(false);
    setAudioLevel(0);
  }, []);

  const startRecording = useCallback(async (startOptions?: StartRecordingOptions) => {
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

    // cleanup() just bumped the attempt counter; this is the live generation.
    const myAttempt = attemptRef.current;

    const result = await startCapturePipeline({
      getUserMedia: () =>
        navigator.mediaDevices!.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        }) as Promise<CaptureStream>,
      createAudioContext: () => {
        const AudioCtx =
          window.AudioContext || (window as any).webkitAudioContext;
        return new AudioCtx();
      },
      createWorkletNode: (ctx) =>
        new AudioWorkletNode(
          ctx as unknown as AudioContext,
          'pcm16-worklet-processor'
        ) as any,
      onAudioChunk: (chunk) => optionsRef.current.onAudioChunk?.(chunk),
      onAudioLevel: setAudioLevel,
      onTrackEnded: () => {
        // Unexpected mid-recording termination (hardware/permission loss).
        cleanup();
        const type: AudioCaptureErrorType = 'disconnected';
        const msg = 'Microphone was disconnected during active recording.';
        setErrorType(type);
        setErrorMessage(msg);
        optionsRef.current.onError?.(type, msg);
      },
      shouldAbort: startOptions?.shouldAbort,
      isStale: () => myAttempt !== attemptRef.current,
    });

    if (result.ok) {
      if (myAttempt !== attemptRef.current) {
        // Superseded by a newer attempt after the pipeline's last checkpoint:
        // release THIS session immediately and touch nothing shared, so an
        // old capture can never hold or clobber the newer attempt's resources.
        result.session.cleanup();
        return false;
      }
      // The pipeline's final checkpoint guarantees no abort/stale raced past
      // the last await, so storing the session here is safe.
      sessionRef.current = result.session;
      setIsRecording(true);
      return true;
    }

    if (result.reason === 'failed') {
      if (result.stage === 'pipeline') {
        const err = result.error as any;
        const msg = `Failed to initialize audio processing pipeline: ${err?.message || err}`;
        setErrorType('unknown');
        setErrorMessage(msg);
        optionsRef.current.onError?.('unknown', msg);
        return false;
      }
      const { type, message } = classifyCaptureError(result.error);
      setErrorType(type);
      setErrorMessage(message);
      optionsRef.current.onError?.(type, message);
      return false;
    }

    // 'aborted' | 'stale': expected cancellation — silent, no error alert.
    return false;
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

/**
 * VoiceSense AI — Injectable Audio Capture Pipeline (Chunk 9.7C-2)
 * Framework-agnostic capture orchestration: getUserMedia → AudioContext →
 * AudioWorklet (with ScriptProcessor fallback) → live PCM16 chunk forwarding.
 * All browser APIs are injected so the abort/stale/cleanup contract is
 * unit-testable without a DOM.
 */

import { calculateRMS, resampleTo16kPCM16 } from './audio-utils';

export interface CaptureTrack {
  stop(): void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onended: ((event?: any) => void) | null;
}

export interface CaptureStream {
  getAudioTracks(): CaptureTrack[];
  getTracks(): CaptureTrack[];
}

export interface CaptureScriptNode {
  connect(destination: unknown): void;
  disconnect(): void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onaudioprocess: ((event: any) => void) | null;
}

export interface CaptureAudioContext {
  readonly state: string;
  readonly sampleRate: number;
  readonly destination: unknown;
  audioWorklet?: { addModule(url: string): Promise<void> };
  createMediaStreamSource(stream: CaptureStream): { connect(node: unknown): void };
  createScriptProcessor(
    bufferSize: number,
    inputChannels: number,
    outputChannels: number
  ): CaptureScriptNode;
  close(): Promise<void>;
}

export interface CaptureWorkletNode {
  connect(destination: unknown): void;
  disconnect(): void;
  port: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onmessage: ((event: { data: ArrayBuffer }) => void) | null;
  };
}

export interface CaptureSessionDeps {
  getUserMedia: () => Promise<CaptureStream>;
  createAudioContext: () => CaptureAudioContext;
  /**
   * Creates the PCM16 worklet node. When absent or when it/addModule throws,
   * the pipeline falls back to ScriptProcessorNode — preserving prior behavior.
   */
  createWorkletNode?: (ctx: CaptureAudioContext) => CaptureWorkletNode;
  workletModuleUrl?: string;
  onAudioChunk?: (chunk: ArrayBuffer) => void;
  onAudioLevel?: (level: number) => void;
  /** Fired when the OS/hardware ends the capture track mid-session. */
  onTrackEnded?: () => void;
  /** Controller cancellation signal (epoch changed). */
  shouldAbort?: () => boolean;
  /** Attempt-generation guard: true when a newer capture attempt superseded this one. */
  isStale?: () => boolean;
}

export interface CaptureSession {
  /** Idempotent: disconnects nodes, stops tracks, closes the context. */
  cleanup(): void;
}

export type CapturePipelineResult =
  | { ok: true; session: CaptureSession }
  | {
      ok: false;
      reason: 'aborted' | 'stale' | 'failed';
      /** 'getUserMedia' → permission/device error; 'pipeline' → AudioContext/node setup. */
      stage?: 'getUserMedia' | 'pipeline';
      error?: unknown;
    };

export async function startCapturePipeline(
  deps: CaptureSessionDeps
): Promise<CapturePipelineResult> {
  const isStale = () => deps.isStale?.() === true;
  const isAborted = () => isStale() || deps.shouldAbort?.() === true;
  const abortReason = (): 'stale' | 'aborted' => (isStale() ? 'stale' : 'aborted');

  let stream: CaptureStream | null = null;
  try {
    stream = await deps.getUserMedia();
  } catch (error) {
    return { ok: false, reason: 'failed', stage: 'getUserMedia', error };
  }
  const capturedStream = stream;

  // Checkpoint 1 — permission resolved after cancellation/stale attempt:
  // release the just-granted tracks before any AudioContext exists.
  if (isAborted()) {
    capturedStream.getTracks().forEach((track) => track.stop());
    return { ok: false, reason: abortReason() };
  }

  // Monitor for mid-stream hardware/permission disconnection.
  const audioTrack = capturedStream.getAudioTracks()[0];
  if (audioTrack) {
    audioTrack.onended = () => deps.onTrackEnded?.();
  }

  let audioCtx: CaptureAudioContext | null = null;
  let workletNode: CaptureWorkletNode | null = null;
  let scriptNode: CaptureScriptNode | null = null;
  // False once teardown begins: queued/in-flight audio callbacks must not
  // forward chunks after the controller's stop frame (avoids NOT_STARTED).
  let forwarding = true;

  const teardown = () => {
    forwarding = false;
    // Clear callbacks BEFORE disconnecting so nothing queued can re-arm them.
    if (workletNode) {
      workletNode.port.onmessage = null;
      try {
        workletNode.disconnect();
      } catch {
        // already disconnected
      }
      workletNode = null;
    }
    if (scriptNode) {
      scriptNode.onaudioprocess = null;
      try {
        scriptNode.disconnect();
      } catch {
        // already disconnected
      }
      scriptNode = null;
    }
    if (stream) {
      stream.getTracks().forEach((track) => {
        track.onended = null;
        track.stop();
      });
      stream = null;
    }
    if (audioCtx && audioCtx.state !== 'closed') {
      audioCtx.close().catch(() => {});
      audioCtx = null;
    }
  };

  try {
    audioCtx = deps.createAudioContext();
    const source = audioCtx.createMediaStreamSource(capturedStream);

    let live = false;
    if (audioCtx.audioWorklet && deps.createWorkletNode) {
      try {
        await audioCtx.audioWorklet.addModule(
          deps.workletModuleUrl ?? '/audio-processor.js'
        );
        // Checkpoint 2 — cancelled while the worklet module was loading.
        if (isAborted()) {
          teardown();
          return { ok: false, reason: abortReason() };
        }
        workletNode = deps.createWorkletNode(audioCtx);
        workletNode.port.onmessage = (e) => {
          if (!forwarding) return;
          const buffer = e.data;
          if (buffer && buffer.byteLength > 0) {
            deps.onAudioLevel?.(calculateRMS(new Int16Array(buffer)));
            deps.onAudioChunk?.(buffer);
          }
        };
        source.connect(workletNode);
        workletNode.connect(audioCtx.destination);
        live = true;
      } catch (workletErr) {
        // Abort raced with a worklet failure: prefer the abort outcome.
        if (isAborted()) {
          teardown();
          return { ok: false, reason: abortReason() };
        }
        console.warn(
          '[AudioCapture] AudioWorklet setup failed, falling back to ScriptProcessor:',
          workletErr
        );
        workletNode = null;
      }
    }

    if (!live) {
      scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);
      scriptNode.onaudioprocess = (event) => {
        if (!forwarding) return;
        const inputData = event.inputBuffer.getChannelData(0);
        deps.onAudioLevel?.(calculateRMS(inputData));
        const pcm16 = resampleTo16kPCM16(inputData, audioCtx!.sampleRate);
        if (pcm16.length > 0) {
          deps.onAudioChunk?.(pcm16.buffer as ArrayBuffer);
        }
      };
      source.connect(scriptNode);
      scriptNode.connect(audioCtx.destination);
    }

    // Checkpoint 3 — cancelled during pipeline init: tear down everything
    // created so far and never enter the live state.
    if (isAborted()) {
      teardown();
      return { ok: false, reason: abortReason() };
    }

    return { ok: true, session: { cleanup: teardown } };
  } catch (error) {
    teardown();
    return { ok: false, reason: 'failed', stage: 'pipeline', error };
  }
}

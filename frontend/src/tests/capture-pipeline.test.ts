import { describe, it, expect, vi } from 'vitest';
import {
  startCapturePipeline,
  CaptureSessionDeps,
  CaptureStream,
  CaptureAudioContext,
  CaptureWorkletNode,
} from '../lib/capturePipeline';

// Chunk 9.7C-2: injectable capture pipeline — abort checkpoints, resource
// cleanup, stale-attempt protection, and worklet→script fallback, all with
// mocked browser APIs (no DOM, no real microphone).

interface MockTrack {
  stop: ReturnType<typeof vi.fn>;
  onended: (() => void) | null;
}

function makeStream() {
  const track: MockTrack = { stop: vi.fn(), onended: null };
  const stream: CaptureStream = {
    getAudioTracks: () => [track],
    getTracks: () => [track],
  };
  return { stream, track };
}

function makeAudioContext(overrides: Partial<CaptureAudioContext> = {}) {
  const source = { connect: vi.fn() };
  const ctx: CaptureAudioContext = {
    state: 'running',
    sampleRate: 48000,
    destination: {},
    audioWorklet: { addModule: vi.fn().mockResolvedValue(undefined) },
    createMediaStreamSource: vi.fn(() => source),
    createScriptProcessor: vi.fn(() => ({
      connect: vi.fn(),
      disconnect: vi.fn(),
      onaudioprocess: null,
    })),
    close: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { ctx, source };
}

function makeWorkletNode() {
  const node: CaptureWorkletNode = {
    connect: vi.fn(),
    disconnect: vi.fn(),
    port: { onmessage: null },
  };
  return node;
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function baseDeps(overrides: Partial<CaptureSessionDeps> = {}) {
  const { stream, track } = makeStream();
  const { ctx, source } = makeAudioContext();
  const workletNode = makeWorkletNode();
  const deps: CaptureSessionDeps = {
    getUserMedia: vi.fn().mockResolvedValue(stream),
    createAudioContext: vi.fn(() => ctx),
    createWorkletNode: vi.fn(() => workletNode),
    onAudioChunk: vi.fn(),
    onAudioLevel: vi.fn(),
    ...overrides,
  };
  return { deps, stream, track, ctx, source, workletNode };
}

describe('startCapturePipeline — abort checkpoints', () => {
  it('abort after getUserMedia: stops tracks, never creates AudioContext', async () => {
    const gum = deferred<CaptureStream>();
    const { deps } = baseDeps({
      getUserMedia: () => gum.promise,
      shouldAbort: () => true,
    });
    const { stream: s2, track: t2 } = makeStream();

    const pending = startCapturePipeline(deps);
    gum.resolve(s2);
    const result = await pending;

    expect(result).toEqual({ ok: false, reason: 'aborted' });
    expect(t2.stop).toHaveBeenCalledTimes(1);
    expect(deps.createAudioContext).not.toHaveBeenCalled();
    expect(deps.createWorkletNode).not.toHaveBeenCalled();
  });

  it('abort during worklet module load: closes context, stops tracks, no worklet node', async () => {
    const moduleLoad = deferred<void>();
    let abort = false;
    const { deps, ctx, track, workletNode } = baseDeps({
      shouldAbort: () => abort,
    });
    ctx.audioWorklet = { addModule: vi.fn(() => moduleLoad.promise) };

    const pending = startCapturePipeline(deps);
    // Wait until the pipeline is actually suspended inside addModule.
    await vi.waitFor(() => {
      expect(ctx.audioWorklet!.addModule).toHaveBeenCalled();
    });
    abort = true;
    moduleLoad.resolve();
    const result = await pending;

    expect(result).toEqual({ ok: false, reason: 'aborted' });
    expect(deps.createWorkletNode).not.toHaveBeenCalled();
    expect(workletNode.connect).not.toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalled();
    expect(track.onended).toBeNull();
    expect(ctx.close).toHaveBeenCalled();
  });

  it('abort before going live: full teardown, no chunks forwarded', async () => {
    let abort = false;
    const { deps, ctx, track, workletNode } = baseDeps({
      shouldAbort: () => abort,
    });
    // Abort flips only at the final checkpoint (after worklet setup).
    const origCreate = deps.createWorkletNode!;
    deps.createWorkletNode = (c) => {
      const node = origCreate(c);
      abort = true;
      return node;
    };

    const pending = startCapturePipeline(deps);
    const result = await pending;

    expect(result).toEqual({ ok: false, reason: 'aborted' });
    expect(workletNode.disconnect).toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalled();
    expect(ctx.close).toHaveBeenCalled();
    expect(deps.onAudioChunk).not.toHaveBeenCalled();
  });

  it('isStale supersedes shouldAbort and reports reason stale', async () => {
    const { deps, track } = baseDeps({
      isStale: () => true,
      shouldAbort: () => false,
    });
    const result = await startCapturePipeline(deps);
    expect(result).toEqual({ ok: false, reason: 'stale' });
    expect(track.stop).toHaveBeenCalled();
  });
});

describe('startCapturePipeline — success and fallback', () => {
  it('returns a live session; worklet onmessage forwards PCM chunks', async () => {
    const { deps, workletNode, track } = baseDeps();
    const result = await startCapturePipeline(deps);

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(track.onended).not.toBeNull();

    const pcm = new Int16Array([100, -100, 200]).buffer;
    workletNode.port.onmessage!({ data: pcm });
    expect(deps.onAudioChunk).toHaveBeenCalledWith(pcm);
    expect(deps.onAudioLevel).toHaveBeenCalled();

    // Session cleanup is idempotent.
    result.session.cleanup();
    result.session.cleanup();
    expect(workletNode.disconnect).toHaveBeenCalledTimes(1);
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(track.onended).toBeNull();
  });

  it('falls back to ScriptProcessor when worklet setup fails', async () => {
    const { deps, ctx } = baseDeps();
    ctx.audioWorklet = {
      addModule: vi.fn().mockRejectedValue(new Error('no worklet')),
    };

    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    expect(deps.createWorkletNode).not.toHaveBeenCalled();
    expect(ctx.createScriptProcessor).toHaveBeenCalledWith(4096, 1, 1);
  });

  it('script fallback forwards resampled chunks', async () => {
    const { deps, ctx } = baseDeps();
    ctx.audioWorklet = undefined; // no worklet support at all
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);

    const scriptNode = vi.mocked(ctx.createScriptProcessor).mock.results[0]
      .value as { onaudioprocess: ((e: any) => void) | null };
    const input = new Float32Array(256).fill(0.1);
    scriptNode.onaudioprocess!({
      inputBuffer: { getChannelData: () => input },
    });
    expect(deps.onAudioChunk).toHaveBeenCalled();
    const chunk = vi.mocked(deps.onAudioChunk!).mock.calls[0][0];
    expect(chunk).toBeInstanceOf(ArrayBuffer);
    expect(chunk.byteLength).toBeGreaterThan(0);
  });

  it('onTrackEnded fires when the media track ends', async () => {
    const onTrackEnded = vi.fn();
    const { deps, track } = baseDeps({ onTrackEnded });
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);

    track.onended!();
    expect(onTrackEnded).toHaveBeenCalledTimes(1);
  });

  it('getUserMedia rejection returns failed with the original error', async () => {
    const err = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    const { deps } = baseDeps({
      getUserMedia: vi.fn().mockRejectedValue(err),
    });
    const result = await startCapturePipeline(deps);
    expect(result).toMatchObject({
      ok: false,
      reason: 'failed',
      stage: 'getUserMedia',
    });
    expect((result as any).error).toBe(err);
  });

  it('pipeline-internal failure tears down and reports stage pipeline', async () => {
    const { deps, track } = baseDeps();
    deps.createAudioContext = vi.fn(() => {
      throw new Error('AudioContext unavailable');
    });
    const result = await startCapturePipeline(deps);
    expect(result).toMatchObject({
      ok: false,
      reason: 'failed',
      stage: 'pipeline',
    });
    expect(track.stop).toHaveBeenCalled();
  });
});

// Chunk 9.8C: once teardown begins, no queued/in-flight audio callback may
// forward a chunk — prevents a post-stop NOT_STARTED error from the server.
describe('startCapturePipeline — teardown callback safety', () => {
  it('worklet onmessage property is cleared by teardown', async () => {
    const { deps, workletNode } = baseDeps();
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const pcm = new Int16Array([1, 2, 3]).buffer;
    workletNode.port.onmessage!({ data: pcm });
    expect(deps.onAudioChunk).toHaveBeenCalledTimes(1);

    result.session.cleanup();
    expect(workletNode.port.onmessage).toBeNull();
    expect(deps.onAudioChunk).toHaveBeenCalledTimes(1);
  });

  it('a callback captured before teardown but invoked afterward is ignored', async () => {
    const { deps, workletNode } = baseDeps();
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const captured = workletNode.port.onmessage!;
    result.session.cleanup();

    const pcm = new Int16Array([9, 9]).buffer;
    captured({ data: pcm }); // queued/in-flight invocation post-teardown
    expect(deps.onAudioChunk).not.toHaveBeenCalled();
    expect(deps.onAudioLevel).not.toHaveBeenCalled();
  });

  it('script processor callback after teardown does not forward chunks', async () => {
    const { deps, ctx } = baseDeps();
    ctx.audioWorklet = undefined;
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const scriptNode = vi.mocked(ctx.createScriptProcessor).mock.results[0]
      .value as { onaudioprocess: ((e: any) => void) | null; disconnect: ReturnType<typeof vi.fn> };
    const captured = scriptNode.onaudioprocess!;

    result.session.cleanup();
    expect(scriptNode.onaudioprocess).toBeNull();

    captured({ inputBuffer: { getChannelData: () => new Float32Array(8).fill(0.5) } });
    expect(deps.onAudioChunk).not.toHaveBeenCalled();
  });

  it('teardown clears the worklet handler before disconnecting', async () => {
    const { deps, workletNode } = baseDeps();
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    // If disconnect ran before the handler was cleared, this assertion
    // inside the mock would fail — proving clear-before-disconnect order.
    vi.mocked(workletNode.disconnect).mockImplementation(() => {
      expect(workletNode.port.onmessage).toBeNull();
    });

    result.session.cleanup();
    expect(workletNode.disconnect).toHaveBeenCalled();
  });

  it('script-path teardown clears onaudioprocess before disconnect', async () => {
    const { deps, ctx } = baseDeps();
    ctx.audioWorklet = undefined;
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const scriptNode = vi.mocked(ctx.createScriptProcessor).mock.results[0]
      .value as {
        onaudioprocess: ((e: any) => void) | null;
        disconnect: ReturnType<typeof vi.fn>;
      };
    vi.mocked(scriptNode.disconnect).mockImplementation(() => {
      expect(scriptNode.onaudioprocess).toBeNull();
    });

    result.session.cleanup();
    expect(scriptNode.disconnect).toHaveBeenCalled();
  });

  it('repeated teardown keeps handlers cleared and disconnects once', async () => {
    const { deps, workletNode } = baseDeps();
    const result = await startCapturePipeline(deps);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    result.session.cleanup();
    result.session.cleanup();
    expect(workletNode.port.onmessage).toBeNull();
    expect(workletNode.disconnect).toHaveBeenCalledTimes(1);
  });

  it('tearing down an older capture does not stop a newer one forwarding', async () => {
    const a = baseDeps();
    const b = baseDeps();
    const resA = await startCapturePipeline(a.deps);
    const resB = await startCapturePipeline(b.deps);
    expect(resA.ok && resB.ok).toBe(true);
    if (!resA.ok || !resB.ok) return;

    resA.session.cleanup();

    const pcmB = new Int16Array([7]).buffer;
    b.workletNode.port.onmessage!({ data: pcmB });
    expect(b.deps.onAudioChunk).toHaveBeenCalledWith(pcmB);
    expect(a.deps.onAudioChunk).not.toHaveBeenCalled();

    resB.session.cleanup();
  });
});

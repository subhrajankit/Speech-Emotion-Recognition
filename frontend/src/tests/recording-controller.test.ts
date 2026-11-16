import { describe, it, expect, vi } from 'vitest';
import {
  createRecordingController,
  RecordingControllerDeps,
} from '../lib/recordingController';

function makeHarness(overrides: Partial<RecordingControllerDeps> = {}) {
  const events: string[] = [];
  const onNotReady = vi.fn(() => {
    events.push('onNotReady');
  });

  const deps: RecordingControllerDeps = {
    isReady: () => true,
    sendStartFrame: () => events.push('sendStart'),
    sendStopFrame: () => events.push('sendStop'),
    startCapture: async () => {
      events.push('startCapture');
      // Simulate the capture pipeline emitting an audio chunk mid-startup:
      // the `start` frame must already have been submitted by this point.
      events.push('audioChunk');
      return true;
    },
    stopCapture: () => events.push('stopCapture'),
    onNotReady,
    ...overrides,
  };

  return { deps, events, onNotReady };
}

describe('RecordingController — start/stop protocol ordering', () => {
  it('sends `start` before capture produces audio on first recording', async () => {
    const { deps, events } = makeHarness();
    const ctl = createRecordingController(deps);

    const result = await ctl.start();

    expect(result).toBe('started');
    expect(events).toEqual(['sendStart', 'startCapture', 'audioChunk']);
    expect(ctl.isActive()).toBe(true);
  });

  it('sends a fresh `start` frame when recording restarts after manual stop', async () => {
    const { deps, events } = makeHarness();
    const ctl = createRecordingController(deps);

    await ctl.start();
    ctl.stop();
    const second = await ctl.start();

    expect(second).toBe('started');
    expect(events).toEqual([
      'sendStart',
      'startCapture',
      'audioChunk',
      'stopCapture',
      'sendStop',
      'sendStart',
      'startCapture',
      'audioChunk',
    ]);
  });

  it('preserves existing stop ordering: capture teardown before `stop` frame', async () => {
    const { deps, events } = makeHarness();
    const ctl = createRecordingController(deps);

    await ctl.start();
    events.length = 0;
    ctl.stop();

    expect(events).toEqual(['stopCapture', 'sendStop']);
    expect(ctl.isActive()).toBe(false);
  });

  it('never emits duplicate `start` frames for concurrent or repeated starts', async () => {
    const { deps, events } = makeHarness();
    const ctl = createRecordingController(deps);

    // Concurrent starts while capture is still pending.
    const [r1, r2] = await Promise.all([ctl.start(), ctl.start()]);
    expect([r1, r2].sort()).toEqual(['busy', 'started']);
    expect(events.filter((e) => e === 'sendStart')).toHaveLength(1);

    // Start while already active.
    const r3 = await ctl.start();
    expect(r3).toBe('busy');
    expect(events.filter((e) => e === 'sendStart')).toHaveLength(1);
  });

  it('refuses to start when the socket is not connected and ready', async () => {
    const { deps, events, onNotReady } = makeHarness({ isReady: () => false });
    const ctl = createRecordingController(deps);

    const result = await ctl.start();

    expect(result).toBe('not_ready');
    expect(onNotReady).toHaveBeenCalledTimes(1);
    expect(events).toEqual(['onNotReady']);
    expect(ctl.isActive()).toBe(false);
    expect(ctl.isStarting()).toBe(false);
  });

  it('reports failure without claiming success when capture cannot start', async () => {
    const { deps, events } = makeHarness({
      startCapture: async () => {
        events.push('startCapture');
        return false; // e.g. microphone permission denied
      },
    });
    const ctl = createRecordingController(deps);

    const result = await ctl.start();

    expect(result).toBe('failed');
    expect(ctl.isActive()).toBe(false);
    expect(ctl.isStarting()).toBe(false);
    // A later attempt is allowed to retry with a fresh `start` frame.
    deps.startCapture = async () => {
      events.push('startCaptureRetry');
      return true;
    };
    const retry = await ctl.start();
    expect(retry).toBe('started');
    expect(events.filter((e) => e === 'sendStart')).toHaveLength(2);
  });

  it('stop() still tears down capture and clears state when readiness is lost', async () => {
    let ready = true;
    const { deps, events } = makeHarness({ isReady: () => ready });
    const ctl = createRecordingController(deps);

    await ctl.start();
    expect(ctl.isActive()).toBe(true);

    // Socket drops mid-recording: readiness goes false, but stop() must still
    // run capture teardown and attempt the stop frame (a no-op on a dead
    // socket in the real hook).
    ready = false;
    ctl.stop();

    expect(ctl.isActive()).toBe(false);
    expect(events.slice(-2)).toEqual(['stopCapture', 'sendStop']);

    // Once readiness returns, a fresh start succeeds with a new `start` frame.
    ready = true;
    const retry = await ctl.start();
    expect(retry).toBe('started');
    expect(events.filter((e) => e === 'sendStart')).toHaveLength(2);
  });

  it('repeated stop() calls do not duplicate cleanup or stop frames', async () => {
    const { deps, events } = makeHarness();
    const ctl = createRecordingController(deps);

    await ctl.start();
    ctl.stop();
    events.length = 0;

    ctl.stop();
    ctl.stop();

    expect(events).toEqual([]);
    expect(ctl.isActive()).toBe(false);
  });

  it('stop() during a pending capture start prevents a zombie recording', async () => {
    let resolveCapture: ((ok: boolean) => void) | null = null;
    const { deps, events } = makeHarness({
      startCapture: () =>
        new Promise<boolean>((resolve) => {
          events.push('startCapture');
          resolveCapture = resolve;
        }),
    });
    const ctl = createRecordingController(deps);

    const startPromise = ctl.start();
    expect(ctl.isStarting()).toBe(true);

    // Connection lost while getUserMedia/pipeline is still pending.
    ctl.stop();
    resolveCapture!(true); // capture pipeline finishes anyway
    const result = await startPromise;

    expect(result).toBe('stopped');
    expect(ctl.isActive()).toBe(false);
    expect(ctl.isStarting()).toBe(false);
    // Capture teardown ran once via stop(); the stale resolution touches no
    // shared cleanup — capture self-cleans via shouldAbort/isStale.
    expect(events.filter((e) => e === 'stopCapture')).toHaveLength(1);
    expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);

    // A subsequent start after readiness returns works normally.
    deps.startCapture = async () => {
      events.push('startCaptureRetry');
      return true;
    };
    expect(await ctl.start()).toBe('started');
  });

  // Chunk 9.7B: unexpected capture termination (track.onended) is routed to
  // controller.stop() by the App onError path. These tests pin the controller
  // contract that makes that recovery safe and restartable.
  describe('capture-failure recovery', () => {
    it('clears active state on failure-stop and permits an immediate restart', async () => {
      const { deps, events } = makeHarness();
      const ctl = createRecordingController(deps);

      await ctl.start();
      expect(ctl.isActive()).toBe(true);

      // Simulates the track.onended → onError('disconnected') → ctl.stop() path.
      ctl.stop();
      expect(ctl.isActive()).toBe(false);
      expect(ctl.isStarting()).toBe(false);

      // A subsequent Start must succeed without a page reload.
      const retry = await ctl.start();
      expect(retry).toBe('started');
      expect(ctl.isActive()).toBe(true);
      expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);
      expect(events.filter((e) => e === 'sendStart')).toHaveLength(2);
    });

    it('sends the stop frame at most once across repeated failure stops', async () => {
      const { deps, events } = makeHarness();
      const ctl = createRecordingController(deps);

      await ctl.start();
      ctl.stop(); // failure path
      ctl.stop(); // duplicate/late callback
      ctl.stop();

      expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);
      expect(events.filter((e) => e === 'stopCapture')).toHaveLength(1);
    });

    it('a failure stop during pending capture prevents a zombie and allows restart', async () => {
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const { deps } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          }),
      });
      const ctl = createRecordingController(deps);

      const startPromise = ctl.start();
      expect(ctl.isStarting()).toBe(true);

      // Track ended (or auth/disconnect stop) while getUserMedia is pending.
      ctl.stop();
      resolveCapture!(true);
      expect(await startPromise).toBe('stopped');
      expect(ctl.isActive()).toBe(false);

      deps.startCapture = async () => true;
      expect(await ctl.start()).toBe('started');
    });

    it('an expected user stop does not leave failure state behind', async () => {
      const { deps, events } = makeHarness();
      const ctl = createRecordingController(deps);

      await ctl.start();
      ctl.stop(); // ordinary user-initiated stop

      // Controller is fully idle: no active/starting residue, restart clean.
      expect(ctl.isActive()).toBe(false);
      expect(ctl.isStarting()).toBe(false);
      expect(await ctl.start()).toBe('started');
      expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);
    });
  });

  // Chunk 9.7C: startup phase is observable and cancellable.
  describe('startup cancellation and state sync', () => {
    it('exposes isStarting() and notifies onStateChange across the lifecycle', async () => {
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const states: boolean[] = [];
      const { deps } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          }),
        onStateChange: () => {
          states.push(true);
        },
      });
      const ctl = createRecordingController(deps);

      const startPromise = ctl.start();
      expect(ctl.isStarting()).toBe(true);
      expect(ctl.isActive()).toBe(false);

      resolveCapture!(true);
      expect(await startPromise).toBe('started');
      expect(ctl.isStarting()).toBe(false);
      expect(ctl.isActive()).toBe(true);
      // Notified at start (starting=true) and at resolution (starting=false).
      expect(states.length).toBeGreaterThanOrEqual(2);
    });

    it('a second toggle during startup cancels: isStarting clears immediately and restart works', async () => {
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const { deps, events } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          }),
      });
      const ctl = createRecordingController(deps);

      const startPromise = ctl.start();
      expect(ctl.isStarting()).toBe(true);

      // User cancels while getUserMedia/pipeline is still pending.
      ctl.stop();
      // isStarting() must report false immediately — the pending promise has
      // not resolved yet, but the session is already cancelled.
      expect(ctl.isStarting()).toBe(false);

      resolveCapture!(true); // capture finishes anyway
      expect(await startPromise).toBe('stopped');
      expect(ctl.isActive()).toBe(false);

      deps.startCapture = async () => true;
      expect(await ctl.start()).toBe('started');
      expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);
    });

    it('passes a live shouldAbort callback that flips true after cancellation', async () => {
      let abortFn: (() => boolean) | undefined;
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const { deps } = makeHarness({
        startCapture: (shouldAbort) => {
          abortFn = shouldAbort;
          return new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          });
        },
      });
      const ctl = createRecordingController(deps);

      const startPromise = ctl.start();
      expect(abortFn?.()).toBe(false); // not cancelled yet

      ctl.stop();
      expect(abortFn?.()).toBe(true); // epoch advanced → abort signalled

      resolveCapture!(false); // capture honours the abort
      expect(await startPromise).toBe('stopped');
    });

    it('repeated stops during a pending start emit exactly one stop frame', async () => {
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const { deps, events } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          }),
      });
      const ctl = createRecordingController(deps);

      const startPromise = ctl.start();
      ctl.stop();
      ctl.stop();
      ctl.stop();
      resolveCapture!(true);
      await startPromise;

      expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);
      expect(events.filter((e) => e === 'stopCapture').length).toBeGreaterThanOrEqual(1);
    });

    it('notifies on every observable transition and skips redundant ones', async () => {
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const snapshots: Array<{ starting: boolean; active: boolean }> = [];
      const { deps } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          }),
        onStateChange: () => {
          snapshots.push({ starting: ctl.isStarting(), active: ctl.isActive() });
        },
      });
      // eslint-disable-next-line @typescript-eslint/no-use-before-define
      const ctl = createRecordingController(deps);

      const p = ctl.start();
      // entering starting
      expect(snapshots).toEqual([{ starting: true, active: false }]);

      ctl.stop(); // cancel while pending
      expect(snapshots[snapshots.length - 1]).toEqual({ starting: false, active: false });

      resolveCapture!(true);
      expect(await p).toBe('stopped');
      // Pending resolution after cancel must NOT re-notify — observable state
      // was already false/false.
      expect(snapshots).toHaveLength(2);

      // Successful lifecycle: starting → active → stopped notifies each change.
      deps.startCapture = async () => true;
      await ctl.start();
      expect(snapshots[snapshots.length - 1]).toEqual({ starting: false, active: true });
      const before = snapshots.length;
      ctl.stop();
      expect(snapshots.length).toBe(before + 1);
      expect(snapshots[snapshots.length - 1]).toEqual({ starting: false, active: false });
    });

    it('a rejected startCapture resolves as failed without stuck state or frames', async () => {
      const { deps, events } = makeHarness({
        startCapture: async () => {
          throw new Error('capture exploded');
        },
      });
      const ctl = createRecordingController(deps);

      const result = await ctl.start();
      expect(result).toBe('failed');
      expect(ctl.isStarting()).toBe(false);
      expect(ctl.isActive()).toBe(false);

      // engaged was cleared: a stray stop() emits nothing.
      events.length = 0;
      ctl.stop();
      expect(events).toEqual([]);

      // Retry works.
      deps.startCapture = async () => true;
      expect(await ctl.start()).toBe('started');
    });

    it('a cancelled older start cannot overwrite a newer start', async () => {
      const resolvers: Array<(ok: boolean) => void> = [];
      const { deps } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolvers.push(resolve);
          }),
      });
      const ctl = createRecordingController(deps);

      const p1 = ctl.start();
      ctl.stop(); // cancel epoch 0
      resolvers[0](true);
      expect(await p1).toBe('stopped');
      expect(ctl.isActive()).toBe(false);

      const p2 = ctl.start(); // epoch 1
      resolvers[1](true);
      expect(await p2).toBe('started');
      expect(ctl.isActive()).toBe(true);
      expect(ctl.isStarting()).toBe(false);
    });
  });

  // Chunk 9.8B: a cancelled-but-unsettled start must not block an immediate
  // restart, and the old attempt must never disturb the new one.
  describe('rapid cancel-to-restart', () => {
    function deferredHarness() {
      const resolvers: Array<{
        resolve: (ok: boolean) => void;
        reject: (err: unknown) => void;
      }> = [];
      const { deps, events } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve, reject) => {
            resolvers.push({ resolve, reject });
          }),
      });
      return { deps, events, resolvers };
    }

    it('allows a new start while the cancelled attempt is still pending', async () => {
      const { deps, events, resolvers } = deferredHarness();
      const ctl = createRecordingController(deps);

      const p1 = ctl.start();
      ctl.stop(); // cancel attempt 1 — engaged=false but promise pending
      expect(ctl.isStarting()).toBe(false);

      // Immediate second press: must start, not return silent 'busy'.
      const p2 = ctl.start();
      expect(ctl.isStarting()).toBe(true);

      resolvers[1].resolve(true);
      expect(await p2).toBe('started');
      expect(ctl.isActive()).toBe(true);

      // Attempt 1 settles late — must report 'stopped' and touch nothing.
      resolvers[0].resolve(true);
      expect(await p1).toBe('stopped');
      expect(ctl.isActive()).toBe(true);
      expect(ctl.isStarting()).toBe(false);

      // Frames: one start+stop for attempt 1, one start for attempt 2.
      expect(events.filter((e) => e === 'sendStart')).toHaveLength(2);
      expect(events.filter((e) => e === 'sendStop')).toHaveLength(1);
      expect(events.filter((e) => e === 'stopCapture')).toHaveLength(1);
    });

    it('old attempt resolving after the new one is active leaves it untouched', async () => {
      const { deps, resolvers } = deferredHarness();
      const ctl = createRecordingController(deps);

      const p1 = ctl.start();
      ctl.stop();
      const p2 = ctl.start();
      resolvers[1].resolve(true);
      await p2;
      expect(ctl.isActive()).toBe(true);

      resolvers[0].resolve(true);
      expect(await p1).toBe('stopped');
      // New recording still fully active and engaged: its stop still works.
      expect(ctl.isActive()).toBe(true);
      ctl.stop();
      expect(ctl.isActive()).toBe(false);
    });

    it('old attempt rejecting after the new start leaves it unaffected', async () => {
      const { deps, resolvers } = deferredHarness();
      const ctl = createRecordingController(deps);

      const p1 = ctl.start();
      ctl.stop();
      const p2 = ctl.start();
      resolvers[1].resolve(true);
      await p2;
      expect(ctl.isActive()).toBe(true);

      resolvers[0].reject(new Error('late gUM failure'));
      expect(await p1).toBe('stopped'); // stale rejection, not 'failed'
      expect(ctl.isActive()).toBe(true);
      expect(ctl.isStarting()).toBe(false);
    });

    it('chained cancel-restart-cancel isolates each attempt', async () => {
      const { deps, events, resolvers } = deferredHarness();
      const ctl = createRecordingController(deps);

      const p1 = ctl.start();
      ctl.stop();
      const p2 = ctl.start();
      ctl.stop(); // cancel attempt 2 as well
      const p3 = ctl.start();
      expect(ctl.isStarting()).toBe(true);

      resolvers[2].resolve(true);
      expect(await p3).toBe('started');
      resolvers[0].resolve(true);
      resolvers[1].resolve(false);
      expect(await p1).toBe('stopped');
      expect(await p2).toBe('stopped');
      expect(ctl.isActive()).toBe(true);

      expect(events.filter((e) => e === 'sendStart')).toHaveLength(3);
      expect(events.filter((e) => e === 'sendStop')).toHaveLength(2);
    });

    it('keeps isStarting()/notifications accurate across overlapping attempts', async () => {
      const { deps, resolvers } = deferredHarness();
      const snapshots: Array<{ starting: boolean; active: boolean }> = [];
      const ctl = createRecordingController({
        ...deps,
        onStateChange: () => {
          snapshots.push({ starting: ctl.isStarting(), active: ctl.isActive() });
        },
      });

      const p1 = ctl.start();
      ctl.stop();
      const p2 = ctl.start();
      resolvers[1].resolve(true);
      await p2;
      resolvers[0].resolve(true);
      await p1;

      // Observable states seen: starting → idle(cancel) → starting → active.
      // The stale attempt's settlement must not add a notification.
      expect(snapshots).toEqual([
        { starting: true, active: false },
        { starting: false, active: false },
        { starting: true, active: false },
        { starting: false, active: true },
      ]);
    });
  });

  // Chunk 10.3C: onSessionStart marks the boundary of a genuinely new
  // recording session — the point where stale live results may be cleared.
  describe('onSessionStart', () => {
    it('fires once when a new recording session goes live', async () => {
      const onSessionStart = vi.fn();
      const { deps } = makeHarness({ onSessionStart });
      const ctl = createRecordingController(deps);

      expect(await ctl.start()).toBe('started');
      expect(onSessionStart).toHaveBeenCalledTimes(1);
    });

    it('does not fire on not_ready, busy, failed, or stop', async () => {
      const onSessionStart = vi.fn();

      // not_ready: no start frame, no session.
      const notReady = makeHarness({ isReady: () => false, onSessionStart });
      const ctlNotReady = createRecordingController(notReady.deps);
      expect(await ctlNotReady.start()).toBe('not_ready');
      expect(onSessionStart).not.toHaveBeenCalled();

      // failed capture: start frame sent but no live session.
      const failed = makeHarness({
        startCapture: async () => false,
        onSessionStart,
      });
      const ctlFailed = createRecordingController(failed.deps);
      expect(await ctlFailed.start()).toBe('failed');
      expect(onSessionStart).not.toHaveBeenCalled();

      // busy while active: not a new session.
      const { deps } = makeHarness({ onSessionStart });
      const ctl = createRecordingController(deps);
      await ctl.start();
      expect(onSessionStart).toHaveBeenCalledTimes(1);
      expect(await ctl.start()).toBe('busy');
      expect(onSessionStart).toHaveBeenCalledTimes(1);

      // stop() itself is not a session start.
      ctl.stop();
      expect(onSessionStart).toHaveBeenCalledTimes(1);
    });

    it('does not fire when a pending start is cancelled before capture resolves', async () => {
      const onSessionStart = vi.fn();
      let resolveCapture: ((ok: boolean) => void) | null = null;
      const { deps } = makeHarness({
        startCapture: () =>
          new Promise<boolean>((resolve) => {
            resolveCapture = resolve;
          }),
        onSessionStart,
      });
      const ctl = createRecordingController(deps);

      const p = ctl.start();
      ctl.stop(); // cancel during pending capture
      resolveCapture!(true);
      expect(await p).toBe('stopped');
      expect(onSessionStart).not.toHaveBeenCalled();
    });

    it('fires again on each genuine restart after stop (new session each time)', async () => {
      const onSessionStart = vi.fn();
      const { deps } = makeHarness({ onSessionStart });
      const ctl = createRecordingController(deps);

      await ctl.start();
      ctl.stop();
      await ctl.start();
      ctl.stop();
      await ctl.start();

      expect(onSessionStart).toHaveBeenCalledTimes(3);
    });
  });

  it('supports repeated record/stop cycles without state leakage', async () => {
    const { deps, events } = makeHarness();
    const ctl = createRecordingController(deps);

    for (let i = 0; i < 3; i++) {
      expect(await ctl.start()).toBe('started');
      ctl.stop();
    }

    expect(events.filter((e) => e === 'sendStart')).toHaveLength(3);
    expect(events.filter((e) => e === 'sendStop')).toHaveLength(3);
    expect(events.filter((e) => e === 'startCapture')).toHaveLength(3);
  });
});

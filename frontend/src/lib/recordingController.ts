/**
 * VoiceSense AI — Recording Session Controller
 * Owns the protocol ordering invariant for a recording session:
 * a `start` frame is submitted before microphone capture is requested, so no
 * audio chunk can ever precede it, and exactly once per recording session.
 * Framework-agnostic and dependency-injected for focused unit testing.
 */

export type RecordingStartResult =
  | 'started'
  | 'busy'
  | 'not_ready'
  | 'failed'
  | 'stopped';

export interface RecordingControllerDeps {
  /** True only when the socket is connected AND the server acknowledged `ready`. */
  isReady: () => boolean;
  /** Sends the protocol `start` frame (language_hint/auth_token resolved by caller). */
  sendStartFrame: () => void;
  /** Sends the protocol `stop` frame. */
  sendStopFrame: () => void;
  /**
   * Starts microphone capture; resolves true on success, false on failure.
   * `shouldAbort` reports whether the start was cancelled while pending
   * (e.g. stop() ran during getUserMedia); capture should bail out early,
   * releasing any granted resources without producing audio.
   */
  startCapture: (shouldAbort?: () => boolean) => Promise<boolean>;
  /** Stops microphone capture and releases devices. */
  stopCapture: () => void;
  /** Optional callback when a start is attempted while the socket is not ready. */
  onNotReady?: () => void;
  /**
   * Optional callback fired once when a new recording session genuinely goes
   * live (capture confirmed after the `start` frame). Never fires on
   * busy/not_ready/failed/stopped attempts — callers use it to discard stale
   * per-session UI state such as the previous live transcript.
   */
  onSessionStart?: () => void;
  /** Optional callback whenever starting/active state may have changed. */
  onStateChange?: () => void;
}

export interface RecordingController {
  start(): Promise<RecordingStartResult>;
  stop(): void;
  isStarting(): boolean;
  isActive(): boolean;
}

export function createRecordingController(
  deps: RecordingControllerDeps
): RecordingController {
  let starting = false;
  let active = false;
  // True from the moment a `start` frame is submitted until the first stop()
  // tears the session down. Dedupes stop frames: repeated stop() calls while
  // a start is still pending (starting stays true until capture resolves)
  // must not each emit cleanup + a `stop` frame.
  let engaged = false;
  // Incremented on every stop(); a pending start compares its epoch after the
  // async capture resolves so a stop-during-start cannot leave a zombie stream.
  let epoch = 0;
  // Identifies the newest start() invocation. A superseded (cancelled) attempt
  // may still be in flight when a newer one begins; its finally block must not
  // clear `starting` or emit for state that now belongs to the newer attempt.
  let latestStart = 0;

  // Notifies the owner only when the *observable* state — isStarting() or
  // isActive() — actually changes. Raw flag mutations that don't alter the
  // observable pair (e.g. engaged clearing during an already-cancelled
  // pending start) produce no redundant callback.
  let lastNotifiedSig = '';
  const emit = () => {
    const sig = `${starting && engaged}|${active}`;
    if (sig !== lastNotifiedSig) {
      lastNotifiedSig = sig;
      deps.onStateChange?.();
    }
  };

  return {
    async start() {
      // Guard: never emit a duplicate `start` frame for one recording session.
      // A cancelled-but-unsettled attempt has engaged=false, so it does NOT
      // block a fresh attempt — its late resolution is epoch-guarded below.
      if (active || (starting && engaged)) {
        return 'busy';
      }

      // Guard: do not pretend recording restarted when the socket is not ready.
      if (!deps.isReady()) {
        deps.onNotReady?.();
        return 'not_ready';
      }

      // Ordering invariant: the `start` frame is submitted synchronously before
      // capture is requested. Audio chunks cannot exist until the capture
      // pipeline (getUserMedia -> AudioContext -> worklet) produces them, which
      // requires awaiting promises that resolve after this call.
      deps.sendStartFrame();
      starting = true;
      engaged = true;
      const myStart = ++latestStart;
      const startEpoch = epoch;
      emit();
      try {
        const captureStarted = await deps.startCapture(() => epoch !== startEpoch);
        if (startEpoch !== epoch) {
          // Superseded while capture was pending (stop() or a newer attempt
          // advanced the epoch). Shared state — engaged, active, starting —
          // may now belong to a newer attempt, so touch NOTHING here. The
          // capture layer self-cleans via shouldAbort/isStale.
          return 'stopped';
        }
        if (!captureStarted) {
          // Capture failed (e.g. permission denied). No audio was produced, and
          // the server-side `is_started` flag is harmless: the next `start`
          // frame resets session state, and no frames arrive in the meantime.
          engaged = false;
          return 'failed';
        }
        active = true;
        deps.onSessionStart?.();
        return 'started';
      } catch {
        // A rejected capture promise must not leave engaged stuck or escape
        // as an unhandled rejection. A stale rejection belongs to a
        // superseded attempt — report 'stopped' without touching shared state.
        if (startEpoch !== epoch) {
          return 'stopped';
        }
        engaged = false;
        return 'failed';
      } finally {
        // Only the newest attempt may clear `starting`/notify — an older
        // attempt settling must not clobber a newer pending start's state.
        if (myStart === latestStart) {
          starting = false;
          emit();
        }
      }
    },

    stop() {
      // Idempotent: only the first stop after a start frame performs teardown
      // and emits the `stop` frame — including repeated stops while a start
      // is still pending.
      if (!engaged) {
        return;
      }
      engaged = false;
      epoch += 1;
      active = false;
      // Preserve existing stop ordering: capture teardown, then `stop` frame.
      deps.stopCapture();
      deps.sendStopFrame();
      emit();
    },

    // `starting && engaged`: false immediately after a cancel even though the
    // pending capture promise has not resolved yet.
    isStarting: () => starting && engaged,
    isActive: () => active,
  };
}

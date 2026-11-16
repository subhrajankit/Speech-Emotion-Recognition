import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  MicrophoneControl,
  DURATION_WARNING_SECONDS,
} from '../components/audio/MicrophoneControl';

// NOTE: the elapsed-second ticking itself lives in an App.tsx useEffect and
// is not runtime-tested in this node-env suite. These tests pin the rendered
// contract: timer visibility, warning threshold, and non-live semantics.

describe('MicrophoneControl recording timer', () => {
  it('shows elapsed time with role="timer" while recording', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording onToggle={() => {}} elapsedSeconds={7} />
    );
    expect(html).toContain('role="timer"');
    expect(html).toContain('0:07');
    expect(html).toContain('aria-live="polite"'); // status line unchanged
  });

  it('hides the timer when not recording', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording={false} onToggle={() => {}} elapsedSeconds={12} />
    );
    expect(html).not.toContain('role="timer"');
    expect(html).not.toContain('0:12');
  });

  it('shows the duration warning at the threshold and not before', () => {
    // Chunk 9.8D: the warning must not imply the session timer is a
    // countdown to the server's per-utterance byte cap.
    const warningText = 'server discards utterances buffered beyond ~30 seconds';

    const before = renderToStaticMarkup(
      <MicrophoneControl
        isRecording
        onToggle={() => {}}
        elapsedSeconds={DURATION_WARNING_SECONDS - 1}
      />
    );
    expect(before).not.toContain(warningText);

    const atThreshold = renderToStaticMarkup(
      <MicrophoneControl
        isRecording
        onToggle={() => {}}
        elapsedSeconds={DURATION_WARNING_SECONDS}
      />
    );
    expect(atThreshold).toContain(warningText);
    expect(atThreshold).toContain('Recording session time');
    expect(atThreshold).not.toContain('limited to 30 seconds');
    expect(atThreshold).toContain('role="status"');
  });

  it('formats minutes correctly in the timer', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording onToggle={() => {}} elapsedSeconds={83} />
    );
    expect(html).toContain('1:23');
  });
});

// Chunk 9.7C: pending-start ("Starting microphone…") affordance.
describe('MicrophoneControl startup state', () => {
  it('shows startup feedback and a cancel label while isStarting', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording={false} isStarting onToggle={() => {}} />
    );
    expect(html).toContain('Starting microphone…');
    expect(html).toContain('Starting…');
    expect(html).toContain('Cancel microphone startup');
    expect(html).not.toContain('Press button or');
  });

  it('keeps the normal idle affordance when not starting', () => {
    const html = renderToStaticMarkup(
      <MicrophoneControl isRecording={false} onToggle={() => {}} />
    );
    expect(html).not.toContain('Starting microphone…');
    expect(html).toContain('Press button or');
  });
});

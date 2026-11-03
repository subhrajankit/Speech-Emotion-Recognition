/**
 * Audio processing utilities for VoiceSense AI.
 */

/**
 * Resamples Float32 audio samples to 16 kHz and encodes as 16-bit signed PCM (little-endian).
 */
export function resampleTo16kPCM16(
  input: Float32Array,
  sourceSampleRate: number
): Int16Array {
  if (!input || input.length === 0) {
    return new Int16Array(0);
  }

  const targetSampleRate = 16000;
  if (sourceSampleRate === targetSampleRate) {
    const output = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1.0, Math.min(1.0, input[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return output;
  }

  const ratio = sourceSampleRate / targetSampleRate;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Int16Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const sourceIndex = Math.floor(i * ratio);
    const s = Math.max(-1.0, Math.min(1.0, input[sourceIndex]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }

  return output;
}

/**
 * Calculates RMS volume level normalized to [0, 1].
 */
export function calculateRMS(samples: Float32Array | Int16Array): number {
  if (!samples || samples.length === 0) return 0;

  let sum = 0;
  const isFloat = samples instanceof Float32Array;

  for (let i = 0; i < samples.length; i++) {
    const val = isFloat ? samples[i] : samples[i] / 32768.0;
    sum += val * val;
  }

  const rms = Math.sqrt(sum / samples.length);
  return Math.min(1.0, rms * 4.0); // Scaled for visual response
}

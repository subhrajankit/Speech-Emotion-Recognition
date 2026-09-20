/**
 * AudioWorklet Processor for SenseAI Voice Assistant
 * Downsamples/converts Float32 input audio to 16kHz PCM 16-bit mono chunks
 */

class PCM16WorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.buffer = [];
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channelData = input[0]; // Channel 0 mono
    if (!channelData || channelData.length === 0) return true;

    // Resample from current sampleRate (e.g. 44100 or 48000) to 16000
    const sourceSampleRate = sampleRate;
    const ratio = sourceSampleRate / this.targetSampleRate;
    const outputLength = Math.floor(channelData.length / ratio);
    const pcm16Data = new Int16Array(outputLength);

    for (let i = 0; i < outputLength; i++) {
      const sourceIndex = Math.floor(i * ratio);
      let s = channelData[sourceIndex];
      // Clamp to [-1.0, 1.0]
      s = Math.max(-1.0, Math.min(1.0, s));
      // Convert to 16-bit signed integer
      pcm16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Post Int16Array buffer to main thread (transferred)
    this.port.postMessage(pcm16Data.buffer, [pcm16Data.buffer]);

    return true;
  }
}

registerProcessor('pcm16-worklet-processor', PCM16WorkletProcessor);

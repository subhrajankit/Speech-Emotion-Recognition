import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import torch
import torchaudio
from transformers import AutoModel
import time

wav_path = "tests/samples/sample_hindi_speech.wav"
print(f"Loading audio from {wav_path}...")
import soundfile as sf
data, sr = sf.read(wav_path, dtype="float32")
if data.ndim > 1:
    data = np.mean(data, axis=-1)

target_sample_rate = 16000
if sr != target_sample_rate:
    import numpy as np
    num_target = int(len(data) * target_sample_rate / sr)
    data = np.interp(
        np.linspace(0, len(data), num_target, endpoint=False),
        np.arange(len(data)),
        data
    ).astype(np.float32)

wav = torch.from_numpy(data).unsqueeze(0)

print(f"Resampled audio shape: {wav.shape}, sr: {target_sample_rate}, duration: {wav.shape[1]/target_sample_rate:.2f}s")

print("Loading IndicConformer-600m model (ai4bharat/indic-conformer-600m-multilingual)...")
t0 = time.perf_counter()
model = AutoModel.from_pretrained("ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True)
print(f"Model loaded in {time.perf_counter() - t0:.2f}s")

# Test CTC decoding
t1 = time.perf_counter()
transcription_ctc = model(wav, "hi", "ctc")
dur_ctc = time.perf_counter() - t1
print(f"CTC Transcription ({dur_ctc:.2f}s): {transcription_ctc}")

# Test RNNT decoding
t2 = time.perf_counter()
transcription_rnnt = model(wav, "hi", "rnnt")
dur_rnnt = time.perf_counter() - t2
print(f"RNNT Transcription ({dur_rnnt:.2f}s): {transcription_rnnt}")

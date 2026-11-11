# Speech Emotion Recognition (SER) Research & Experiments

This document records **only measured outputs persisted under [`docs/training/runs/`](./runs/)** alongside exact configuration and environment metadata. Any stage without saved run artifacts is explicitly marked **`NOT YET MEASURED`**.

For pipeline execution instructions, see [`README.md`](./README.md). For CREMA-D corpus background and acted-speech constraints, see [`../dataset/crema_d.md`](../dataset/crema_d.md).

---

## 1. Summary Benchmark Table

| Experiment / Run | Dataset | Split (`train / val / test`) | Accuracy | UAR (Balanced Acc) | Macro F1 | Weighted F1 | Source Artifact | Status |
|---|---|---|---|---|---|---|---|---|
| `run_20261025_193120` (Smoke) | Synthetic 30-sample manifest (`crema_d_smoke.yaml`) | `20 / 5 / 5` (`4 / 1 / 1` speakers) | `0.4000` | `0.1667` | `0.2000` | `0.4800` | [`metrics.json`](./runs/run_20261025_193120/metrics.json) | `smoke test, not a result` |
| Wav2Vec2-Base + MLP (`default.yaml`) | CREMA-D (Real audio) | Configured `70% / 15% / 15%` speaker-disjoint | **NOT YET MEASURED** | **NOT YET MEASURED** | **NOT YET MEASURED** | **NOT YET MEASURED** | — | Real dataset not downloaded |
| SenseVoiceSmall Zero-Shot Baseline | CREMA-D (Held-out Test) | `evaluated_samples: 0`, `skipped_samples: 5` (smoke) | **NOT YET MEASURED** | **NOT YET MEASURED** | **NOT YET MEASURED** | **NOT YET MEASURED** | [`sensevoice_baseline.json`](./runs/run_20261025_193120/sensevoice_baseline.json) | Pending real audio |

> [!WARNING]
> An earlier version of [`docs/training/README.md`](./README.md) reported `0.2500 / 0.2500 / 0.1000 / 0.0625` for the smoke run. Those values did not match the saved artifacts (`0.4000 / 0.1667 / 0.2000 / 0.4800` in `metrics.json` and `evaluation_summary.txt`) and have now been reconciled.

---

## 2. Detailed Breakdown: `run_20261025_193120` (Synthetic Smoke Run)

Recorded verbatim from [`evaluation_summary.txt`](./runs/run_20261025_193120/evaluation_summary.txt) and [`confusion_matrix.csv`](./runs/run_20261025_193120/confusion_matrix.csv):

- **Total Evaluated Test Samples:** `5` (synthetic fixtures; speaker distribution `happy: 3, angry: 2, neutral: 0, sad: 0`)
- **Per-Class Metrics:**
  - `angry`: Precision `0.0000`, Recall `0.0000`, F1 `0.0000`, Support `2`
  - `happy`: Precision `1.0000`, Recall `0.6667`, F1 `0.8000`, Support `3`
  - `neutral`: Precision `0.0000`, Recall `0.0000`, F1 `0.0000`, Support `0`
  - `sad`: Precision `0.0000`, Recall `0.0000`, F1 `0.0000`, Support `0`
- **Confusion Matrix (rows = actual, cols = `angry, happy, neutral, sad`):**
  - Actual `angry` (`2`): predicted `sad` (`2`)
  - Actual `happy` (`3`): predicted `happy` (`2`), `sad` (`1`)
  - Actual `neutral` (`0`): all `0`
  - Actual `sad` (`0`): all `0`
- **Zero-Shot Baseline Status:** [`sensevoice_baseline.json`](./runs/run_20261025_193120/sensevoice_baseline.json) records `"status": "NOT YET MEASURED"`, `"evaluated_samples": 0`, `"skipped_samples": 5`.

> [!NOTE]
> The 5-sample synthetic test split validates split logic, checkpoint saving, and evaluation report generation only. It proves **nothing** about real acoustic emotion accuracy on human speech or CREMA-D. Furthermore, CREMA-D consists of acted English sentences ([`crema_d.md`](../dataset/crema_d.md)); Hindi emotion recognition remains a separate unsolved research track (`emotion: null` on Hindi runtime turns).

---

## 3. Reproducibility Checklist

Metadata recorded in [`run_metadata.json`](./runs/run_20261025_193120/run_metadata.json) and training configs:

| Item | Smoke Run (`run_20261025_193120`) | Full Run Config (`default.yaml`) | Verification Status |
|---|---|---|---|
| **Random Seed** | `42` | `42` | Recorded |
| **Git Commit SHA** | `f1ae29cf62e6326df7c31c20b788dc4c89a423d1` | Tracked dynamically via `git rev-parse HEAD` | Recorded |
| **Config YAML** | `ai/training/config/crema_d_smoke.yaml` | `ai/training/config/default.yaml` | Tracked in repo |
| **Backbone / Model** | Synthetic NumPy smoke classifier | `facebook/wav2vec2-base` (`Apache-2.0`) | `default.yaml` |
| **Python / NumPy / SoundFile** | `3.13.14` / `2.5.3` / `0.14.0` (`win32`) | Local `.venv` Python `3.13+` | Recorded |
| **PyTorch / CUDA** | `torch_version: NOT_INSTALLED`, `cuda_available: False` | Target RTX 2050 (`4 GB` VRAM) / CPU | Full run `NOT YET MEASURED` |
| **Training Duration** | `0.86 s` (`epochs: 1`, `batch_size: 4`) | `~4.5 min` estimated (`15 epochs`) | Estimate **`unverified`** |

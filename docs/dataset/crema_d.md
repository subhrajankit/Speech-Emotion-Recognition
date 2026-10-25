# CREMA-D Dataset Specification & Acted-Speech Disclosure

**Document Status:** Source Specification  
**Dataset Name:** CREMA-D (Crowd-sourced Emotional Multimodal Actors Dataset)  
**License:** Open Database License (ODbL) v1.0 (Commercial & research use permitted with attribution)  
**Host URL:** [GitHub / Zenodo](https://github.com/CheyneyComputerScience/CREMA-D)

---

## 1. Critical Methodological Disclosure: Acted vs. Spontaneous Speech

> [!WARNING]
> **Acted-Speech Inflation Warning:**
> CREMA-D is an **ACTED speech corpus**. Professional actors were asked to deliberately simulate specific emotional states while reading standardized, emotionally neutral sentences in controlled studio acoustic conditions.
>
> **Implications for Performance Claims:**
> 1. Classification metrics achieved on CREMA-D (e.g. 70%–85% accuracy) reflect discrimination of **deliberate, exaggerated theatrical vocal acoustics**.
> 2. These metrics **must not be presented as real-world voice assistant performance**. In real-world conversational or customer interactions, emotional expression is predominantly spontaneous, subtle, and acoustic variations are substantially smaller.
> 3. True spontaneous conversational benchmarks (e.g., in Phase 10 observability) will yield lower confidence and require multimodal lexical fusion.

---

## 2. Dataset Specifications

- **Total Audio Clips**: 7,442 clips
- **Total Speakers**: 91 professional actors (48 male, 43 female)
- **Ethnic Diversity**: African American, Asian, Caucasian, and Hispanic actors representing broad acoustic demographic variety.
- **Language**: English
- **Audio Quality**: 16 kHz / 44.1 kHz WAV mono audio
- **Total Download Size**: ~550 MB (audio only)

---

## 3. Emotion Categories & Label Mapping

CREMA-D labels 6 categorical emotions across 4 intensity levels (Low, Medium, High, Unspecified):

| CREMA-D Code | Canonical Label | Target 4-Class Core | Description / Vocal Delivery |
|---|---|---|---|
| `NEU` | `neutral` | ✅ Included | Calm, uninflected statement reading |
| `HAP` | `happy` | ✅ Included | Cheerful, upbeat pitch and tempo |
| `SAD` | `sad` | ✅ Included | Lower pitch, subdued volume, slower cadence |
| `ANG` | `angry` | ✅ Included | Elevated pitch, high acoustic intensity, fast attack |
| `FEA` | `fearful` | Excluded in 4-class | High pitch, vocal tremor (available in 6-class config) |
| `DIS` | `disgusted` | Excluded in 4-class | Guttural, low pitch emphasis (available in 6-class config) |

---

## 4. Speaker-Independent Split Policy

To eliminate identity leakage (the model learning to recognize an actor's voice rather than emotional acoustics), splits are partitioned **strictly by actor ID**:

- **Train Split (70%)**: 65 actors (~5,200 clips)
- **Validation Split (15%)**: 13 actors (~1,100 clips)
- **Test Split (15%)**: 13 actors (~1,100 clips)
- **Leakage Invariant**:
  $$\text{Speakers}(\text{Train}) \cap \text{Speakers}(\text{Val}) \cap \text{Speakers}(\text{Test}) = \emptyset$$

Split manifests are serialized to `data/metadata/` with checksums and speaker IDs.
Audio files are stored locally in `data/raw/crema_d/` and are strictly excluded from version control via `.gitignore`.

"""
VoxLingua107 spoken language identification (LID) detector.

Implements the ``LanguageIdentifier`` protocol using the locally stored
SpeechBrain VoxLingua107 ECAPA-TDNN checkpoints (``models/voxlingua107/``).

Design constraints:
- Never downloads weights. Missing artifacts or missing dependencies
  (torch / speechbrain / hyperpyyaml) raise a clear ``RuntimeError`` that
  names the exact blocker; ``identify()`` degrades to ``("unknown", 0.0)``
  so the router's confidence threshold falls back to the default engine.
- Lazy, one-time loading guarded by a lock. ``identify()`` is safe to call
  from worker threads (``asyncio.to_thread``) and never loads per-utterance
  after the first successful load; a failed load is cached and not retried.
- Confidence is the model's own softmax posterior over the 107 VoxLingua107
  classes. It is never fabricated; unreliable outcomes return 0.0.
"""

import logging
import re
import threading
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ai.preprocessing.audio import resample_audio
from ai.routing.language_router import LanguageIdentifier

logger = logging.getLogger(__name__)


class VoxLingua107LanguageIdentifier(LanguageIdentifier):
    """
    Spoken LID backed by SpeechBrain's VoxLingua107 ECAPA-TDNN model.

    Replicates ``speechbrain.inference.classifiers.EncoderClassifier``
    forward pass manually because the local checkpoint layout
    (``label_encoder.ckpt`` instead of upstream ``label_encoder.txt``)
    is incompatible with ``Pretrainer`` path resolution, and automatic
    downloads are forbidden.
    """

    TARGET_SAMPLE_RATE = 16000

    # Files required in model_dir. label_encoder.ckpt uses SpeechBrain's
    # CategoricalEncoder literal format ('xx: Name' => index).
    REQUIRED_FILES = (
        "hyperparams.yaml",
        "embedding_model.ckpt",
        "classifier.ckpt",
        "label_encoder.ckpt",
    )

    # Model labels look like 'hi: Hindi'. The prefix is the ISO code, but the
    # upstream model card (HF issue #2396) documents two obsolete codes that
    # must be normalized to current ISO 639 codes.
    _LABEL_PATTERN = re.compile(r"^([A-Za-z]{2,3})\s*:")
    LABEL_CODE_ALIASES = {
        "iw": "he",  # Hebrew (obsolete ISO 639-1)
        "jw": "jv",  # Javanese (obsolete ISO 639-1)
    }

    def __init__(
        self,
        model_dir: str = "models/voxlingua107",
        device: str = "cpu",
        auto_load: bool = False,
    ):
        self.model_dir = Path(model_dir)
        self.device = device
        self.is_loaded = False

        self._compute_features = None
        self._mean_var_norm = None
        self._embedding_model = None
        self._classifier = None
        self._label_encoder = None

        self._lock = threading.Lock()
        self._load_error: Optional[BaseException] = None

        if auto_load:
            self.load()

    # ------------------------------------------------------------------
    # Artifact validation
    # ------------------------------------------------------------------
    def has_required_files(self) -> bool:
        """True when all checkpoint/config files exist locally."""
        return all((self.model_dir / name).is_file() for name in self.REQUIRED_FILES)

    def _check_artifacts(self) -> None:
        missing = [n for n in self.REQUIRED_FILES if not (self.model_dir / n).is_file()]
        if missing:
            raise RuntimeError(
                f"VoxLingua107 LID artifacts missing in '{self.model_dir}': "
                f"{', '.join(missing)}. Place the SpeechBrain "
                f"lang-id-voxlingua107-ecapa checkpoints locally; automatic "
                f"downloads are disabled."
            )

    # ------------------------------------------------------------------
    # Loading (one-time, lazy, thread-safe)
    # ------------------------------------------------------------------
    def load(self) -> None:
        """
        Loads hyperparameters, model weights, and the label encoder once.
        Raises RuntimeError naming the exact missing dependency or artifact.
        """
        if self.is_loaded:
            return

        self._check_artifacts()

        try:
            import torch  # noqa: F401  (validated here; used in _infer)
        except ImportError as e:
            raise RuntimeError(
                "VoxLingua107 LID requires PyTorch, which is not installed. "
                "Install the ML dependencies (requirements/ml.txt) to enable LID."
            ) from e

        try:
            import hyperpyyaml
        except ImportError as e:
            raise RuntimeError(
                "VoxLingua107 LID requires hyperpyyaml to parse "
                "hyperparams.yaml. Install speechbrain (which depends on "
                "hyperpyyaml) via requirements/ml.txt."
            ) from e

        try:
            from speechbrain.dataio.encoder import CategoricalEncoder
        except ImportError as e:
            raise RuntimeError(
                "VoxLingua107 LID requires speechbrain. Install it via "
                "requirements/ml.txt to enable LID."
            ) from e

        try:
            with open(self.model_dir / "hyperparams.yaml", "r", encoding="utf-8") as f:
                hparams = hyperpyyaml.load_hyperpyyaml(f)
            modules = hparams["modules"]
            self._compute_features = modules["compute_features"]
            self._mean_var_norm = modules["mean_var_norm"]
            self._embedding_model = modules["embedding_model"]
            self._classifier = modules["classifier"]

            import torch
            for name, ckpt_name, module in (
                ("embedding_model", "embedding_model.ckpt", self._embedding_model),
                ("classifier", "classifier.ckpt", self._classifier),
            ):
                state_dict = torch.load(
                    self.model_dir / ckpt_name,
                    map_location="cpu",
                    weights_only=True,
                )
                module.load_state_dict(state_dict, strict=True)

            self._label_encoder = CategoricalEncoder()
            self._label_encoder.load(str(self.model_dir / "label_encoder.ckpt"))

            if self.device and self.device != "cpu":
                for module in (
                    self._compute_features,
                    self._mean_var_norm,
                    self._embedding_model,
                    self._classifier,
                ):
                    if hasattr(module, "to"):
                        module.to(self.device)

            for module in (
                self._compute_features,
                self._mean_var_norm,
                self._embedding_model,
                self._classifier,
            ):
                if hasattr(module, "eval"):
                    module.eval()

            self.is_loaded = True
            logger.info(
                f"VoxLingua107 LID loaded from '{self.model_dir}' "
                f"({len(self._label_encoder)} languages, device={self.device})."
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize VoxLingua107 LID from '{self.model_dir}': {e}"
            ) from e

    def _ensure_loaded(self) -> None:
        """Loads once; caches and re-raises the first failure without retrying."""
        if self.is_loaded:
            return
        with self._lock:
            if self.is_loaded:
                return
            if self._load_error is not None:
                raise self._load_error
            try:
                self.load()
            except Exception as e:
                self._load_error = e
                logger.error(f"VoxLingua107 LID unavailable: {e}")
                raise

    # ------------------------------------------------------------------
    # Label mapping
    # ------------------------------------------------------------------
    @classmethod
    def map_label_to_code(cls, label: Optional[str]) -> str:
        """
        Converts a VoxLingua107 label ('hi: Hindi') into a bare ISO language
        code ('hi'). Returns 'unknown' for empty, malformed, or unparseable
        labels — never guesses.
        """
        if not label:
            return "unknown"
        match = cls._LABEL_PATTERN.match(label.strip())
        if not match:
            return "unknown"
        code = match.group(1).lower()
        return cls.LABEL_CODE_ALIASES.get(code, code)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def _prepare_audio(self, audio: np.ndarray, sample_rate: int) -> Optional[np.ndarray]:
        """
        Validates and normalizes input audio to 16 kHz mono float32.
        Returns None for empty, silent, or non-finite input.
        """
        if audio is None:
            return None
        arr = np.asarray(audio)
        if arr.size == 0:
            return None
        arr = arr.astype(np.float32, copy=False)
        if arr.ndim > 1:
            arr = arr.reshape(-1) if arr.shape[0] == 1 else arr.mean(axis=-1)
        arr = np.asarray(arr, dtype=np.float32).reshape(-1)
        if not np.isfinite(arr).all():
            return None
        if float(np.max(np.abs(arr))) < 1e-4:
            return None  # silence / effectively empty
        if sample_rate and sample_rate != self.TARGET_SAMPLE_RATE:
            arr = resample_audio(arr, int(sample_rate), self.TARGET_SAMPLE_RATE)
        if len(arr) == 0:
            return None
        return np.clip(arr, -1.0, 1.0)

    def _infer(self, audio: np.ndarray) -> Tuple[str, float]:
        """
        Runs the ECAPA-TDNN forward pass and returns
        (raw_model_label, top1_softmax_confidence).
        """
        import torch

        wav = torch.from_numpy(audio).unsqueeze(0).to(self.device)
        wav_lens = torch.ones(wav.shape[0], device=self.device)

        with torch.no_grad():
            feats = self._compute_features(wav)
            feats = self._mean_var_norm(feats, wav_lens)
            embeddings = self._embedding_model(feats, wav_lens)
            log_probs = self._classifier(embeddings).squeeze(1)
            probs = torch.softmax(log_probs, dim=-1)
            score, index = torch.max(probs, dim=-1)
            labels = self._label_encoder.decode_torch(index)

        label = labels[0] if labels else ""
        return label, float(score.item())

    def identify(self, audio: np.ndarray, sample_rate: int = 16000) -> Tuple[str, float]:
        """
        Predicts (language_code, confidence) for a 16 kHz float32 waveform.

        Returns ("unknown", 0.0) for invalid/silent audio, missing
        artifacts, missing dependencies, or any inference failure — the
        router treats 0.0 confidence as below threshold and falls back to
        the default engine.
        """
        prepared = self._prepare_audio(audio, sample_rate)
        if prepared is None:
            return "unknown", 0.0

        try:
            self._ensure_loaded()
            raw_label, confidence = self._infer(prepared)
            return self.map_label_to_code(raw_label), confidence
        except Exception as e:
            # Load failures are already logged once inside _ensure_loaded;
            # inference-time failures are logged here.
            if e is not self._load_error:
                logger.warning(f"VoxLingua107 LID inference failed: {e}")
            return "unknown", 0.0

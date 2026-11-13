"""
Offline English ASR evaluation for SenseVoiceSpeechEngine (iic/SenseVoiceSmall).

EVALUATION-ONLY TOOL — not part of the runtime pipeline, not run in CI.
Requires the ML environment (.venv with torch + funasr). No production
inference, routing, or configuration is modified by this script.

Usage:
    .venv/Scripts/python.exe scripts/eval_english_asr.py \
        --manifest data/english_asr_eval/manifests/english_asr_eval_manifest.csv \
        --dataset-root data/english_asr_eval \
        --modes auto,en [--split dev|heldout|all] [--device cpu]

Manifest columns (see data/english_asr_eval/README.md):
    recording_id, speaker_id, audio_path, reference_path, recording_type,
    duration_seconds, sample_rate, channels, accent_notes,
    consent_confirmed, split

Normalization policy (applied identically to hypothesis and reference):
  - Unicode NFKC, lowercase.
  - Punctuation removed EXCEPT apostrophes inside words (contractions like
    "don't" are preserved as single tokens); leading/trailing apostrophes
    stripped.
  - All whitespace collapsed to single spaces; tokens split on whitespace.
  - No stop-word removal, no number-word conversion, no filler stripping —
    normalization must not silently erase transcription errors.

Metrics:
  - WER = (S + D + I) / N_ref_words   (corpus-level and per-file)
  - CER = edit_distance(chars) / N_ref_chars
  - Edit counts via Levenshtein DP on word/char sequences (stdlib only).

Detected language: result.language and debug.raw_tags are reported per file
SEPARATELY from WER/CER — tag correctness is a routing signal, not a
transcription-quality metric.
"""

import argparse
import csv
import json
import sys
import unicodedata
from pathlib import Path

# Allow `python scripts/eval_english_asr.py` from the repo root without
# PYTHONPATH: repo root is the parent of this script's directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np


def normalize_text(text: str) -> str:
    """Case/punctuation/whitespace normalization per module docstring."""
    text = unicodedata.normalize("NFKC", text).lower()
    # Keep intra-word apostrophes (contractions); drop all other punctuation.
    out = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif ch == "'":
            out.append(ch)
        else:
            out.append(" ")
    tokens = []
    for tok in "".join(out).split():
        tok = tok.strip("'")
        if tok:
            tokens.append(tok)
    return " ".join(tokens)


def _edit_counts(ref_seq, hyp_seq):
    """
    Levenshtein DP returning (substitutions, deletions, insertions).

    Minimizes TOTAL edit count (S+D+I). Ties are broken deterministically:
    diagonal (match/substitution) preferred over deletion over insertion.
    """
    n, m = len(ref_seq), len(hyp_seq)
    # cell = (total_edits, priority, subs, dels, inss); lower tuple wins.
    # priority: diagonal=0, deletion=1, insertion=2.
    dp = [[None] * (m + 1) for _ in range(n + 1)]

    def cell(total, prio, s, d, i):
        return (total, prio, s, d, i)

    dp[0][0] = cell(0, 0, 0, 0, 0)
    for j in range(1, m + 1):
        dp[0][j] = cell(j, 2, 0, 0, j)
    for i in range(1, n + 1):
        dp[i][0] = cell(i, 1, 0, i, 0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s0, d0, i0 = dp[i - 1][j - 1][2], dp[i - 1][j - 1][3], dp[i - 1][j - 1][4]
            cost = 0 if ref_seq[i - 1] == hyp_seq[j - 1] else 1
            cand_diag = cell(dp[i - 1][j - 1][0] + cost, 0, s0 + cost, d0, i0)
            cand_del = cell(dp[i - 1][j][0] + 1, 1, dp[i - 1][j][2], dp[i - 1][j][3] + 1, dp[i - 1][j][4])
            cand_ins = cell(dp[i][j - 1][0] + 1, 2, dp[i][j - 1][2], dp[i][j - 1][3], dp[i][j - 1][4] + 1)
            dp[i][j] = min(cand_diag, cand_del, cand_ins)
    _, _, s, d, i = dp[n][m]
    return s, d, i


def wer_cer(reference: str, hypothesis: str):
    """Returns dict with word/char edit counts and rates."""
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)

    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()
    s, d, i = _edit_counts(ref_words, hyp_words)
    n_words = len(ref_words)
    wer = (s + d + i) / n_words if n_words else (0.0 if not hyp_words else 1.0)

    ref_chars = list(ref_norm.replace(" ", ""))
    hyp_chars = list(hyp_norm.replace(" ", ""))
    cs, cd, ci = _edit_counts(ref_chars, hyp_chars)
    n_chars = len(ref_chars)
    cer = (cs + cd + ci) / n_chars if n_chars else (0.0 if not hyp_chars else 1.0)

    return {
        "wer": wer,
        "cer": cer,
        "ref_words": n_words,
        "substitutions": s,
        "deletions": d,
        "insertions": i,
        "char_edits": cs + cd + ci,
        "ref_chars": n_chars,
        "normalized_reference": ref_norm,
        "normalized_hypothesis": hyp_norm,
    }


def load_manifest(path: Path, split: str):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if split != "all" and row.get("split", "").strip() != split:
                continue
            consent = row.get("consent_confirmed", "").strip().lower()
            rtype = row.get("recording_type", "").strip().lower()
            if rtype == "synthetic_tts":
                # Generated audio has no human subject; consent is N/A.
                if consent not in ("yes", "n/a"):
                    continue
            elif consent != "yes":
                # Human recordings require explicit consent.
                continue
            rows.append(row)
    return rows


REQUIRED_COLUMNS = {
    "recording_id", "speaker_id", "audio_path", "reference_path",
    "recording_type", "split", "consent_confirmed",
}
VALID_SPLITS = {"dev", "heldout"}
SPEAKER_ID_PREFIX = "EN_S"


def validate_rows(rows, dataset_root: Path):
    """
    Dataset-readiness checks. Returns list of error strings (empty = valid).
    Runs before any model load so bad manifests fail fast and clearly.
    """
    errors = []
    seen_ids = set()
    for idx, row in enumerate(rows, start=2):  # line 2 = first data row
        rid = (row.get("recording_id") or "").strip()
        tag = f"row {idx} ({rid or '<no recording_id>'})"

        missing_cols = REQUIRED_COLUMNS - set(row.keys())
        if missing_cols:
            errors.append(f"{tag}: missing columns {sorted(missing_cols)}")
            continue

        if not rid:
            errors.append(f"row {idx}: empty recording_id")
        elif rid in seen_ids:
            errors.append(f"{tag}: duplicate recording_id '{rid}'")
        else:
            seen_ids.add(rid)

        split = (row.get("split") or "").strip()
        if split not in VALID_SPLITS:
            errors.append(f"{tag}: split '{split}' invalid (expected dev|heldout)")

        speaker = (row.get("speaker_id") or "").strip()
        if not speaker:
            errors.append(f"{tag}: empty speaker_id")
        elif not speaker.startswith(SPEAKER_ID_PREFIX):
            errors.append(
                f"{tag}: speaker_id '{speaker}' should look like EN_S01 "
                "(anonymous IDs only — no real names)"
            )

        for col in ("audio_path", "reference_path"):
            raw = (row.get(col) or "").strip()
            if not raw:
                errors.append(f"{tag}: empty {col}")
                continue
            p = Path(raw)
            if not p.is_absolute():
                p = dataset_root / p
            if not p.is_file():
                errors.append(f"{tag}: {col} not found: {p}")

        ref_raw = (row.get("reference_path") or "").strip()
        if ref_raw:
            ref_p = Path(ref_raw)
            if not ref_p.is_absolute():
                ref_p = dataset_root / ref_p
            if ref_p.is_file() and not ref_p.read_text(
                encoding="utf-8", errors="replace"
            ).strip():
                errors.append(f"{tag}: reference transcript is empty: {ref_p}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path,
                        help="Base dir for relative audio_path/reference_path")
    parser.add_argument("--modes", default="auto,en",
                        help="Comma-separated engine modes: 'auto' (language=auto) and/or 'en' (language=en)")
    parser.add_argument("--split", default="all", choices=["dev", "heldout", "all"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", type=Path, default=None,
                        help="Optional JSON report path")
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    valid = {"auto": None, "en": "en"}
    bad = [m for m in modes if m not in valid]
    if bad:
        print(f"Invalid modes {bad}; allowed: auto, en", file=sys.stderr)
        return 2

    rows = load_manifest(args.manifest, args.split)
    if not rows:
        print("No manifest rows matched (check split/consent fields).")
        return 1

    validation_errors = validate_rows(rows, args.dataset_root)
    if validation_errors:
        print("Manifest validation failed:", file=sys.stderr)
        for e in validation_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    # Late import: heavy ML deps only needed when actually evaluating.
    from ai.inference.sensevoice import SenseVoiceSpeechEngine
    from ai.preprocessing.audio import load_and_preprocess_audio

    engine = SenseVoiceSpeechEngine(device=args.device, auto_load=True)

    report = {"modes": {}, "files": len(rows)}
    for mode in modes:
        lang_hint = valid[mode]
        per_file = []
        tot = {"ref_words": 0, "s": 0, "d": 0, "i": 0, "cs": 0, "ref_chars": 0}
        detected = {}
        for row in rows:
            audio_path = Path(row["audio_path"])
            ref_path = Path(row["reference_path"])
            if not audio_path.is_absolute():
                audio_path = args.dataset_root / audio_path
            if not ref_path.is_absolute():
                ref_path = args.dataset_root / ref_path
            reference = ref_path.read_text(encoding="utf-8").strip()
            audio = load_and_preprocess_audio(str(audio_path), target_sr=16000)
            result = engine.transcribe(audio, sample_rate=16000, language_hint=lang_hint)
            m = wer_cer(reference, result.transcript)
            per_file.append({
                "recording_id": row["recording_id"],
                "speaker_id": row["speaker_id"],
                "split": row.get("split", ""),
                "detected_language": result.language,
                "detected_language_source": "sensevoice_tag",
                "transcript": result.transcript,
                **{k: m[k] for k in ("wer", "cer", "ref_words", "substitutions",
                                     "deletions", "insertions", "ref_chars")},
            })
            # Corpus-level aggregation uses raw edit counts / raw reference
            # lengths — never an unweighted mean of per-file rates.
            tot["s"] += m["substitutions"]; tot["d"] += m["deletions"]; tot["i"] += m["insertions"]
            tot["ref_words"] += m["ref_words"]
            tot["cs"] += m["char_edits"]
            tot["ref_chars"] += m["ref_chars"]
            detected[result.language] = detected.get(result.language, 0) + 1

        word_edits = tot["s"] + tot["d"] + tot["i"]
        agg = {
            "wer": word_edits / tot["ref_words"] if tot["ref_words"] else None,
            "cer": tot["cs"] / tot["ref_chars"] if tot["ref_chars"] else None,
            "total_ref_words": tot["ref_words"],
            "substitutions": tot["s"], "deletions": tot["d"], "insertions": tot["i"],
            "detected_language_counts": detected,
        }
        report["modes"][mode] = {"aggregate": agg, "per_file": per_file}

        print(f"\n=== mode language_hint={lang_hint!r} ({mode}) ===")
        for pf in per_file:
            print(f"{pf['recording_id']:>10} spk={pf['speaker_id']:<7} "
                  f"lang_tag={pf['detected_language']:<7} "
                  f"WER={pf['wer']:.3f} CER={pf['cer']:.3f} "
                  f"(S{pf['substitutions']}/D{pf['deletions']}/I{pf['insertions']})")
        print(f"AGGREGATE WER={agg['wer']:.4f} CER={agg['cer']:.4f} "
              f"words={agg['total_ref_words']} S={agg['substitutions']} "
              f"D={agg['deletions']} I={agg['insertions']} tags={detected}")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"\nReport written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

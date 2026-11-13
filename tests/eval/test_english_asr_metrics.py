"""
Deterministic unit tests for scripts/eval_english_asr.py metric functions.

Pure-stdlib tests — no torch/funasr/model weights required (CI-safe).
"""

import pytest

from scripts.eval_english_asr import normalize_text, wer_cer, _edit_counts


# ----------------------------------------------------------------------
# Normalization
# ----------------------------------------------------------------------

def test_normalize_lowercase_punctuation_whitespace():
    assert normalize_text("  Hello,   WORLD!  ") == "hello world"


def test_normalize_preserves_contractions():
    assert normalize_text("Don't stop, it's fine.") == "don't stop it's fine"


def test_normalize_strips_edge_apostrophes():
    assert normalize_text("'quoted' '") == "quoted"


def test_normalize_unicode_nfc_and_compat():
    # NFKC compatibility + lowercase; accents preserved as letters.
    assert normalize_text("CAFÉ—naïve") == "café naïve"


# ----------------------------------------------------------------------
# Edit counts (minimum Levenshtein S/D/I)
# ----------------------------------------------------------------------

def test_edit_counts_exact_match():
    assert _edit_counts(["a", "b"], ["a", "b"]) == (0, 0, 0)


def test_edit_counts_one_substitution():
    assert _edit_counts(["the", "cat", "sat"], ["the", "dog", "sat"]) == (1, 0, 0)


def test_edit_counts_one_deletion():
    assert _edit_counts(["the", "cat", "sat"], ["the", "sat"]) == (0, 1, 0)


def test_edit_counts_one_insertion():
    assert _edit_counts(["the", "sat"], ["the", "cat", "sat"]) == (0, 0, 1)


def test_edit_counts_prefers_substitution_over_indel_pair():
    # "the" -> "a" must be ONE substitution, not del+ins (total=2).
    s, d, i = _edit_counts(["the"], ["a"])
    assert (s, d, i) == (1, 0, 0)
    assert s + d + i == 1


# ----------------------------------------------------------------------
# wer_cer end-to-end
# ----------------------------------------------------------------------

def test_wer_cer_exact_match():
    m = wer_cer("The quick brown fox.", "the quick brown fox")
    assert m["wer"] == 0.0 and m["cer"] == 0.0
    assert m["substitutions"] == m["deletions"] == m["insertions"] == 0


def test_wer_cer_reported_discrepancy_case():
    """Regression: 'the'->'a' is 1 substitution, WER=1/6 (not 2 errors)."""
    m = wer_cer("The cat sat on the mat.", "The cat sat on a mat")
    assert m["ref_words"] == 6
    assert (m["substitutions"], m["deletions"], m["insertions"]) == (1, 0, 0)
    assert m["wer"] == pytest.approx(1 / 6)


def test_wer_cer_one_deletion():
    m = wer_cer("the cat sat", "the sat")
    assert (m["substitutions"], m["deletions"], m["insertions"]) == (0, 1, 0)
    assert m["wer"] == pytest.approx(1 / 3)


def test_wer_cer_one_insertion():
    m = wer_cer("the sat", "the cat sat")
    assert (m["substitutions"], m["deletions"], m["insertions"]) == (0, 0, 1)
    assert m["wer"] == pytest.approx(1 / 2)


def test_wer_cer_empty_hypothesis():
    m = wer_cer("hello world", "")
    assert m["wer"] == 1.0
    assert m["deletions"] == 2


def test_wer_cer_empty_reference():
    m = wer_cer("", "hello")
    assert m["wer"] == 1.0  # all-insertion against empty ref
    assert m["insertions"] == 1


def test_wer_cer_both_empty():
    m = wer_cer("", "")
    assert m["wer"] == 0.0 and m["cer"] == 0.0


def test_wer_cer_contraction_tokenization():
    # "don't" is one token; "do not" is two — a real WER difference, not hidden.
    m_same = wer_cer("I don't know.", "i don't know")
    assert m_same["wer"] == 0.0
    m_diff = wer_cer("I don't know.", "i do not know")
    assert m_diff["wer"] > 0.0


def test_wer_cer_cer_uses_char_level():
    m = wer_cer("cat", "cut")
    assert m["wer"] == pytest.approx(1 / 1)
    assert m["cer"] == pytest.approx(1 / 3)


# ----------------------------------------------------------------------
# Manifest validation (dataset readiness)
# ----------------------------------------------------------------------

from pathlib import Path
from scripts.eval_english_asr import validate_rows


def _row(**kw):
    base = {
        "recording_id": "EN_R01", "speaker_id": "EN_S01", "audio_path": "audio/a.wav",
        "reference_path": "references/a.txt", "recording_type": "read",
        "split": "dev", "consent_confirmed": "yes",
    }
    base.update(kw)
    return base


def test_validate_rows_accepts_valid(tmp_path):
    (tmp_path / "audio").mkdir(); (tmp_path / "references").mkdir()
    (tmp_path / "audio" / "a.wav").write_bytes(b"x")
    (tmp_path / "references" / "a.txt").write_text("hello world")
    assert validate_rows([_row()], tmp_path) == []


def test_validate_rows_duplicate_id(tmp_path):
    (tmp_path / "audio").mkdir(); (tmp_path / "references").mkdir()
    for n in ("a", "b"):
        (tmp_path / "audio" / f"{n}.wav").write_bytes(b"x")
        (tmp_path / "references" / f"{n}.txt").write_text("hi")
    rows = [_row(recording_id="EN_R01", audio_path="audio/a.wav", reference_path="references/a.txt"),
            _row(recording_id="EN_R01", audio_path="audio/b.wav", reference_path="references/b.txt")]
    errs = validate_rows(rows, tmp_path)
    assert any("duplicate" in e for e in errs)


def test_validate_rows_missing_files_and_bad_split(tmp_path):
    errs = validate_rows([_row(split="train", audio_path="nope.wav", reference_path="nope.txt")], tmp_path)
    assert any("invalid" in e for e in errs)
    assert sum("not found" in e for e in errs) == 2


def test_validate_rows_empty_reference_and_bad_speaker(tmp_path):
    (tmp_path / "audio").mkdir(); (tmp_path / "references").mkdir()
    (tmp_path / "audio" / "a.wav").write_bytes(b"x")
    (tmp_path / "references" / "a.txt").write_text("   ")
    errs = validate_rows([_row(speaker_id="John Doe")], tmp_path)
    assert any("EN_S01" in e for e in errs)
    assert any("empty" in e for e in errs)


# ----------------------------------------------------------------------
# Consent handling in load_manifest (Chunk 4.4B)
# ----------------------------------------------------------------------

import csv
from scripts.eval_english_asr import load_manifest


def _write_manifest(tmp_path, rows):
    p = tmp_path / "m.csv"
    cols = ["recording_id","speaker_id","audio_path","reference_path",
            "recording_type","split","consent_confirmed"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return p


def _mrow(rid, rtype, consent, split="dev"):
    return {"recording_id": rid, "speaker_id": "EN_S01", "audio_path": "a.wav",
            "reference_path": "a.txt", "recording_type": rtype,
            "split": split, "consent_confirmed": consent}


def test_synthetic_tts_na_consent_accepted(tmp_path):
    p = _write_manifest(tmp_path, [_mrow("EN_SYN_001", "synthetic_tts", "n/a")])
    assert len(load_manifest(p, "dev")) == 1


def test_synthetic_tts_yes_consent_accepted(tmp_path):
    p = _write_manifest(tmp_path, [_mrow("EN_SYN_001", "synthetic_tts", "yes")])
    assert len(load_manifest(p, "dev")) == 1


def test_human_yes_accepted(tmp_path):
    p = _write_manifest(tmp_path, [_mrow("EN_R01", "read", "yes")])
    assert len(load_manifest(p, "dev")) == 1


@pytest.mark.parametrize("consent", ["n/a", "no", "", "maybe"])
def test_human_non_yes_consent_rejected(tmp_path, consent):
    p = _write_manifest(tmp_path, [_mrow("EN_R01", "read", consent)])
    assert load_manifest(p, "dev") == []


def test_missing_consent_column_rejected_for_human(tmp_path):
    p = _write_manifest(tmp_path, [_mrow("EN_R01", "read", "")])
    assert load_manifest(p, "dev") == []


def test_split_filter_still_applies(tmp_path):
    p = _write_manifest(tmp_path, [_mrow("EN_SYN_001", "synthetic_tts", "n/a", split="heldout")])
    assert load_manifest(p, "dev") == []
    assert len(load_manifest(p, "heldout")) == 1


def test_header_only_manifest_yields_no_rows(tmp_path):
    p = _write_manifest(tmp_path, [])
    assert load_manifest(p, "dev") == []
    assert load_manifest(p, "all") == []

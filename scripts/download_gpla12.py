from __future__ import annotations

"""
Download GPLA-12 public dataset from GitHub (best-effort) and convert to WAV.

Source repo:
- https://github.com/Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12

Zip:
- https://github.com/Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12/archive/refs/heads/main.zip

Notes:
- This script avoids non-stdlib audio deps (no soundfile).
- It can convert .npy/.csv/.txt numeric arrays to 16-bit PCM WAV.
- .mat conversion requires SciPy; if unavailable, .mat files are skipped.
"""

import argparse
import csv
import re
import shutil
import wave
import zipfile
from collections import Counter
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np


DATA = Path("data")
CACHE = DATA / "_cache"
OUT = DATA / "audio" / "gpla12_wav"
META = OUT / "metadata.csv"

ZIP_URL = "https://github.com/Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12/archive/refs/heads/main.zip"
DEFAULT_NORMAL_CLASS_IDS = "1,2,3,4"
DEFAULT_UNCERTAIN_CLASS_IDS = "9,10,11,12"

_LEAK_PAT = re.compile(r"(leak|hole|crack|burst|fault|defect)", re.IGNORECASE)
_NORMAL_PAT = re.compile(r"(normal|baseline|nominal|healthy|no[_-]?leak)", re.IGNORECASE)


def _ensure_dirs() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)


def _label_from_path(p: Path) -> tuple[str, str, str, str]:
    s = str(p).lower()
    if _LEAK_PAT.search(s) and not _NORMAL_PAT.search(s):
        return ("leak", "path_keyword", "high_confidence", "Path keyword strongly indicates leak.")
    if _NORMAL_PAT.search(s) and not _LEAK_PAT.search(s):
        return ("normal", "path_keyword", "high_confidence", "Path keyword strongly indicates normal.")
    # Unknown: route to investigate lane to avoid overconfident leak labels.
    return ("investigate", "path_keyword_ambiguous", "uncertain", "Ambiguous file naming; routed to investigate.")


def _write_wav(sig: np.ndarray, out: Path, sr: int) -> None:
    sig = np.asarray(sig).reshape(-1).astype(np.float32)
    if sig.size == 0:
        raise ValueError("empty signal")
    mx = float(np.max(np.abs(sig)))
    if mx > 1.0e-9:
        sig = sig / mx
    pcm16 = (np.clip(sig, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(pcm16.tobytes())


def _convert_any(p: Path, out: Path, sr: int) -> bool:
    ext = p.suffix.lower()
    if ext == ".wav":
        shutil.copy2(p, out)
        return True
    if ext == ".npy":
        _write_wav(np.load(p), out, sr)
        return True
    if ext in [".csv", ".txt"]:
        arr = np.loadtxt(p, delimiter="," if ext == ".csv" else None)
        _write_wav(arr, out, sr)
        return True
    if ext == ".mat":
        try:
            from scipy.io import loadmat  # type: ignore
        except Exception:
            return False
        mat = loadmat(p)
        for k, v in mat.items():
            if k.startswith("__"):
                continue
            if isinstance(v, np.ndarray) and np.issubdtype(v.dtype, np.number) and v.size > 100:
                _write_wav(v, out, sr)
                return True
    return False


def _is_likely_tabular_pack_file(p: Path) -> bool:
    name = p.name.lower()
    return name in {"data.csv", "label.csv", "lable.csv", "data.xlsx", "lable.xlsx", "label.xlsx"}


def _convert_v1_table(
    *,
    root: Path,
    sr: int,
    max_files: int,
    normal_class_ids: set[int],
    uncertain_class_ids: set[int],
) -> list[dict[str, str]]:
    """
    GPLA-12 v1 ships as tabular matrices:
    - data/data_v1/data.csv    -> shape (N, T), one row = one sample
    - data/data_v1/label.csv   -> shape (N, 1), class id in [1..12]
    """
    data_csv = root / "data" / "data_v1" / "data.csv"
    label_csv = root / "data" / "data_v1" / "label.csv"
    if not data_csv.exists() or not label_csv.exists():
        return []

    data = np.loadtxt(data_csv, delimiter=",")
    labels = np.loadtxt(label_csv, delimiter=",", dtype=np.int64)
    if data.ndim != 2:
        raise RuntimeError(f"Unexpected GPLA-12 data.csv shape: {data.shape}")
    if labels.ndim > 1:
        labels = labels.reshape(-1)
    if data.shape[0] != labels.shape[0]:
        raise RuntimeError(f"data/label row mismatch: data={data.shape[0]} labels={labels.shape[0]}")

    n = int(min(max_files, data.shape[0]))
    # Deterministic shuffle to avoid selecting only the first class block.
    rng = np.random.default_rng(42)
    pick_idx = rng.permutation(data.shape[0])[:n]

    rows: list[dict[str, str]] = []
    for i, ridx in enumerate(pick_idx, start=1):
        cls = int(labels[ridx])
        if cls in normal_class_ids:
            label = "normal"
            label_confidence = "high_confidence"
            label_source = "class_map_default"
            review_note = "Class id mapped to normal."
        elif cls in uncertain_class_ids:
            label = "investigate"
            label_confidence = "uncertain"
            label_source = "class_map_uncertain"
            review_note = "Class id marked uncertain; routed to investigate."
        else:
            label = "leak"
            label_confidence = "high_confidence"
            label_source = "class_map_default"
            review_note = "Class id mapped to leak."
        out = OUT / f"gpla12_{label}_{i:05d}.wav"
        _write_wav(data[int(ridx)], out, sr)
        rows.append(
            {
                "out_wav": out.as_posix(),
                "label": label,
                "source_path": f"data/data_v1/data.csv[row={int(ridx)}]",
                "source_ext": ".csv_row",
                "source_class_id": str(cls),
                "normal_class_ids": ",".join(str(x) for x in sorted(normal_class_ids)),
                "uncertain_class_ids": ",".join(str(x) for x in sorted(uncertain_class_ids)),
                "label_source": label_source,
                "label_confidence": label_confidence,
                "review_note": review_note,
            }
        )
    return rows


def main(
    *,
    max_files: int,
    sr: int,
    clean: bool,
    normal_class_ids: set[int],
    uncertain_class_ids: set[int],
) -> None:
    _ensure_dirs()
    if clean and OUT.exists():
        shutil.rmtree(OUT)
        OUT.mkdir(parents=True, exist_ok=True)

    zpath = CACHE / "gpla12_main.zip"
    if not zpath.exists():
        print(f"Downloading {ZIP_URL}")
        urlretrieve(ZIP_URL, zpath)

    tmp = CACHE / "gpla12_repo"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "r") as z:
        z.extractall(tmp)

    roots = list(tmp.glob("acoustic-leakage-dataset-GPLA-12-*"))
    if not roots:
        raise SystemExit("Could not locate extracted GPLA-12 root folder.")
    root = roots[0]

    data_root = root / "data"
    if not data_root.exists():
        raise SystemExit("GPLA-12 archive does not include a data/ directory.")

    # First pass: try file-based conversion from newest versions.
    # Some GPLA-12 revisions publish tabular archives (v1/v2), where direct file conversion is not applicable.
    exts = {".wav", ".npy", ".csv", ".txt", ".mat"}
    candidates = sorted(data_root.glob("data_v*"), reverse=True)
    if not candidates:
        candidates = [data_root]

    meta_rows: list[dict[str, str]] = []
    for data_dir in candidates:
        files = sorted([p for p in data_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts])
        files = [p for p in files if not _is_likely_tabular_pack_file(p)]
        if not files:
            continue
        print(f"Using file-based data dir: {data_dir}")
        files = files[: int(max_files)]
        for i, p in enumerate(files, start=1):
            label, label_source, label_confidence, review_note = _label_from_path(p)
            out = OUT / f"gpla12_{label}_{i:05d}.wav"
            converted = _convert_any(p, out, sr)
            if not converted:
                continue
            meta_rows.append(
                {
                    "out_wav": out.as_posix(),
                    "label": label,
                    "source_path": str(p.relative_to(root)).replace("\\", "/"),
                    "source_ext": p.suffix.lower(),
                    "source_class_id": "",
                    "normal_class_ids": ",".join(str(x) for x in sorted(normal_class_ids)),
                    "uncertain_class_ids": ",".join(str(x) for x in sorted(uncertain_class_ids)),
                    "label_source": label_source,
                    "label_confidence": label_confidence,
                    "review_note": review_note,
                }
            )
        if meta_rows:
            break

    # Fallback: v1 tabular conversion.
    if not meta_rows:
        print("File-based conversion found no usable samples; trying data_v1 tabular fallback.")
        meta_rows = _convert_v1_table(
            root=root,
            sr=sr,
            max_files=max_files,
            normal_class_ids=normal_class_ids,
            uncertain_class_ids=uncertain_class_ids,
        )
        if not meta_rows:
            raise SystemExit("No convertible files found under GPLA-12 data directory (including v1 tabular fallback).")

    with META.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(
            f,
            fieldnames=[
                "out_wav",
                "label",
                "source_path",
                "source_ext",
                "source_class_id",
                "normal_class_ids",
                "uncertain_class_ids",
                "label_source",
                "label_confidence",
                "review_note",
            ],
        )
        wr.writeheader()
        wr.writerows(meta_rows)

    counts = Counter(str(r.get("label", "")) for r in meta_rows)
    conf_counts = Counter(str(r.get("label_confidence", "")) for r in meta_rows)
    print(
        f"Produced {len(meta_rows)} wav files in {OUT} "
        f"(leak={counts.get('leak', 0)}, normal={counts.get('normal', 0)}, investigate={counts.get('investigate', 0)})"
    )
    print(
        "Class mapping assumption: "
        f"normal_class_ids={sorted(normal_class_ids)} uncertain_class_ids={sorted(uncertain_class_ids)}"
    )
    print(f"Label confidence: {dict(conf_counts)}")
    print(f"Wrote metadata: {META}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-files", type=int, default=40)
    ap.add_argument("--sr", type=int, default=16000)
    ap.add_argument("--clean", action="store_true", help="Delete existing data/audio/gpla12_wav first.")
    ap.add_argument(
        "--normal-class-ids",
        default=DEFAULT_NORMAL_CLASS_IDS,
        help=(
            "Comma-separated class IDs treated as 'normal' for data_v1 tabular fallback. "
            f"Default: {DEFAULT_NORMAL_CLASS_IDS}"
        ),
    )
    ap.add_argument(
        "--uncertain-class-ids",
        default=DEFAULT_UNCERTAIN_CLASS_IDS,
        help=(
            "Comma-separated class IDs treated as uncertain for data_v1 fallback. "
            f"Uncertain samples are routed to 'investigate'. Default: {DEFAULT_UNCERTAIN_CLASS_IDS}"
        ),
    )
    args = ap.parse_args()
    normal_ids = {int(x.strip()) for x in str(args.normal_class_ids).split(",") if str(x).strip()}
    uncertain_ids = {int(x.strip()) for x in str(args.uncertain_class_ids).split(",") if str(x).strip()}
    overlap = sorted(normal_ids.intersection(uncertain_ids))
    if overlap:
        raise SystemExit(f"Invalid class mapping: overlap in normal and uncertain ids: {overlap}")
    main(
        max_files=args.max_files,
        sr=args.sr,
        clean=bool(args.clean),
        normal_class_ids=normal_ids,
        uncertain_class_ids=uncertain_ids,
    )

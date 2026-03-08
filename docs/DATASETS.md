# Datasets

## GPLA-12 (Acoustic Leakage Dataset)
We optionally use a **small subset** of the GPLA-12 public dataset as a limited real sample for audio evidence.

Repository (source):
- `Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12`

How we use it:
- Download at build/run time via `scripts/download_gpla12.py` (we do not commit dataset files into this repo).
- Convert supported formats to WAV and label files as `gpla12_leak_*.wav`, `gpla12_normal_*.wav`, or `gpla12_investigate_*.wav`.
- Generate spectrograms with `python scripts/build_spectrograms.py --use-gpla12`.

Implementation note:
- Some upstream revisions expose `data_v3` without directly convertible files in the archive.
- Our downloader falls back to `data_v1` tabular files (`data.csv` + `label.csv`) and reconstructs per-sample WAV rows.
- For this fallback, class-id to binary label is inferred (`--normal-class-ids`).
- For this fallback, uncertain class IDs can be explicitly routed to investigate (`--uncertain-class-ids`).
- Current default assumption (must be reviewed before final claim):
  - Normal classes: `1,2,3,4`
  - Leak-like high-confidence classes: `5,6,7,8`
  - Uncertain classes (routed to investigate): `9,10,11,12`
- The active mapping is printed during download and stored in `data/audio/gpla12_wav/metadata.csv`.
- Metadata fields include:
  - `label_source`
  - `label_confidence` (`high_confidence` or `uncertain`)
  - `review_note`

Manifest selection policy (`scripts/create_manifest.py`):
- Leak-labeled `real_challenge` scenarios select only `high_confidence` leak samples when available.
- Uncertain samples are used only for investigate-style lanes (or ignored for leak confirmation).
- If suitable real samples are missing, manifest falls back to synthetic spectrograms and marks source in manifest columns.

Important:
- Review the dataset repository for license/terms and include attribution as required.
- If the dataset format is primarily `.mat` and SciPy is not available, conversion will skip those files.

## Hybrid Benchmark Tracks
- `core`: deterministic synthetic scenarios for stable regression checks.
- `real_challenge`: scenarios that prefer GPLA-12 spectrogram evidence (`track=real_challenge`, `prefer_real_audio=true`).

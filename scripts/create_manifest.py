from __future__ import annotations

from pathlib import Path
import csv
import json
import random

import pandas as pd

DATA = Path("data")
SCENARIOS = DATA / "scenarios" / "scenario_pack.json"

GPLA_SPEC_DIR = DATA / "spectrogram" / "gpla12"
GPLA_META = DATA / "audio" / "gpla12_wav" / "metadata.csv"


def _pick(lst: list[Path]) -> str:
    return str(random.choice(lst).as_posix())


def _pick_pool(*, key: str, candidates: list[Path], pools: dict[str, list[Path]]) -> str:
    if not candidates:
        raise ValueError(f"empty candidate pool for {key}")
    if key not in pools or not pools[key]:
        pools[key] = list(candidates)
        random.shuffle(pools[key])
    return str(pools[key].pop().as_posix())


def _load_gpla_metadata() -> dict[str, dict[str, str]]:
    if not GPLA_META.exists():
        return {}
    try:
        df = pd.read_csv(GPLA_META)
    except Exception:
        return {}
    by_stem: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        wav = str(row.get("out_wav", "") or "").strip()
        if not wav:
            continue
        stem = Path(wav).stem
        by_stem[stem] = {
            "label": str(row.get("label", "") or "").strip().lower(),
            "label_confidence": str(row.get("label_confidence", "") or "").strip().lower(),
            "label_source": str(row.get("label_source", "") or "").strip().lower(),
            "review_note": str(row.get("review_note", "") or "").strip(),
        }
    return by_stem


def _gpla_groups(gpla_spec: list[Path], meta_by_stem: dict[str, dict[str, str]]) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {
        "leak_high": [],
        "normal_high": [],
        "investigate_any": [],
        "uncertain_any": [],
        "all": list(gpla_spec),
    }
    for p in gpla_spec:
        m = meta_by_stem.get(p.stem, {})
        label = str(m.get("label", "") or "").strip().lower()
        conf = str(m.get("label_confidence", "") or "").strip().lower()
        if label == "leak" and conf == "high_confidence":
            out["leak_high"].append(p)
        if label == "normal" and conf == "high_confidence":
            out["normal_high"].append(p)
        if label == "investigate":
            out["investigate_any"].append(p)
        if conf == "uncertain":
            out["uncertain_any"].append(p)
    return out


def main() -> None:
    random.seed(42)
    pack = json.loads(SCENARIOS.read_text(encoding="utf-8"))

    thermal_normal = sorted((DATA / "thermal" / "zone-1").glob("normal_*.png"))
    thermal_leak = sorted((DATA / "thermal" / "zone-1").glob("leak_*.png"))
    spec_normal = sorted((DATA / "spectrogram" / "zone-1").glob("normal_*.png"))
    spec_leak = sorted((DATA / "spectrogram" / "zone-1").glob("leak_*.png"))
    # Optional real spectrograms (GPLA-12); naming from download script: gpla12_leak_*.wav -> gpla12_leak_*.png
    gpla_spec = sorted(GPLA_SPEC_DIR.glob("gpla12_*.png")) if GPLA_SPEC_DIR.exists() else []
    gpla_meta_by_stem = _load_gpla_metadata()
    gpla = _gpla_groups(gpla_spec, gpla_meta_by_stem)

    if not thermal_normal or not thermal_leak or not spec_normal or not spec_leak:
        raise SystemExit("Missing demo assets. Run scripts/generate_flows.py, scripts/generate_thermal_images.py, scripts/build_spectrograms.py")

    rows = []
    pools: dict[str, list[Path]] = {}
    flow = str((DATA / "flows" / "zone-1_base.csv").as_posix())
    for s in pack["scenarios"]:
        label = s["label"]
        track = str(s.get("track", "core") or "core").strip().lower()
        prefer_real_audio = bool(s.get("prefer_real_audio", False) or track == "real_challenge")
        audio_label_confidence = "synthetic"
        audio_label_source = "synthetic_demo"
        audio_review_note = ""
        if label == "normal":
            tfile, sp = _pick(thermal_normal), _pick(spec_normal)
        elif label == "planned_ops":
            # For the demo, planned ops should not show strong leak signatures.
            # (We keep ambiguity for later Bedrock/multimodal reasoning improvements.)
            tfile, sp = _pick(thermal_normal), _pick(spec_normal)
        else:
            tfile = _pick(thermal_leak) if s.get("thermal_expected") else _pick(thermal_normal)
            if prefer_real_audio and gpla.get("all"):
                if s.get("audio_expected"):
                    # Leak-labeled scenarios must use only high-confidence leak samples.
                    if gpla.get("leak_high"):
                        sp = _pick_pool(key="gpla_leak_high", candidates=gpla["leak_high"], pools=pools)
                    else:
                        sp = _pick(spec_leak)
                        audio_label_confidence = "synthetic_fallback"
                        audio_label_source = "gpla_missing_high_confidence_leak"
                else:
                    # Investigate/normal lanes prefer uncertain or investigate-tagged samples when available.
                    if label == "investigate":
                        if gpla.get("investigate_any"):
                            sp = _pick_pool(key="gpla_investigate_any", candidates=gpla["investigate_any"], pools=pools)
                        elif gpla.get("uncertain_any"):
                            sp = _pick_pool(key="gpla_uncertain_any", candidates=gpla["uncertain_any"], pools=pools)
                        elif gpla.get("normal_high"):
                            sp = _pick_pool(key="gpla_normal_high_for_investigate", candidates=gpla["normal_high"], pools=pools)
                        else:
                            sp = _pick(spec_normal)
                            audio_label_confidence = "synthetic_fallback"
                            audio_label_source = "gpla_missing_investigate_or_uncertain"
                    else:
                        if gpla.get("normal_high"):
                            sp = _pick_pool(key="gpla_normal_high", candidates=gpla["normal_high"], pools=pools)
                        elif gpla.get("uncertain_any"):
                            sp = _pick_pool(key="gpla_uncertain_any_for_normal", candidates=gpla["uncertain_any"], pools=pools)
                        else:
                            sp = _pick(spec_normal)
                            audio_label_confidence = "synthetic_fallback"
                            audio_label_source = "gpla_missing_high_confidence_normal"
            else:
                sp = _pick(spec_leak) if s.get("audio_expected") else _pick(spec_normal)

        m = gpla_meta_by_stem.get(Path(sp).stem, {})
        if m:
            audio_label_confidence = str(m.get("label_confidence", "") or audio_label_confidence)
            audio_label_source = str(m.get("label_source", "") or audio_label_source)
            audio_review_note = str(m.get("review_note", "") or "")

        rows.append(
            {
                "timestamp": s["incident_timestamp"],
                "zone": s["zone"],
                "scenario_id": s["scenario_id"],
                "flow_file": flow,
                "thermal_file": tfile,
                "spectrogram_file": sp,
                "planned_op_id": s.get("planned_op_id", ""),
                "label": label,
                "track": track,
                "audio_label_confidence": audio_label_confidence,
                "audio_label_source": audio_label_source,
                "audio_review_note": audio_review_note,
            }
        )

    out = DATA / "manifest" / "manifest.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

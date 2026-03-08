from __future__ import annotations
from pathlib import Path
import csv, json, random

DATA = Path("data")
pack = json.loads((DATA/"scenarios"/"scenario_pack.json").read_text(encoding="utf-8"))

thermal_normal = sorted((DATA/"thermal"/"zone-1").glob("normal_*.png"))
thermal_leak = sorted((DATA/"thermal"/"zone-1").glob("leak_*.png"))
audio_normal = sorted((DATA/"audio"/"zone-1").glob("normal_*.wav"))
audio_leak = sorted((DATA/"audio"/"zone-1").glob("leak_*.wav"))
spec_normal = sorted((DATA/"spectrogram"/"zone-1").glob("normal_*.png"))
spec_leak = sorted((DATA/"spectrogram"/"zone-1").glob("leak_*.png"))

def pick(lst): return str(random.choice(lst).as_posix())

def main():
    rows=[]
    flow = str((DATA/"flows"/"zone-1_base.csv").as_posix())
    for s in pack["scenarios"]:
        label=s["label"]
        if label=="normal":
            tfile,afile,sp=pick(thermal_normal),pick(audio_normal),pick(spec_normal)
        elif label=="planned_ops":
            tfile,afile,sp=pick(thermal_normal+thermal_leak),pick(audio_normal+audio_leak),pick(spec_normal+spec_leak)
        else:
            tfile = pick(thermal_leak) if s["thermal_expected"] else pick(thermal_normal)
            if s["audio_expected"]:
                afile,sp=pick(audio_leak),pick(spec_leak)
            else:
                afile,sp=pick(audio_normal),pick(spec_normal)
        rows.append({
            "timestamp": s["incident_timestamp"],
            "zone": s["zone"],
            "scenario_id": s["scenario_id"],
            "flow_file": flow,
            "thermal_file": tfile,
            "audio_file": afile,
            "spectrogram_file": sp,
            "planned_op_id": s.get("planned_op_id",""),
            "label": label
        })
    out = DATA/"manifest"/"manifest.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        wr=csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader(); wr.writerows(rows)
    print("Wrote", out)

if __name__=="__main__":
    main()

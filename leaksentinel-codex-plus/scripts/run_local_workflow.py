from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from app.bedrock_client import BedrockClient

DATA = Path("data")

def overlap(a_start,a_end,b_start,b_end):
    return a_start <= b_end and a_end >= b_start

def main(scenario_id: str):
    pack = json.loads((DATA/"scenarios"/"scenario_pack.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(DATA/"manifest"/"manifest.csv")
    scenario = next(x for x in pack["scenarios"] if x["scenario_id"]==scenario_id)
    row = manifest[manifest["scenario_id"]==scenario_id].iloc[0].to_dict()

    zone=row["zone"]; ts=row["timestamp"]
    flow = pd.read_csv(row["flow_file"])
    flow["timestamp"]=pd.to_datetime(flow["timestamp"])
    t=pd.to_datetime(ts)
    window = flow[(flow["timestamp"]<=t) & (flow["timestamp"]>=t-pd.Timedelta(minutes=scenario["window_minutes"]))]
    ctx={"zone":zone,"timestamp":ts,"flow_summary":{
        "observed": float(window["flow"].iloc[-1]),
        "expected": float(window["expected"].iloc[-1]),
        "anomaly_score": float(window["anomaly_score"].iloc[-1]),
    }, "thermal_file":row["thermal_file"], "spectrogram_file":row["spectrogram_file"]}

    client = BedrockClient(live=False)
    thermal = client.thermal_check(prompt="THERMAL", image_path=ctx["thermal_file"]).json
    audio = {"skipped": True}
    if thermal.get("confidence",0.0) < scenario["thermal_conf_threshold"]:
        audio = client.audio_check(prompt="AUDIO", image_path=ctx["spectrogram_file"]).json

    ops = json.loads((DATA/"ops_db.json").read_text(encoding="utf-8"))["ops"]
    sdt, edt = (t-pd.Timedelta(minutes=60)), (t+pd.Timedelta(minutes=60))
    planned=[r["planned_op_id"] for r in ops if r["zone"]==zone and overlap(pd.to_datetime(r["start"]),pd.to_datetime(r["end"]),sdt,edt)]
    ops_out={"planned_op_found": bool(planned), "planned_op_ids": planned, "summary":"Planned ops found." if planned else "No planned ops."}

    evidence={"context":ctx,"thermal":thermal,"audio":audio,"ops":ops_out}
    decision = client.decision(prompt="DECISION", evidence_json=evidence).json

    out = DATA/"evidence_bundles"
    out.mkdir(parents=True, exist_ok=True)
    p = out/f"{scenario_id}_{zone}_{ts.replace(':','-')}.json"
    p.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print("Wrote", p)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--scenario_id", required=True)
    args=ap.parse_args()
    main(args.scenario_id)

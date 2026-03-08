from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

DATA = Path("data")
OPS_DB = DATA/"ops_db.json"
MANIFEST = DATA/"manifest"/"manifest.csv"
BUNDLES = DATA/"evidence_bundles"

st.set_page_config(page_title="LeakSentinel", layout="wide")
st.title("LeakSentinel — Dashboard")

page = st.sidebar.radio("Page", ["Incidents", "Ops Portal"])

def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)

if page == "Ops Portal":
    st.header("Ops Portal (Demo)")
    ops = json.loads(OPS_DB.read_text(encoding="utf-8")).get("ops", []) if OPS_DB.exists() else []
    if not ops:
        st.warning("No ops records found.")
        st.stop()

    df = pd.DataFrame(ops)
    zones = ["(all)"] + sorted(df["zone"].unique().tolist())
    types = ["(all)"] + sorted(df["type"].unique().tolist())

    z = st.selectbox("Zone", zones)
    t = st.selectbox("Type", types)
    c1,c2 = st.columns(2)
    with c1: start = st.text_input("Start (ISO)", "2026-02-05T00:00:00")
    with c2: end = st.text_input("End (ISO)", "2026-02-06T06:00:00")
    q = st.text_input("Search (id/note contains)", "")

    f = df.copy()
    if z != "(all)":
        f = f[f["zone"] == z]
    if t != "(all)":
        f = f[f["type"] == t]

    try:
        sdt, edt = parse_dt(start), parse_dt(end)
        f["start_dt"] = f["start"].map(parse_dt)
        f["end_dt"] = f["end"].map(parse_dt)
        f = f[(f["start_dt"] <= edt) & (f["end_dt"] >= sdt)]
    except Exception:
        st.warning("Time filter parse failed; showing without time filter.")

    if q.strip():
        qq = q.strip().lower()
        f = f[f["planned_op_id"].str.lower().str.contains(qq) | f["note"].str.lower().str.contains(qq)]

    st.dataframe(f[["planned_op_id","zone","start","end","type","note"]], use_container_width=True)
    st.info("Nova Act can use this portal to validate planned operations (filter + open record).")
    st.stop()

# Incidents page
st.header("Incidents")
if not MANIFEST.exists():
    st.warning("Manifest not found. Run scripts/create_manifest.py")
    st.stop()

manifest = pd.read_csv(MANIFEST)
st.dataframe(manifest[["scenario_id","timestamp","zone","label","planned_op_id"]], use_container_width=True)

st.subheader("Evidence Bundles")
BUNDLES.mkdir(parents=True, exist_ok=True)
files = sorted(BUNDLES.glob("*.json"))
if not files:
    st.info("No bundles yet. Run: python scripts/run_local_workflow.py --scenario_id S02")
    st.stop()

sel = st.selectbox("Select bundle", [p.name for p in files])
bundle = json.loads((BUNDLES/sel).read_text(encoding="utf-8"))
st.metric("Decision", bundle.get("decision","?"))
st.metric("Confidence", f"{bundle.get('confidence',0):.2f}")
st.write("Rationale")
for r in bundle.get("rationale", []):
    st.write("- " + r)
st.divider()
st.json(bundle)

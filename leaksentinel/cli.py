from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from leaksentinel.config import AppSettings
from leaksentinel.orchestrator import run_scenario
from leaksentinel.doctor import run_doctor
from leaksentinel.eval.benchmark import run_benchmark, validate_dataset
from leaksentinel.feedback.store import VALID_OUTCOMES, create_feedback_record, list_feedback_records
from leaksentinel.ops.coverage_optimizer import build_coverage_plan
from leaksentinel.ops.closed_loop import simulate_closed_loop
from leaksentinel.ops.incidents_store import (
    INCIDENT_STATUSES,
    close_incident,
    dispatch_incident,
    field_update_incident,
    list_incidents,
    open_incident,
)
from leaksentinel.ops.risk_map import build_zone_risk_map
from leaksentinel.compliance.standards_mode import evaluate_standards_readiness, load_json_or_default
from leaksentinel.impact.proof import build_impact_compare
from leaksentinel.impact.kpis import compute_impact_kpis
from leaksentinel.integrations.bridge import export_data, ingest_event, list_connectors
from leaksentinel.feedback.store import resolve_latest_bundle_for_scenario


def _cmd_run(args: argparse.Namespace) -> int:
    out = run_scenario(
        scenario_id=args.scenario_id,
        mode=args.mode,
        write_bundle=not args.no_write,
        ablation=args.ablation,
        analysis_version=args.analysis_version,
        include_counterfactuals=not bool(args.no_counterfactuals),
        include_impact=not bool(args.no_impact),
        include_flow_agent=not bool(args.no_flow_agent),
        include_pressure_plan=not bool(args.no_pressure_plan),
        include_scorecard=not bool(args.no_scorecard),
        include_standards=not bool(args.no_standards),
        judge_mode=bool(args.judge_mode),
    )
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"decision={out.get('decision')} confidence={out.get('confidence')}")
        for r in out.get("rationale", [])[:5]:
            print(f"- {r}")
        bundle_path = out.get("_bundle_path")
        if bundle_path:
            print(f"bundle={bundle_path}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    rep = run_doctor()
    print(json.dumps(rep, indent=2))
    return 0


def _cmd_act_ops_check(args: argparse.Namespace) -> int:
    from leaksentinel.act.ops_check import run_ops_check_act

    try:
        out = run_ops_check_act(
            zone=args.zone,
            start=args.start,
            end=args.end,
            op_type=args.op_type if args.op_type not in ("", None) else None,
        )
        print(json.dumps(out, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 2


def _cmd_feedback_add(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = create_feedback_record(
        bundle_path=args.bundle_path if args.bundle_path else None,
        scenario_id=args.scenario_id if args.scenario_id else None,
        outcome=args.outcome,
        operator_note=args.note,
        reviewer=args.reviewer,
        root_cause_guess=args.root_cause_guess,
        evidence_gap=args.evidence_gap,
        evidence_dir=settings.paths.evidence_dir,
        feedback_dir=settings.paths.feedback_dir,
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_feedback_list(args: argparse.Namespace) -> int:
    settings = AppSettings()
    rows = list_feedback_records(
        feedback_dir=settings.paths.feedback_dir,
        zone=args.zone if args.zone else None,
        outcome=args.outcome if args.outcome else None,
        limit=int(args.limit),
    )
    print(json.dumps({"count": len(rows), "items": rows}, indent=2))
    return 0


def _cmd_ops_coverage_plan(args: argparse.Namespace) -> int:
    settings = AppSettings()
    evidence_dir = Path(args.evidence_dir) if str(args.evidence_dir).strip() else settings.paths.evidence_dir
    zones = [z.strip() for z in str(args.zones).split(",") if z.strip()] if str(args.zones).strip() else []
    out = build_coverage_plan(
        evidence_dir=evidence_dir,
        horizon_hours=int(args.horizon_hours),
        max_crews=int(args.max_crews),
        zones=zones,
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_standards_check(args: argparse.Namespace) -> int:
    settings = AppSettings()
    profile = load_json_or_default(
        Path(args.profile) if str(args.profile).strip() else settings.standards.default_profile_path,
        default_obj={},
    )
    catalog = load_json_or_default(
        Path(args.catalog) if str(args.catalog).strip() else settings.standards.controls_catalog_path,
        default_obj={"required_controls": []},
    )
    out = evaluate_standards_readiness(building_profile=profile, controls_catalog=catalog)
    print(json.dumps(out, indent=2))
    return 0


def _cmd_impact_compare(args: argparse.Namespace) -> int:
    settings = AppSettings(mode=args.mode)
    assumptions_register = load_json_or_default(
        settings.impact.assumptions_path,
        default_obj={},
    )
    bundles: list[dict] = []
    if str(args.scenario_ids).strip():
        for sid in [s.strip() for s in str(args.scenario_ids).split(",") if s.strip()]:
            out = run_scenario(
                scenario_id=sid,
                mode=args.mode,
                write_bundle=False,
                analysis_version="v2",
                ablation="full",
            )
            if isinstance(out, dict):
                bundles.append(out)
    if str(args.bundle_paths).strip():
        for p in [s.strip() for s in str(args.bundle_paths).split(",") if s.strip()]:
            obj = json.loads(Path(p).read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                bundles.append(obj)
    if not bundles:
        raise ValueError("Provide --scenario-ids or --bundle-paths.")
    out = build_impact_compare(
        bundles=bundles,
        assumptions_register=assumptions_register,
        persona=str(args.persona),
        personas_path=settings.impact.personas_path,
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_ops_closed_loop_simulate(args: argparse.Namespace) -> int:
    out = simulate_closed_loop(
        scenario_id=args.scenario_id,
        mode=args.mode,
        field_verdict=args.field_verdict,
        max_crews=int(args.max_crews),
        horizon_hours=int(args.horizon_hours),
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_ops_incident_open(args: argparse.Namespace) -> int:
    settings = AppSettings(mode=args.mode)
    bundle: dict | None = None
    bundle_path = str(args.bundle_path or "").strip()
    if bundle_path:
        obj = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            bundle = obj
    elif str(args.scenario_id or "").strip():
        sid = str(args.scenario_id).strip()
        try:
            bp = resolve_latest_bundle_for_scenario(evidence_dir=settings.paths.evidence_dir, scenario_id=sid)
            bundle_path = str(bp)
            obj = json.loads(bp.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                bundle = obj
        except FileNotFoundError:
            out = run_scenario(
                scenario_id=sid,
                mode=args.mode,
                write_bundle=True,
                analysis_version="v2",
                ablation="full",
            )
            if isinstance(out, dict):
                bundle = out
                bundle_path = str(out.get("_bundle_path", "") or "")
    else:
        raise ValueError("Provide --bundle-path or --scenario-id.")
    if not isinstance(bundle, dict):
        raise ValueError("Failed to load bundle for incident open.")
    out = open_incident(
        incidents_path=settings.paths.incidents_path,
        bundle=bundle,
        bundle_path=bundle_path,
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_ops_incident_list(args: argparse.Namespace) -> int:
    settings = AppSettings()
    rows = list_incidents(
        incidents_path=settings.paths.incidents_path,
        status=args.status,
        zone=args.zone,
        limit=int(args.limit),
    )
    print(json.dumps({"count": len(rows), "items": rows}, indent=2))
    return 0


def _cmd_ops_incident_dispatch(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = dispatch_incident(
        incidents_path=settings.paths.incidents_path,
        incident_id=args.incident_id,
        team=args.team,
        eta_minutes=int(args.eta_minutes),
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_ops_incident_update(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = field_update_incident(
        incidents_path=settings.paths.incidents_path,
        incident_id=args.incident_id,
        status=args.status,
        note=args.note,
        evidence_added=bool(args.evidence_added),
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_ops_incident_close(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = close_incident(
        incidents_path=settings.paths.incidents_path,
        incident_id=args.incident_id,
        closure_type=args.closure_type,
        note=args.note,
        repair_cost_usd=float(args.repair_cost_usd),
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_ops_risk_map(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = build_zone_risk_map(
        evidence_dir=settings.paths.evidence_dir,
        incidents_path=settings.paths.incidents_path,
        window_days=int(args.window_days),
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_impact_kpis(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = compute_impact_kpis(
        incidents_path=settings.paths.incidents_path,
        from_ts=args.from_ts,
        to_ts=args.to_ts,
        zone=args.zone,
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_integrations_list(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = list_connectors(connectors_path=settings.paths.connectors_path)
    print(json.dumps({"count": len(out), "items": out}, indent=2))
    return 0


def _cmd_integrations_ingest(args: argparse.Namespace) -> int:
    settings = AppSettings()
    payload = {}
    if str(args.payload_json).strip():
        obj = json.loads(str(args.payload_json))
        if isinstance(obj, dict):
            payload = obj
    out = ingest_event(
        events_path=settings.paths.integration_events_path,
        source=args.source,
        event_type=args.event_type,
        zone=args.zone,
        timestamp=args.timestamp,
        payload=payload,
    )
    print(json.dumps(out, indent=2))
    return 0


def _cmd_integrations_export(args: argparse.Namespace) -> int:
    settings = AppSettings()
    out = export_data(
        export_format=args.format,
        entity=args.entity,
        from_ts=args.from_ts,
        to_ts=args.to_ts,
        zone=args.zone,
        incidents_path=settings.paths.incidents_path,
        exports_dir=settings.paths.exports_dir,
    )
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    # Allow local runs to configure Bedrock/Nova via a gitignored .env file.
    load_dotenv()

    ap = argparse.ArgumentParser(prog="leaksentinel")
    sub = ap.add_subparsers(dest="cmd", required=True)

    runp = sub.add_parser("run", help="Run a scenario and produce an evidence bundle.")
    runp.add_argument("--scenario-id", required=True)
    runp.add_argument("--mode", choices=["local", "bedrock"], default="local")
    runp.add_argument(
        "--ablation",
        choices=["full", "flow-only", "flow+thermal", "flow+thermal+audio"],
        default="full",
        help="Benchmark/debug option: disable parts of the pipeline to measure impact.",
    )
    runp.add_argument(
        "--analysis-version",
        choices=["v1", "v2"],
        default="v2",
        help="Output schema version for augmented analysis fields.",
    )
    runp.add_argument(
        "--no-counterfactuals",
        action="store_true",
        help="Skip counterfactual outputs.",
    )
    runp.add_argument(
        "--no-impact",
        action="store_true",
        help="Skip impact estimate outputs.",
    )
    runp.add_argument(
        "--no-flow-agent",
        action="store_true",
        help="Skip continuous-flow alert output.",
    )
    runp.add_argument(
        "--no-pressure-plan",
        action="store_true",
        help="Skip pressure autopilot output.",
    )
    runp.add_argument(
        "--no-scorecard",
        action="store_true",
        help="Skip NRW/carbon scorecard output.",
    )
    runp.add_argument(
        "--no-standards",
        action="store_true",
        help="Skip standards readiness output.",
    )
    runp.add_argument(
        "--judge-mode",
        action="store_true",
        help="Enable judge compliance checks in output.",
    )
    runp.add_argument("--no-write", action="store_true", help="Do not write evidence bundle to disk.")
    runp.add_argument("--json", action="store_true", help="Print full JSON output.")
    runp.set_defaults(func=_cmd_run)

    docp = sub.add_parser("doctor", help="Bedrock/Nova preflight diagnostics (no AWS CLI required).")
    docp.set_defaults(func=_cmd_doctor)

    actp = sub.add_parser("act", help="Nova Act demos (optional).")
    actsub = actp.add_subparsers(dest="act_cmd", required=True)

    op = actsub.add_parser("ops-check", help="Use Nova Act tool-calling to validate planned ops for a time window.")
    op.add_argument("--zone", required=True)
    op.add_argument("--start", required=True, help="ISO timestamp, e.g. 2026-02-05T02:00:00")
    op.add_argument("--end", required=True, help="ISO timestamp, e.g. 2026-02-05T04:00:00")
    op.add_argument("--op-type", default="", help="Optional op type filter (e.g., tank_fill).")
    op.set_defaults(func=_cmd_act_ops_check)

    fbp = sub.add_parser("feedback", help="Operator feedback (learning from mistakes).")
    fbsub = fbp.add_subparsers(dest="feedback_cmd", required=True)

    fba = fbsub.add_parser("add", help="Add operator feedback for an existing evidence bundle.")
    fba.add_argument("--bundle-path", default="", help="Path to evidence bundle JSON.")
    fba.add_argument("--scenario-id", default="", help="If set, uses latest bundle for this scenario id.")
    fba.add_argument("--outcome", default=VALID_OUTCOMES[0], choices=list(VALID_OUTCOMES))
    fba.add_argument("--note", default="", help="Optional operator note.")
    fba.add_argument("--reviewer", default="", help="Optional reviewer/operator id.")
    fba.add_argument("--root-cause-guess", default="", help="Optional root-cause tag for false positive.")
    fba.add_argument("--evidence-gap", default="", help="Optional missing-evidence tag.")
    fba.set_defaults(func=_cmd_feedback_add)

    fbl = fbsub.add_parser("list", help="List stored feedback records.")
    fbl.add_argument("--zone", default="")
    fbl.add_argument("--outcome", default="", choices=["", *list(VALID_OUTCOMES)])
    fbl.add_argument("--limit", type=int, default=100)
    fbl.set_defaults(func=_cmd_feedback_list)

    opsp = sub.add_parser("ops", help="Operational planning tools.")
    opssub = opsp.add_subparsers(dest="ops_cmd", required=True)
    opc = opssub.add_parser("coverage-plan", help="Prioritize bundles into a dispatch queue.")
    opc.add_argument("--horizon-hours", type=int, default=24)
    opc.add_argument("--max-crews", type=int, default=3)
    opc.add_argument("--zones", default="", help="Comma-separated zone filter, e.g. zone-1,zone-2")
    opc.add_argument("--evidence-dir", default="", help="Override evidence bundle directory.")
    opc.set_defaults(func=_cmd_ops_coverage_plan)
    ocs = opssub.add_parser("closed-loop-simulate", help="Run an end-to-end closed-loop simulation.")
    ocs.add_argument("--scenario-id", required=True)
    ocs.add_argument("--mode", choices=["local", "bedrock"], default="local")
    ocs.add_argument("--field-verdict", default="rejected_false_positive", choices=["rejected_false_positive", "confirmed"])
    ocs.add_argument("--max-crews", type=int, default=3)
    ocs.add_argument("--horizon-hours", type=int, default=24)
    ocs.set_defaults(func=_cmd_ops_closed_loop_simulate)
    oio = opssub.add_parser("incident-open", help="Open or reuse an operational incident from a bundle/scenario.")
    oio.add_argument("--scenario-id", default="", help="Scenario id; uses latest bundle or runs scenario if missing.")
    oio.add_argument("--bundle-path", default="", help="Path to bundle JSON.")
    oio.add_argument("--mode", choices=["local", "bedrock"], default="local")
    oio.set_defaults(func=_cmd_ops_incident_open)
    oil = opssub.add_parser("incident-list", help="List incidents with optional filters.")
    oil.add_argument("--status", default="", choices=["", *list(INCIDENT_STATUSES)])
    oil.add_argument("--zone", default="")
    oil.add_argument("--limit", type=int, default=100)
    oil.set_defaults(func=_cmd_ops_incident_list)
    oid = opssub.add_parser("incident-dispatch", help="Assign dispatch team to incident.")
    oid.add_argument("--incident-id", required=True)
    oid.add_argument("--team", required=True)
    oid.add_argument("--eta-minutes", type=int, default=30)
    oid.set_defaults(func=_cmd_ops_incident_dispatch)
    oiu = opssub.add_parser("incident-update", help="Update incident field status.")
    oiu.add_argument("--incident-id", required=True)
    oiu.add_argument("--status", required=True, choices=list(INCIDENT_STATUSES))
    oiu.add_argument("--note", default="")
    oiu.add_argument("--evidence-added", action="store_true")
    oiu.set_defaults(func=_cmd_ops_incident_update)
    oic = opssub.add_parser("incident-close", help="Close incident with true/false positive verdict.")
    oic.add_argument("--incident-id", required=True)
    oic.add_argument("--closure-type", required=True, choices=["true_positive", "false_positive"])
    oic.add_argument("--note", default="")
    oic.add_argument("--repair-cost-usd", type=float, default=0.0)
    oic.set_defaults(func=_cmd_ops_incident_close)
    orm = opssub.add_parser("risk-map", help="Build zone risk map from recent incidents + bundles.")
    orm.add_argument("--window-days", type=int, default=30)
    orm.set_defaults(func=_cmd_ops_risk_map)

    stdp = sub.add_parser("standards", help="Building standards readiness checks.")
    stdsub = stdp.add_subparsers(dest="standards_cmd", required=True)
    stdc = stdsub.add_parser("check", help="Evaluate standards readiness using profile+catalog.")
    stdc.add_argument("--profile", default="", help="Path to building profile JSON.")
    stdc.add_argument("--catalog", default="", help="Path to controls catalog JSON.")
    stdc.set_defaults(func=_cmd_standards_check)

    ipp = sub.add_parser("impact", help="Impact analysis tools.")
    ips = ipp.add_subparsers(dest="impact_cmd", required=True)
    ipc = ips.add_parser("compare", help="Compare baseline vs LeakSentinel impact across scenarios/bundles.")
    ipc.add_argument("--mode", choices=["local", "bedrock"], default="local")
    ipc.add_argument("--scenario-ids", default="", help="Comma-separated scenario ids.")
    ipc.add_argument("--bundle-paths", default="", help="Comma-separated evidence bundle JSON paths.")
    ipc.add_argument("--persona", choices=["utility", "industrial", "campus"], default="utility")
    ipc.set_defaults(func=_cmd_impact_compare)
    ipk = ips.add_parser("kpis", help="Aggregate incident impact KPIs.")
    ipk.add_argument("--from-ts", default="", help="ISO start timestamp filter.")
    ipk.add_argument("--to-ts", default="", help="ISO end timestamp filter.")
    ipk.add_argument("--zone", default="")
    ipk.set_defaults(func=_cmd_impact_kpis)

    intp = sub.add_parser("integrations", help="Lightweight integration bridge tools.")
    intsub = intp.add_subparsers(dest="integrations_cmd", required=True)
    intl = intsub.add_parser("list-connectors", help="List configured connectors.")
    intl.set_defaults(func=_cmd_integrations_list)
    inte = intsub.add_parser("ingest-event", help="Ingest an external event into normalized event log.")
    inte.add_argument("--source", required=True)
    inte.add_argument("--event-type", required=True)
    inte.add_argument("--zone", default="")
    inte.add_argument("--timestamp", default="")
    inte.add_argument("--payload-json", default="{}", help='JSON object string, e.g. "{\"pressure\":42}"')
    inte.set_defaults(func=_cmd_integrations_ingest)
    intx = intsub.add_parser("export", help="Export incidents or KPI summaries.")
    intx.add_argument("--format", default="json", choices=["json", "csv"])
    intx.add_argument("--entity", default="incidents", choices=["incidents", "kpis"])
    intx.add_argument("--from-ts", default="")
    intx.add_argument("--to-ts", default="")
    intx.add_argument("--zone", default="")
    intx.set_defaults(func=_cmd_integrations_export)

    benchp = sub.add_parser("benchmark", help="Run scenario pack benchmark and write a report (md+csv).")
    benchp.add_argument("--mode", choices=["local", "bedrock"], default="local")
    benchp.add_argument(
        "--ablation",
        choices=["all", "flow-only", "flow+thermal", "flow+thermal+audio", "full"],
        default="all",
    )
    benchp.add_argument("--out-dir", default="data/_reports", help="Output directory for reports.")
    benchp.add_argument(
        "--strict",
        action="store_true",
        help="Fail the benchmark if dataset validation warnings are found.",
    )
    benchp.add_argument(
        "--scenario-pack",
        default="data/scenarios/scenario_pack.json",
        help="Scenario pack JSON path (default: data/scenarios/scenario_pack.json).",
    )
    benchp.add_argument(
        "--manifest",
        default="data/manifest/manifest.csv",
        help="Manifest CSV path for the selected scenario pack.",
    )
    benchp.add_argument(
        "--ops-db",
        default="data/ops_db.json",
        help="Planned ops DB JSON path for dataset validation.",
    )

    def _cmd_benchmark(args: argparse.Namespace) -> int:
        if args.ablation == "all":
            ablations = ["flow-only", "flow+thermal", "flow+thermal+audio", "full"]
        else:
            ablations = [args.ablation]
        res = run_benchmark(
            mode=args.mode,
            scenario_pack_path=Path(args.scenario_pack),
            ablations=ablations,
            out_dir=Path(args.out_dir),
            manifest_path=Path(args.manifest),
            ops_db_path=Path(args.ops_db),
            strict=bool(args.strict),
        )
        print(json.dumps(res.meta, indent=2))
        return 0

    benchp.set_defaults(func=_cmd_benchmark)

    vdp = sub.add_parser("validate-dataset", help="Validate scenario pack, manifest and ops consistency.")
    vdp.add_argument("--scenario-pack", default="data/scenarios/scenario_pack.json")
    vdp.add_argument("--manifest", default="data/manifest/manifest.csv")
    vdp.add_argument("--ops-db", default="data/ops_db.json")
    vdp.add_argument("--strict", action="store_true", help="Exit non-zero when warnings are found.")

    def _cmd_validate_dataset(args: argparse.Namespace) -> int:
        warnings = validate_dataset(
            scenario_pack_path=Path(args.scenario_pack),
            ops_db_path=Path(args.ops_db),
            manifest_path=Path(args.manifest),
        )
        blocking = [w for w in warnings if not str(w).startswith("dataset_diversity_warning:")]
        out = {
            "ok": len(blocking) == 0,
            "warnings_n": len(warnings),
            "blocking_warnings_n": len(blocking),
            "warnings": warnings,
        }
        print(json.dumps(out, indent=2))
        if args.strict and blocking:
            return 2
        return 0

    vdp.set_defaults(func=_cmd_validate_dataset)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


def _utc_now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _as_bool(value: Any) -> bool:
    return bool(value)


def _non_empty_request_ids(req: dict[str, Any]) -> bool:
    for v in req.values():
        if isinstance(v, (str, int, float)):
            if str(v).strip():
                return True
        if isinstance(v, list) and v:
            return True
        if isinstance(v, dict) and v:
            return True
    return False


def _post_json(url: str, body: dict[str, Any], *, api_key: str | None, timeout_sec: int) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["X-API-Key"] = api_key.strip()
    req = request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST {url} failed with HTTP {e.code}: {detail}") from e
    except error.URLError as e:
        raise SystemExit(f"POST {url} failed: {e}") from e
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise SystemExit(f"POST {url} returned non-JSON payload.") from e
    if not isinstance(obj, dict):
        raise SystemExit("POST /run returned JSON but root is not an object.")
    return obj


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture one hosted judge-mode run and verify Bedrock trace evidence.")
    ap.add_argument("--api-base", default="http://127.0.0.1:8000", help="API base URL, e.g. http://alb-dns-name")
    ap.add_argument("--scenario-id", default="S05")
    ap.add_argument("--mode", default="bedrock", choices=["bedrock", "local"])
    ap.add_argument("--analysis-version", default="v2", choices=["v1", "v2"])
    ap.add_argument("--api-key", default=os.getenv("LEAKSENTINEL_API_KEY", ""))
    ap.add_argument("--timeout-sec", type=int, default=90)
    ap.add_argument("--out-dir", default="data/_reports/judge_runs")
    ap.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true, exits non-zero if judge/Bedrock trace checks fail.",
    )
    args = ap.parse_args()

    run_url = f"{str(args.api_base).rstrip('/')}/run"
    body = {
        "scenario_id": str(args.scenario_id),
        "mode": str(args.mode),
        "judge_mode": True,
        "analysis_version": str(args.analysis_version),
        "include_counterfactuals": True,
        "include_impact": True,
        "include_flow_agent": True,
        "include_pressure_plan": True,
        "include_scorecard": True,
        "include_standards": True,
    }

    out = _post_json(run_url, body, api_key=str(args.api_key or ""), timeout_sec=int(args.timeout_sec))
    jc = out.get("judge_compliance", {}) if isinstance(out.get("judge_compliance"), dict) else {}
    rt = out.get("_runtime", {}) if isinstance(out.get("_runtime"), dict) else {}
    br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
    req = br.get("request_ids", {}) if isinstance(br.get("request_ids"), dict) else {}

    judge_pass = _as_bool(jc.get("pass"))
    bedrock_used = _as_bool(br.get("used"))
    has_req_ids = _non_empty_request_ids(req)
    missing_fields = jc.get("missing_fields", []) if isinstance(jc.get("missing_fields"), list) else []
    failed_checks = jc.get("failed_checks", []) if isinstance(jc.get("failed_checks"), list) else []

    ts = _utc_now_tag()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_path = out_dir / f"judge_run_{ts}_{args.mode}_{args.scenario_id}.json"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"

    run_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [
        "# Hosted Judge Run Capture",
        "",
        f"- Timestamp (UTC): `{ts}`",
        f"- API base: `{args.api_base}`",
        f"- Scenario: `{args.scenario_id}`",
        f"- Mode: `{args.mode}`",
        f"- Saved JSON: `{run_path.as_posix()}`",
        "",
        "## Checks",
        f"- `judge_compliance.pass`: `{judge_pass}`",
        f"- `_runtime.bedrock.used`: `{bedrock_used}`",
        f"- `_runtime.bedrock.request_ids` non-empty: `{has_req_ids}`",
        f"- `missing_fields`: `{', '.join(str(x) for x in missing_fields) if missing_fields else '-'}`",
        f"- `failed_checks`: `{', '.join(str(x) for x in failed_checks) if failed_checks else '-'}`",
    ]

    latest_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    strict_fail = not (judge_pass and bedrock_used and has_req_ids)
    if bool(args.strict) and strict_fail:
        print("Strict mode failed: hosted judge evidence is incomplete.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

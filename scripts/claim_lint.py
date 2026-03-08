from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    claim_id: str
    ok: bool
    errors: list[str]


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _contains_all(text: str, snippets: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    norm = text.lower()
    for s in snippets:
        token = str(s).strip()
        if not token:
            continue
        if token.lower() not in norm:
            missing.append(token)
    return (len(missing) == 0), missing


def _run_claim_check(root: Path, claim: dict[str, Any]) -> CheckResult:
    claim_id = str(claim.get("id", "unknown")).strip() or "unknown"
    errors: list[str] = []

    source = claim.get("source", {}) if isinstance(claim.get("source"), dict) else {}
    source_path = root / str(source.get("path", ""))
    source_contains = [str(x) for x in (source.get("contains") or []) if str(x).strip()]
    if not source_path.exists():
        errors.append(f"source_missing:{source_path.as_posix()}")
    else:
        src_text = _load_text(source_path)
        ok_src, missing_src = _contains_all(src_text, source_contains)
        if not ok_src:
            errors.append(f"source_missing_snippets:{','.join(missing_src)}")

    evidence = claim.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) == 0:
        errors.append("evidence_missing:claim has no evidence entries")
    else:
        for idx, ev in enumerate(evidence):
            if not isinstance(ev, dict):
                errors.append(f"evidence_invalid:{idx}")
                continue
            ev_path = root / str(ev.get("path", ""))
            ev_contains = [str(x) for x in (ev.get("contains") or []) if str(x).strip()]
            if not ev_path.exists():
                errors.append(f"evidence_path_missing:{ev_path.as_posix()}")
                continue
            ev_text = _load_text(ev_path)
            ok_ev, missing_ev = _contains_all(ev_text, ev_contains)
            if not ok_ev:
                errors.append(
                    f"evidence_missing_snippets:{ev_path.as_posix()}:{','.join(missing_ev)}"
                )

    return CheckResult(claim_id=claim_id, ok=(len(errors) == 0), errors=errors)


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate that submission/demo claims are backed by local evidence.")
    ap.add_argument("--map", default="docs/claim_evidence_map.json")
    ap.add_argument("--out", default="data/_reports/claim_lint_latest.md")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    map_path = root / str(args.map)
    if not map_path.exists():
        raise SystemExit(f"Claim map not found: {map_path}")

    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"Failed to parse claim map: {e}") from e
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    if not isinstance(claims, list) or len(claims) == 0:
        raise SystemExit("Claim map has no claims.")

    results = [_run_claim_check(root, c if isinstance(c, dict) else {}) for c in claims]
    ok_n = sum(1 for r in results if r.ok)
    fail_n = len(results) - ok_n

    lines = [
        "# Claim Lint Report",
        "",
        f"- Map: `{map_path.relative_to(root).as_posix()}`",
        f"- Total claims: `{len(results)}`",
        f"- Passed: `{ok_n}`",
        f"- Failed: `{fail_n}`",
        "",
        "| Claim ID | Status | Details |",
        "|---|---|---|",
    ]
    for r in results:
        detail = "ok" if r.ok else "; ".join(r.errors)
        lines.append(f"| `{r.claim_id}` | `{'PASS' if r.ok else 'FAIL'}` | {detail} |")

    out_path = root / str(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    if fail_n > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(".").resolve()
REPORTS_DIR = Path("data") / "_llm_reports"


def _utc_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(cmd: List[str]) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True)
    out = (p.stdout or b"").decode("utf-8", errors="replace")
    err = (p.stderr or b"").decode("utf-8", errors="replace")
    return int(p.returncode), out, err


def _have(cmd: str) -> bool:
    code, _, _ = _run([cmd, "--version"])
    return code == 0


def _rg(pattern: str, path: str = ".", max_hits: int = 200) -> str:
    if not _have("rg"):
        return f"(rg not available) pattern={pattern}\n"
    code, out, err = _run(
        ["rg", "-n", "--hidden", "--follow", "--color", "never", "--max-count", str(max_hits), pattern, path]
    )
    if code not in (0, 1):
        return f"(rg error) pattern={pattern}\n{err.strip()}\n"
    return out.strip() + ("\n" if out.strip() else "")


def _head(path: Path, n: int = 80) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:n]).strip() + ("\n" if lines else "")


def _list_top() -> str:
    rows = []
    for p in sorted(REPO_ROOT.iterdir()):
        name = p.name
        if name in {".git", ".venv", "__pycache__"}:
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            mtime = "?"
        rows.append(f"- `{name}` ({'dir' if p.is_dir() else 'file'}, mtime={mtime})")
    return "\n".join(rows) + "\n"


def build_report() -> str:
    parts: List[str] = []
    parts.append("# Local Repo Scan Report")
    parts.append("")
    parts.append(f"- Timestamp (UTC): `{_utc_ts()}`")
    parts.append(f"- Repo root: `{REPO_ROOT}`")
    parts.append("")

    parts.append("## Top-Level Contents")
    parts.append(_list_top())

    parts.append("## Quick Context (README / plan)")
    parts.append("### `README.md` (head)")
    parts.append("```text")
    parts.append(_head(Path("README.md")))
    parts.append("```")
    parts.append("")
    parts.append("### `plan.md` (head)")
    parts.append("```text")
    parts.append(_head(Path("plan.md")))
    parts.append("```")
    parts.append("")

    parts.append("## Stubs / Placeholders / Fallbacks")
    parts.append("### bedrock fallback / not implemented")
    parts.append("```text")
    parts.append(_rg("bedrock mode not implemented|not fully implemented|local fallback|Placeholder", "."))
    parts.append("```")
    parts.append("")
    parts.append("### echo-only / skeleton")
    parts.append("```text")
    parts.append(_rg("echo-only|\\bskeleton\\b", "."))
    parts.append("```")
    parts.append("")

    parts.append("## TODO / WIP / FIXME")
    parts.append("```text")
    parts.append(_rg("TODO|WIP|FIXME", "."))
    parts.append("```")
    parts.append("")

    parts.append("## Amazon / Nova / Bedrock Mentions")
    parts.append("```text")
    parts.append(_rg("Bedrock|Nova|NOVA_|NovaAct|Sonic|embeddings", "."))
    parts.append("```")
    parts.append("")

    parts.append("## Tech Stack (requirements)")
    parts.append("### `requirements.txt`")
    parts.append("```text")
    parts.append(Path("requirements.txt").read_text(encoding="utf-8", errors="replace").strip() if Path("requirements.txt").exists() else "")
    parts.append("```")
    parts.append("")
    parts.append("### `requirements-hosted.txt`")
    parts.append("```text")
    parts.append(
        Path("requirements-hosted.txt").read_text(encoding="utf-8", errors="replace").strip()
        if Path("requirements-hosted.txt").exists()
        else ""
    )
    parts.append("```")
    parts.append("")

    parts.append("## Infra Cost Flags (NAT / public IP)")
    parts.append("```text")
    parts.append(_rg("NAT|AssignPublicIp|PublicSubnets|PrivateSubnets", "infra"))
    parts.append("```")
    parts.append("")

    parts.append("## Data Artifacts Present (committed vs generated)")
    parts.append("```text")
    code, out, err = _run(["powershell", "-NoProfile", "-Command", "Get-ChildItem -Recurse -Depth 3 -Force data | Select-Object FullName,Length | Format-Table -HideTableHeaders"])
    if code == 0:
        parts.append(out.strip())
    else:
        parts.append(err.strip())
    parts.append("```")
    parts.append("")

    return "\n".join(parts).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a local (no network) repo scan report.")
    ap.add_argument("--out", default="", help="Output path (default: data/_llm_reports/local_scan_<ts>.md)")
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc_ts().replace(":", "-")
    out_path = Path(args.out) if args.out else (REPORTS_DIR / f"local_scan_{ts}.md")

    report = build_report()
    out_path.write_text(report, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


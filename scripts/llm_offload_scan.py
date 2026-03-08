from __future__ import annotations

import argparse
import json
import os
import subprocess
import getpass
import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

from dotenv import load_dotenv


REPO_ROOT = Path(".").resolve()
REPORTS_DIR = Path("data") / "_llm_reports"


def _utc_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(cmd: List[str]) -> Tuple[int, str, str]:
    # Use bytes + explicit decode to avoid Windows console encoding failures when rg
    # outputs characters not representable in the active code page.
    try:
        p = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True)
    except FileNotFoundError as e:
        return 127, "", str(e)
    out = (p.stdout or b"").decode("utf-8", errors="replace")
    err = (p.stderr or b"").decode("utf-8", errors="replace")
    return int(p.returncode), out, err


def _have_rg() -> bool:
    code, _, _ = _run(["rg", "--version"])
    return code == 0


def _walk_files() -> List[Path]:
    out: List[Path] = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip common virtualenv/cache dirs early for speed.
        dn = {".git", ".venv", "__pycache__", ".pytest_cache"}
        dirs[:] = [d for d in dirs if d not in dn]
        for fn in files:
            p = Path(root) / fn
            try:
                out.append(p.resolve().relative_to(REPO_ROOT))
            except Exception:
                continue
    return out


def _repo_files(globs: List[str] | None = None) -> List[Path]:
    if _have_rg():
        cmd = ["rg", "--files", "--hidden", "--follow", "--color", "never"]
        if globs:
            for g in globs:
                cmd += ["-g", g]
        code, out, err = _run(cmd)
        if code != 0:
            raise RuntimeError(f"rg --files failed: {err.strip()}")
        return [Path(line.strip()) for line in out.splitlines() if line.strip()]
    # Fallback: Python walk (globs ignored here; we filter later).
    return _walk_files()


def _rg_search(pattern: str, paths: List[str] | None = None, max_hits: int = 200) -> List[Tuple[str, int, str]]:
    if _have_rg():
        cmd = ["rg", "-n", "--hidden", "--follow", "--color", "never", "--max-count", str(max_hits), pattern]
        if paths:
            cmd += paths
        code, out, err = _run(cmd)
        if code not in (0, 1):  # 1 means "no matches"
            raise RuntimeError(f"rg search failed: {err.strip()}")
        hits: List[Tuple[str, int, str]] = []
        for line in out.splitlines():
            # format: path:line:matchtext
            parts = line.split(":", 2)
            if len(parts) != 3:
                continue
            p, lno, txt = parts
            try:
                hits.append((p, int(lno), txt))
            except Exception:
                continue
        return hits

    # Fallback: Python regex scan (best-effort).
    rx = re.compile(pattern, flags=re.IGNORECASE)
    hits: List[Tuple[str, int, str]] = []
    for p in _walk_files():
        if len(hits) >= max_hits:
            break
        if _is_probably_binary(p):
            continue
        try:
            with (REPO_ROOT / p).open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, start=1):
                    if rx.search(line):
                        hits.append((p.as_posix(), i, line.rstrip("\n")))
                        if len(hits) >= max_hits:
                            break
        except Exception:
            continue
    return hits


def _read_text(p: Path, max_bytes: int) -> str:
    try:
        b = p.read_bytes()
    except Exception:
        return ""
    if len(b) > max_bytes:
        b = b[:max_bytes]
    try:
        return b.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _is_probably_binary(p: Path) -> bool:
    # quick check: presence of NUL byte in first 8KB
    try:
        b = p.read_bytes()[:8192]
    except Exception:
        return True
    return b"\x00" in b


def _default_excludes() -> List[str]:
    return [
        "data/**",
        "**/__pycache__/**",
        ".venv/**",
        "**/*.pyc",
        "**/*.png",
        "**/*.jpg",
        "**/*.jpeg",
        "**/*.wav",
        "**/*.mp3",
        "**/*.zip",
        "**/*.pdf",
    ]


@dataclass
class SelectedFile:
    path: str
    reason: str
    bytes_included: int
    content: str


def select_files_for_query(
    *,
    query: str,
    include_globs: List[str] | None,
    exclude_globs: List[str] | None,
    max_files: int,
    max_file_bytes: int,
) -> List[SelectedFile]:
    excludes = _default_excludes()
    if exclude_globs:
        excludes += exclude_globs

    # Build a candidate file list with rg --files, then filter by globs via rg itself.
    # We'll pass exclude globs to rg by re-running on selection steps.
    file_globs = include_globs or ["**/*.py", "**/*.md", "**/*.txt", "**/*.yaml", "**/*.yml", "**/*.toml", "**/*.json", "**/*.html"]
    files = _repo_files(file_globs)

    # Quick prune by suffix if include_globs not provided.
    # (We still respect user include_globs by keeping broad.)
    if include_globs is None:
        keep_sfx = {".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".html"}
        files = [p for p in files if p.suffix.lower() in keep_sfx]

    # Exclude known heavy/binary areas.
    # (We apply globs using simple string contains for the defaults; good enough for our repo.)
    def _excluded(p: Path) -> bool:
        s = p.as_posix()
        # Allow a few small data files even though we exclude data/** by default.
        if s == "data/ops_db.json" or s.startswith("data/scenarios/"):
            return False
        for g in excludes:
            if fnmatch.fnmatch(s, g):
                return True
        return False

    files = [p for p in files if not _excluded(p)]

    # Rank files by keyword hit count for query tokens.
    tokens = [t.strip() for t in query.replace("\n", " ").split(" ") if len(t.strip()) >= 3]
    tokens = tokens[:8]  # keep it small
    if not tokens:
        tokens = ["LeakSentinel", "orchestrator", "bedrock", "Nova"]
    score: dict[str, int] = {}
    if _have_rg():
        pat = "|".join([_escape_rg_regex(t) for t in tokens])
        hits = _rg_search(pat, paths=["."], max_hits=500)
        for p, _, _ in hits:
            try:
                rp = str(Path(p).resolve().relative_to(REPO_ROOT))
            except Exception:
                rp = str(Path(p))
            score[rp] = score.get(rp, 0) + 1
    else:
        # Fallback: lightweight per-file substring counting (no line numbers).
        tl = [t.lower() for t in tokens]
        for p in files:
            if _is_probably_binary(p):
                continue
            txt = _read_text(p, max_bytes=min(12_000, max_file_bytes))
            if not txt:
                continue
            low = txt.lower()
            sc = 0
            for t in tl:
                sc += low.count(t)
            if sc > 0:
                rp = str(p.as_posix())
                score[rp] = sc

    # Always include a few important top-level docs if present.
    must = []
    for mp in ["README.md", "plan.md", "ABOUT.md", "docs/SUBMISSION_CHECKLIST.md", "docs/BUDGET_PLAN.md"]:
        if Path(mp).exists():
            must.append(Path(mp))

    # Sort by score desc; then smaller files first to save tokens.
    def _file_key(p: Path) -> Tuple[int, int, str]:
        try:
            rp = str(p.resolve().relative_to(REPO_ROOT))
        except Exception:
            rp = str(p)
        sc = score.get(rp, 0)
        try:
            sz = p.stat().st_size
        except Exception:
            sz = 10**9
        return (-sc, sz, rp)

    ranked = sorted(files, key=_file_key)

    selected: List[Path] = []
    for p in must:
        if p not in selected:
            selected.append(p)
    for p in ranked:
        if len(selected) >= max_files:
            break
        if p in selected:
            continue
        rp = str(p.resolve().relative_to(REPO_ROOT))
        if score.get(rp, 0) <= 0 and len(selected) > 6:
            # once we have enough context, avoid pulling unrelated files
            continue
        selected.append(p)

    out: List[SelectedFile] = []
    for p in selected[:max_files]:
        if _is_probably_binary(p):
            continue
        try:
            rp = str(p.resolve().relative_to(REPO_ROOT))
        except Exception:
            rp = str(p)
        sc = score.get(rp, 0)
        reason = "core-doc" if p in must else (f"keyword_hits={sc}" if sc else "context")
        txt = _read_text(p, max_bytes=max_file_bytes)
        out.append(SelectedFile(path=rp, reason=reason, bytes_included=min(max_file_bytes, len(txt.encode("utf-8", "ignore"))), content=txt))
    return out


def _escape_rg_regex(s: str) -> str:
    # escape minimal regex chars for rg pattern
    for ch in "\\.^$|?*+()[]{}":
        s = s.replace(ch, "\\" + ch)
    return s


def build_prompt(*, query: str, files: List[SelectedFile]) -> str:
    parts = []
    parts.append("You are a senior engineer helping with codebase analysis. Be concise and actionable.")
    parts.append("")
    parts.append("Task:")
    parts.append(query.strip())
    parts.append("")
    parts.append("Repo context: The following files are provided (path + content). Use them, do not assume other files.")
    parts.append("")
    for f in files:
        parts.append(f"--- FILE: {f.path} ({f.reason}, bytes_included={f.bytes_included}) ---")
        parts.append(f.content)
        parts.append("")
    parts.append("Output:")
    parts.append("- Bullet summary")
    parts.append("- Concrete file/path references")
    parts.append("- If missing info, list what to fetch next (keywords / files)")
    return "\n".join(parts)


def call_openai(*, model: str, prompt: str, max_output_tokens: int) -> str:
    # Lazy import so script can run in --dry-run mode without deps.
    from openai import OpenAI  # type: ignore

    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")

    # base_url can be used for Azure OpenAI (OpenAI-compatible gateway), e.g.:
    # https://<resource>.openai.azure.com/openai/v1/
    client = OpenAI(api_key=api_key, base_url=base_url)

    effort = os.getenv("OPENAI_REASONING_EFFORT", "high")
    primary_kwargs = dict(model=model, input=prompt, max_output_tokens=int(max_output_tokens), reasoning={"effort": effort})
    fallback_kwargs = dict(model=model, input=prompt, max_output_tokens=int(max_output_tokens))

    # Try with reasoning effort, then fall back if the endpoint rejects the parameter.
    try:
        resp = client.responses.create(**primary_kwargs)
    except TypeError:
        resp = client.responses.create(**fallback_kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "reasoning" in msg or "unknown" in msg or "unrecognized" in msg:
            resp = client.responses.create(**fallback_kwargs)
        else:
            raise

    # SDKs expose output text slightly differently across versions.
    if hasattr(resp, "output_text") and resp.output_text:
        return str(resp.output_text)
    # Fallback: walk output blocks for text.
    try:
        chunks = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    chunks.append(t)
        if chunks:
            return "\n".join(chunks)
    except Exception:
        pass
    return json.dumps(resp.model_dump(), indent=2) if hasattr(resp, "model_dump") else str(resp)


def main() -> int:
    ap = argparse.ArgumentParser(description="Offload token-heavy repo reading/summarization to an OpenAI model.")
    ap.add_argument("--query", required=True, help="What you want the model to do (e.g., 'summarize architecture' / 'find stubs').")
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.2-codex"), help="OpenAI model id.")
    ap.add_argument(
        "--effort",
        default=os.getenv("OPENAI_REASONING_EFFORT", "high"),
        choices=["low", "medium", "high"],
        help="Reasoning effort (best-effort; ignored if model/SDK doesn't support it).",
    )
    ap.add_argument("--max-files", type=int, default=20)
    ap.add_argument("--max-file-bytes", type=int, default=24_000, help="Max bytes per file to include in the prompt.")
    ap.add_argument("--max-output-tokens", type=int, default=1200)
    ap.add_argument("--dry-run", action="store_true", help="Do not call OpenAI; write prompt + selection report only.")
    args = ap.parse_args()

    load_dotenv()
    # Expose effort to call_openai() without threading args everywhere.
    os.environ["OPENAI_REASONING_EFFORT"] = str(args.effort)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc_ts().replace(":", "-")
    base = REPORTS_DIR / f"offload_{ts}"

    files = select_files_for_query(
        query=args.query,
        include_globs=None,
        exclude_globs=None,
        max_files=int(args.max_files),
        max_file_bytes=int(args.max_file_bytes),
    )

    prompt = build_prompt(query=args.query, files=files)

    (base.with_suffix(".selection.json")).write_text(
        json.dumps(
            {
                "ts": _utc_ts(),
                "query": args.query,
                "model": args.model,
                "files": [{"path": f.path, "reason": f.reason, "bytes_included": f.bytes_included} for f in files],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (base.with_suffix(".prompt.txt")).write_text(prompt, encoding="utf-8")

    if args.dry_run:
        print(str(base))
        return 0

    if not os.getenv("OPENAI_API_KEY"):
        # Prompt securely to avoid users needing to understand env vars.
        # getpass does not echo the secret in the terminal.
        key = getpass.getpass("Enter OPENAI_API_KEY (input hidden): ").strip()
        if not key:
            raise SystemExit("OPENAI_API_KEY is required.")
        os.environ["OPENAI_API_KEY"] = key

    out = call_openai(model=args.model, prompt=prompt, max_output_tokens=int(args.max_output_tokens))
    (base.with_suffix(".out.md")).write_text(out, encoding="utf-8")
    print(str(base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

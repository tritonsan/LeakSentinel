from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

from leaksentinel.feedback.store import list_feedback_records
from leaksentinel.retrieval.local_hash_embed import cosine, embed_text


def top_k_similar_mistakes(
    *,
    query_text: str,
    feedback_records: list[Dict[str, Any]],
    k: int = 3,
    dim: int = 256,
    min_score: float = 0.0,
) -> list[Dict[str, Any]]:
    if not feedback_records:
        return []
    q = embed_text(query_text, dim=dim)
    scored: list[tuple[float, Dict[str, Any]]] = []
    for r in feedback_records:
        text = str(r.get("fingerprint_text") or "")
        if not text.strip():
            continue
        emb = embed_text(text, dim=dim)
        score = float(cosine(q, emb))
        if score >= float(min_score):
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    out: list[Dict[str, Any]] = []
    for score, r in scored[:k]:
        out.append(
            {
                "score": float(score),
                "feedback_id": r.get("feedback_id"),
                "outcome": r.get("outcome"),
                "scenario_id": r.get("scenario_id"),
                "zone": r.get("zone"),
                "timestamp": r.get("timestamp"),
                "decision": r.get("decision"),
                "confidence": r.get("confidence"),
                "operator_note": r.get("operator_note"),
                "root_cause_guess": r.get("root_cause_guess"),
                "evidence_gap": r.get("evidence_gap"),
                "bundle_path": r.get("bundle_path"),
            }
        )
    return out


def load_top_k_similar_mistakes(
    *,
    query_text: str,
    feedback_dir: Path,
    outcomes: Optional[list[str]] = None,
    k: int = 3,
    dim: int = 256,
    min_score: float = 0.0,
    limit: int = 300,
) -> list[Dict[str, Any]]:
    rows = list_feedback_records(feedback_dir=feedback_dir, limit=limit)
    if outcomes:
        allow = set(str(x) for x in outcomes)
        rows = [r for r in rows if str(r.get("outcome") or "") in allow]
    return top_k_similar_mistakes(query_text=query_text, feedback_records=rows, k=k, dim=dim, min_score=min_score)


def summarize_root_causes(similar_mistakes: list[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    rows = list(similar_mistakes or [])
    if not rows:
        return {"summary": "No similar historical false positives.", "top_causes": [], "top_evidence_gaps": []}

    cause_counter: Counter[str] = Counter()
    gap_counter: Counter[str] = Counter()
    for r in rows:
        cause = str(r.get("root_cause_guess") or "").strip()
        gap = str(r.get("evidence_gap") or "").strip()
        if cause:
            cause_counter[cause] += 1
        if gap:
            gap_counter[gap] += 1

    top_causes = [{"cause": c, "count": int(n)} for c, n in cause_counter.most_common(max(1, int(top_n)))]
    top_gaps = [{"gap": g, "count": int(n)} for g, n in gap_counter.most_common(max(1, int(top_n)))]

    if top_causes:
        head = top_causes[0]
        summary = (
            f"Most frequent historical false-positive cause: {head['cause']} "
            f"(seen {head['count']} times in top matches)."
        )
    else:
        summary = "Historical false positives exist, but root-cause tags are missing."
    return {"summary": summary, "top_causes": top_causes, "top_evidence_gaps": top_gaps}

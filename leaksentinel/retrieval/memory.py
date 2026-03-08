from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from leaksentinel.retrieval.local_hash_embed import embed_text, cosine


@dataclass(frozen=True)
class MemoryItem:
    path: Path
    embedding: np.ndarray
    summary: Dict[str, Any]


def _bundle_summary(obj: Dict[str, Any]) -> Dict[str, Any]:
    ev = obj.get("evidence", {})
    ctx = ev.get("context", {})
    return {
        "scenario_id": ctx.get("scenario_id"),
        "zone": ctx.get("zone"),
        "timestamp": ctx.get("timestamp"),
        "decision": obj.get("decision"),
        "confidence": obj.get("confidence"),
        "rationale": (obj.get("rationale") or [])[:2],
    }


def _bundle_text(obj: Dict[str, Any]) -> str:
    ev = obj.get("evidence", {})
    ctx = ev.get("context", {})
    flow = (ctx.get("flow_summary") or {})
    parts = [
        f"zone={ctx.get('zone')}",
        f"ts={ctx.get('timestamp')}",
        f"decision={obj.get('decision')}",
        f"anomaly={flow.get('anomaly_score')}",
    ]
    for r in (obj.get("rationale") or [])[:6]:
        parts.append(str(r))
    return " ".join(parts)


@dataclass
class EmbeddingsCache:
    path: Path
    data: Dict[str, Any]
    hits: int = 0
    misses: int = 0

    @classmethod
    def load(cls, path: Path) -> "EmbeddingsCache":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return cls(path=path, data=data)
            except Exception:
                pass
        return cls(path=path, data={})

    def get(self, key: str) -> Optional[List[float]]:
        v = self.data.get(key)
        if isinstance(v, list):
            self.hits += 1
            return [float(x) for x in v]
        self.misses += 1
        return None

    def set(self, key: str, vec: List[float]) -> None:
        self.data[key] = [float(x) for x in vec]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")


def _cache_key_for_file(*, model_id: str, dim: int, p: Path) -> str:
    try:
        mtime = int(p.stat().st_mtime)
    except Exception:
        mtime = 0
    return f"{model_id}|dim={dim}|file={p.name}|mtime={mtime}"


def _cache_key_for_query(*, model_id: str, dim: int, text: str) -> str:
    h = sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()
    return f"{model_id}|dim={dim}|query={h}"


def load_memory_local(evidence_dir: Path, *, dim: int = 256, limit: int = 200) -> List[MemoryItem]:
    if not evidence_dir.exists():
        return []
    items: List[MemoryItem] = []
    for p in sorted(evidence_dir.glob("*.json"))[-limit:]:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        emb = embed_text(_bundle_text(obj), dim=dim)
        items.append(MemoryItem(path=p, embedding=emb, summary=_bundle_summary(obj)))
    return items


def load_memory_bedrock(
    *,
    evidence_dir: Path,
    client: Any,
    model_id: str,
    cache: EmbeddingsCache,
    request_ids_out: Optional[List[str]] = None,
    dim: int = 256,
    limit: int = 200,
) -> List[MemoryItem]:
    from leaksentinel.bedrock.nova_embeddings import embed_text_via_bedrock_with_request_id

    if not evidence_dir.exists():
        return []
    items: List[MemoryItem] = []
    for p in sorted(evidence_dir.glob("*.json"))[-limit:]:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        key = _cache_key_for_file(model_id=model_id, dim=dim, p=p)
        vec = cache.get(key)
        if vec is None:
            emb, rid = embed_text_via_bedrock_with_request_id(client=client, model_id=model_id, text=_bundle_text(obj), dim=dim)
            if request_ids_out is not None and rid:
                request_ids_out.append(str(rid))
            cache.set(key, emb.astype(np.float32).tolist())
        else:
            emb = np.asarray(vec, dtype=np.float32)
        items.append(MemoryItem(path=p, embedding=emb, summary=_bundle_summary(obj)))
    cache.save()
    return items


def top_k_similar_local(query_text: str, memory: List[MemoryItem], *, k: int = 3, dim: int = 256) -> List[Dict[str, Any]]:
    q = embed_text(query_text, dim=dim)
    scored = []
    for it in memory:
        scored.append((cosine(q, it.embedding), it))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for score, it in scored[:k]:
        out.append(
            {
                "score": float(score),
                "bundle": it.path.name,
                **it.summary,
            }
        )
    return out


def top_k_similar_bedrock(
    *,
    query_text: str,
    memory: List[MemoryItem],
    client: Any,
    model_id: str,
    cache: EmbeddingsCache,
    request_ids_out: Optional[List[str]] = None,
    k: int = 3,
    dim: int = 256,
) -> List[Dict[str, Any]]:
    from leaksentinel.bedrock.nova_embeddings import embed_text_via_bedrock_with_request_id

    qkey = _cache_key_for_query(model_id=model_id, dim=dim, text=query_text)
    qv = cache.get(qkey)
    if qv is None:
        q, rid = embed_text_via_bedrock_with_request_id(client=client, model_id=model_id, text=query_text, dim=dim)
        if request_ids_out is not None and rid:
            request_ids_out.append(str(rid))
        cache.set(qkey, q.astype(np.float32).tolist())
    else:
        q = np.asarray(qv, dtype=np.float32)

    scored = []
    for it in memory:
        scored.append((cosine(q, it.embedding), it))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for score, it in scored[:k]:
        out.append(
            {
                "score": float(score),
                "bundle": it.path.name,
                **it.summary,
            }
        )
    cache.save()
    return out

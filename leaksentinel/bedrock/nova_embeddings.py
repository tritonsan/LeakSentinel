from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from leaksentinel.bedrock.runtime import invoke_model_json


def _extract_embedding_vector(data: Dict[str, Any]) -> List[float]:
    # Try common shapes. We keep it permissive because schemas can vary.
    # Nova embeddings (per AWS docs) often return:
    # { "embeddings": [ { "embeddingType": "TEXT", "embedding": [..] } ] }
    v = data.get("embeddings")
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, dict):
            vv = first.get("embedding")
            if isinstance(vv, list) and vv and isinstance(vv[0], (int, float)):
                return [float(x) for x in vv]

    for k in ["embedding", "vector", "outputEmbedding"]:
        vv = data.get(k)
        if isinstance(vv, list) and vv and isinstance(vv[0], (int, float)):
            return [float(x) for x in vv]
    raise ValueError(f"could not extract embedding from response keys={list(data.keys())}")


def embed_text_via_bedrock(
    *,
    client: Any,
    model_id: str,
    text: str,
    dim: int = 256,
) -> np.ndarray:
    emb, _req_id = embed_text_via_bedrock_with_request_id(client=client, model_id=model_id, text=text, dim=dim)
    return emb


def embed_text_via_bedrock_with_request_id(
    *,
    client: Any,
    model_id: str,
    text: str,
    dim: int = 256,
) -> tuple[np.ndarray, str | None]:
    if not text:
        return np.zeros((dim,), dtype=np.float32), None

    # Amazon Nova Multimodal Embeddings request schema (InvokeModel), per AWS docs.
    # Ref: https://docs.aws.amazon.com/nova/latest/userguide/nova-embeddings.html
    payload: Dict[str, Any] = {
        "schemaVersion": "nova-multimodal-embed-v1",
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": int(dim),
            "text": {"truncationMode": "END", "value": text},
        },
    }
    data, req_id, _ = invoke_model_json(client=client, model_id=model_id, payload=payload)

    vec = _extract_embedding_vector(data)
    arr = np.asarray(vec, dtype=np.float32)
    # Some models ignore requested dim; normalize/trim/pad to requested size for cosine consistency.
    if arr.size != dim:
        if arr.size > dim:
            arr = arr[:dim]
        else:
            pad = np.zeros((dim - arr.size,), dtype=np.float32)
            arr = np.concatenate([arr, pad], axis=0)
    # L2 normalize
    n = float(np.linalg.norm(arr))
    if n > 0:
        arr = arr / n
    return arr, req_id

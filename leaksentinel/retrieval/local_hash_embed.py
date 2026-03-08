from __future__ import annotations

import re
from typing import Iterable

import numpy as np


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def embed_text(text: str, *, dim: int = 256) -> np.ndarray:
    """
    Dependency-free embedding for local demo mode.
    Uses a simple hashing trick over tokens -> fixed-size vector.

    This is NOT a semantic embedding. It exists to validate retrieval plumbing
    before switching to Nova multimodal embeddings on Bedrock.
    """
    v = np.zeros((dim,), dtype=np.float32)
    toks = _tokens(text)
    if not toks:
        return v
    for tok in toks:
        v[hash(tok) % dim] += 1.0
    # L2 normalize
    n = float(np.linalg.norm(v))
    if n > 0:
        v /= n
    return v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


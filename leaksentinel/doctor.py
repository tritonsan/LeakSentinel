from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from leaksentinel.bedrock.runtime import (
    converse_image,
    converse_text,
    invoke_model_json,
    make_bedrock_runtime_client,
)


def _safe(s: str, n: int = 220) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def _get_env() -> Dict[str, str]:
    return {
        "AWS_REGION": os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "")),
        "NOVA_REASONING_MODEL_ID": os.getenv("NOVA_REASONING_MODEL_ID", ""),
        "NOVA_EMBEDDINGS_MODEL_ID": os.getenv("NOVA_EMBEDDINGS_MODEL_ID", ""),
        "NOVA_MULTIMODAL_MODEL_ID": os.getenv("NOVA_MULTIMODAL_MODEL_ID", ""),
    }


def _warn_reasoning_model_id(mid: str) -> List[str]:
    w: List[str] = []
    if not mid:
        w.append("NOVA_REASONING_MODEL_ID is empty.")
        return w
    if mid.count("arn:aws:bedrock:") > 1 or mid.startswith("arn:arn:"):
        w.append("NOVA_REASONING_MODEL_ID looks malformed (duplicate 'arn:').")
    if "YOUR_ACCOUNT_ID" in mid or "ACCOUNT_ID" in mid:
        w.append("NOVA_REASONING_MODEL_ID still contains placeholder text (YOUR_ACCOUNT_ID).")
    if ":inference-profile/" in mid and not mid.startswith("arn:aws:bedrock:"):
        w.append("Inference profile id/arn should start with arn:aws:bedrock:... (or be a plain profile id).")
    return w


def _payload_for_embeddings(text: str, dim: int = 256) -> Dict[str, Any]:
    return {
        "schemaVersion": "nova-multimodal-embed-v1",
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": int(dim),
            "text": {"truncationMode": "END", "value": text},
        },
    }


def _finalize_report(out: Dict[str, Any]) -> Dict[str, Any]:
    checks = {
        "identity_ok": bool(out.get("caller_identity")),
        "reasoning_ok": bool((out.get("reasoning_smoke") or {}).get("ok")),
        "multimodal_ok": bool((out.get("multimodal_smoke") or {}).get("ok")),
        "embeddings_ok": bool((out.get("embeddings_smoke") or {}).get("ok")),
    }
    passed = int(sum(1 for v in checks.values() if bool(v)))
    total = int(len(checks))
    out["checks"] = checks
    out["checks_passed"] = passed
    out["checks_total"] = total
    out["ready_for_bedrock_demo"] = bool(checks["identity_ok"] and (checks["reasoning_ok"] or checks["multimodal_ok"]))
    out["summary"] = f"Bedrock preflight passed {passed}/{total} checks."
    return out


def run_doctor(*, scenario_image: Optional[str] = None) -> Dict[str, Any]:
    """
    Bedrock/Nova preflight diagnostics without requiring AWS CLI.
    Prints: caller identity, env vars, and does 3 smoke calls:
    - reasoning converse (Nova 2 Lite inference profile)
    - multimodal converse (Nova Pro) with a sample image
    - embeddings invoke (Nova embeddings)
    """
    load_dotenv()

    env = _get_env()
    out: Dict[str, Any] = {"env": env, "warnings": _warn_reasoning_model_id(env["NOVA_REASONING_MODEL_ID"])}

    region = env["AWS_REGION"] or "us-east-1"
    out["region"] = region

    # Credentials + identity (boto3)
    try:
        import boto3  # type: ignore

        sts = boto3.client("sts", region_name=region)
        out["caller_identity"] = sts.get_caller_identity()
    except Exception as e:
        out["caller_identity_error"] = f"{type(e).__name__}: {_safe(e)}"
        return _finalize_report(out)

    # Bedrock runtime client
    try:
        brt = make_bedrock_runtime_client(region=region)
    except Exception as e:
        out["bedrock_runtime_client_error"] = f"{type(e).__name__}: {_safe(e)}"
        return _finalize_report(out)

    # Reasoning smoke
    out["reasoning_smoke"] = {"ok": False}
    mid = env["NOVA_REASONING_MODEL_ID"]
    if mid:
        try:
            r = converse_text(
                client=brt,
                model_id=mid,
                system="Return ONLY valid JSON.",
                user='Return {"ok": true, "component": "reasoning"}',
                inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 80},
            )
            out["reasoning_smoke"] = {"ok": True, "request_id": r.request_id, "text": _safe(r.text, 400)}
        except Exception as e:
            out["reasoning_smoke"] = {"ok": False, "error": f"{type(e).__name__}: {_safe(e)}"}

    # Multimodal smoke (image)
    out["multimodal_smoke"] = {"ok": False}
    mmid = env["NOVA_MULTIMODAL_MODEL_ID"]
    img_path = scenario_image or "data/thermal/zone-1/normal_00.png"
    if mmid and Path(img_path).exists():
        try:
            b = Path(img_path).read_bytes()
            r = converse_image(
                client=brt,
                model_id=mmid,
                system="Return ONLY valid JSON.",
                user='Return {"ok": true, "component": "multimodal"}',
                image_bytes=b,
                image_format="png",
                inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 120},
            )
            out["multimodal_smoke"] = {
                "ok": True,
                "request_id": r.request_id,
                "image_path": img_path,
                "text": _safe(r.text, 400),
            }
        except Exception as e:
            out["multimodal_smoke"] = {"ok": False, "error": f"{type(e).__name__}: {_safe(e)}"}
    else:
        out["multimodal_smoke"] = {"ok": False, "skipped": True, "reason": f"missing model id or image: {img_path}"}

    # Embeddings smoke
    out["embeddings_smoke"] = {"ok": False}
    emid = env["NOVA_EMBEDDINGS_MODEL_ID"]
    if emid:
        try:
            payload = _payload_for_embeddings("doctor smoke embedding", dim=256)
            data, req_id, _raw = invoke_model_json(client=brt, model_id=emid, payload=payload)
            # Don't dump full embeddings; just show shape.
            emb = None
            if isinstance(data, dict):
                embs = data.get("embeddings")
                if isinstance(embs, list) and embs and isinstance(embs[0], dict):
                    v = embs[0].get("embedding")
                    if isinstance(v, list):
                        emb = len(v)
            out["embeddings_smoke"] = {"ok": True, "request_id": req_id, "embedding_len": emb, "keys": list(data.keys())}
        except Exception as e:
            out["embeddings_smoke"] = {"ok": False, "error": f"{type(e).__name__}: {_safe(e)}"}

    return _finalize_report(out)


def main() -> int:
    rep = run_doctor()
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


def _lazy_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore

        return boto3, Config
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "boto3/botocore not available. Install runtime deps: pip install -r requirements.txt (or requirements-hosted.txt)."
        ) from e


@dataclass
class BedrockCallResult:
    text: str
    request_id: Optional[str]
    raw: Any


def make_bedrock_runtime_client(*, region: str):
    boto3, Config = _lazy_boto3()
    cfg = Config(
        connect_timeout=10,
        read_timeout=120,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return boto3.client("bedrock-runtime", region_name=region, config=cfg)


def _extract_request_id(resp: Any) -> Optional[str]:
    try:
        return resp.get("ResponseMetadata", {}).get("RequestId")
    except Exception:
        return None


def _extract_converse_text(resp: Dict[str, Any]) -> str:
    # Bedrock Converse response shape can differ across SDK versions.
    # We try a few common paths.
    try:
        content = resp["output"]["message"]["content"]
        for c in content:
            if "text" in c and c["text"] is not None:
                return str(c["text"])
    except Exception:
        pass
    try:
        # Some responses include "message" at top level.
        content = resp["message"]["content"]
        for c in content:
            if "text" in c and c["text"] is not None:
                return str(c["text"])
    except Exception:
        pass
    # As a last resort, serialize the resp to help debugging.
    return json.dumps(resp, ensure_ascii=True)


def converse_text(
    *,
    client: Any,
    model_id: str,
    system: str,
    user: str,
    inference_config: Optional[Dict[str, Any]] = None,
) -> BedrockCallResult:
    if not model_id:
        raise ValueError("model_id is empty")
    req = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": [{"text": user}]}],
    }
    if inference_config:
        req["inferenceConfig"] = inference_config
    resp = client.converse(**req)
    return BedrockCallResult(text=_extract_converse_text(resp), request_id=_extract_request_id(resp), raw=resp)


def converse_image(
    *,
    client: Any,
    model_id: str,
    system: str,
    user: str,
    image_bytes: bytes,
    image_format: str = "png",
    inference_config: Optional[Dict[str, Any]] = None,
) -> BedrockCallResult:
    if not model_id:
        raise ValueError("model_id is empty")
    content = [
        {"text": user},
        {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
    ]
    req = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": content}],
    }
    if inference_config:
        req["inferenceConfig"] = inference_config
    resp = client.converse(**req)
    return BedrockCallResult(text=_extract_converse_text(resp), request_id=_extract_request_id(resp), raw=resp)


def invoke_model_json(
    *,
    client: Any,
    model_id: str,
    payload: Dict[str, Any],
    content_type: str = "application/json",
    accept: str = "application/json",
) -> Tuple[Dict[str, Any], Optional[str], Any]:
    if not model_id:
        raise ValueError("model_id is empty")
    body = json.dumps(payload).encode("utf-8")
    resp = client.invoke_model(modelId=model_id, body=body, contentType=content_type, accept=accept)
    req_id = _extract_request_id(resp)
    raw_body = resp.get("body")
    data_bytes = raw_body.read() if hasattr(raw_body, "read") else raw_body
    if isinstance(data_bytes, (bytes, bytearray)):
        data = json.loads(data_bytes.decode("utf-8", errors="replace") or "{}")
    elif isinstance(data_bytes, str):
        data = json.loads(data_bytes or "{}")
    else:
        data = data_bytes if isinstance(data_bytes, dict) else {}
    return data, req_id, resp


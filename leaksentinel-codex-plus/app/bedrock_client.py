from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class ModelResult:
    json: Dict[str, Any]
    raw: Any = None

class BedrockClient:
    """Stub for local dev. Codex will replace with real Bedrock Nova calls."""
    def __init__(self, live: bool = False):
        self.live = live

    def thermal_check(self, *, prompt: str, image_path: str) -> ModelResult:
        return ModelResult(json={"has_leak_signature": False, "confidence": 0.2, "suspected_region":"none",
                                 "explanation":"Stub.", "next_step":"audio_check"})

    def audio_check(self, *, prompt: str, image_path: str) -> ModelResult:
        return ModelResult(json={"leak_like": False, "confidence": 0.2, "explanation":"Stub.", "next_step":"ops_verification"})

    def decision(self, *, prompt: str, evidence_json: Dict[str, Any]) -> ModelResult:
        return ModelResult(json={
            "decision":"INVESTIGATE","confidence":0.5,
            "rationale":["Stub decision."],
            "recommended_action":"Inspect on-site if anomaly persists.",
            "evidence_weights":{"flow":0.4,"thermal":0.25,"audio":0.25,"ops_override":0.1},
            "evidence":evidence_json
        })

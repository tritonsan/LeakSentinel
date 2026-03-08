from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any, List

class FlowEvent(BaseModel):
    zone: str
    timestamp: str  # ISO
    window_minutes: int = 120
    flow_file: Optional[str] = None

class ThermalOut(BaseModel):
    has_leak_signature: bool
    confidence: float = Field(ge=0, le=1)
    suspected_region: str
    explanation: str
    next_step: Literal["audio_check","ops_verification","none"]

class AudioOut(BaseModel):
    leak_like: bool
    confidence: float = Field(ge=0, le=1)
    explanation: str
    next_step: Literal["ops_verification","none"]

class OpsOut(BaseModel):
    planned_op_found: bool
    planned_op_ids: List[str] = []
    summary: str = ""
    raw: Dict[str, Any] = {}

class DecisionOut(BaseModel):
    decision: Literal["LEAK_CONFIRMED","INVESTIGATE","IGNORE_PLANNED_OPS"]
    confidence: float = Field(ge=0, le=1)
    rationale: List[str]
    recommended_action: str
    evidence_weights: Dict[str, float]
    evidence: Dict[str, Any] = {}

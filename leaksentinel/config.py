from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(frozen=True)
class Paths:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_DATA_DIR", "data")))
    scenarios_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_SCENARIOS_PATH", "data/scenarios/scenario_pack.json"))
    )
    ops_db_path: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_OPS_DB_PATH", "data/ops_db.json")))
    manifest_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_MANIFEST_PATH", "data/manifest/manifest.csv"))
    )
    evidence_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_EVIDENCE_DIR", "data/evidence_bundles"))
    )
    feedback_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_FEEDBACK_DIR", "data/feedback")))
    ops_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_OPS_DIR", "data/ops")))
    incidents_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_INCIDENTS_PATH", "data/ops/incidents.json"))
    )
    integrations_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_INTEGRATIONS_DIR", "data/integrations"))
    )
    connectors_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_CONNECTORS_PATH", "data/integrations/connectors.json"))
    )
    integration_events_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_INTEGRATION_EVENTS_PATH", "data/integrations/events.jsonl"))
    )
    exports_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_EXPORTS_DIR", "data/exports")))
    pressure_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_PRESSURE_DIR", "data/pressure")))
    standards_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_STANDARDS_DIR", "data/standards")))
    impact_dir: Path = field(default_factory=lambda: Path(os.getenv("LEAKSENTINEL_IMPACT_DIR", "data/impact")))
    confidence_calibration_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("LEAKSENTINEL_CONFIDENCE_CALIBRATION_PATH", "data/calibration/temperature_scaling_v1.json")
        )
    )


@dataclass(frozen=True)
class BedrockSettings:
    # Keep names generic; model ids differ across accounts/regions.
    # Use default_factory so values reflect the current environment (after loading .env).
    region: str = field(default_factory=lambda: os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")))
    nova_reasoning_model_id: str = field(default_factory=lambda: os.getenv("NOVA_REASONING_MODEL_ID", ""))
    nova_embeddings_model_id: str = field(default_factory=lambda: os.getenv("NOVA_EMBEDDINGS_MODEL_ID", ""))
    nova_multimodal_model_id: str = field(default_factory=lambda: os.getenv("NOVA_MULTIMODAL_MODEL_ID", ""))
    nova_sonic_model_id: str = field(default_factory=lambda: os.getenv("NOVA_SONIC_MODEL_ID", ""))


@dataclass(frozen=True)
class ImpactSettings:
    currency: str = field(default_factory=lambda: os.getenv("LEAKSENTINEL_IMPACT_CURRENCY", "USD"))
    dispatch_cost_usd: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_DISPATCH_COST_USD", "1200")))
    leak_loss_per_hour_usd: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_LEAK_LOSS_PER_HOUR_USD", "5000"))
    )
    default_delay_hours: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_DELAY_HOURS", "1.0")))
    investigate_dispatch_factor: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_INVESTIGATE_DISPATCH_FACTOR", "0.25"))
    )
    investigate_leak_factor: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_INVESTIGATE_LEAK_FACTOR", "0.15"))
    )
    assumptions_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_IMPACT_ASSUMPTIONS_PATH", "data/impact/assumptions.json"))
    )
    personas_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_IMPACT_PERSONAS_PATH", "data/impact/personas.json"))
    )


@dataclass(frozen=True)
class FlowAgentSettings:
    lookback_hours: int = field(default_factory=lambda: int(os.getenv("LEAKSENTINEL_FLOW_LOOKBACK_HOURS", "24")))
    min_flow_threshold: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_MIN_FLOW_THRESHOLD", "5.0"))
    )
    min_excess_lpm_threshold: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_MIN_EXCESS_LPM_THRESHOLD", "2.5"))
    )
    continuous_hours_threshold: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_CONTINUOUS_HOURS_THRESHOLD", "2.0"))
    )


@dataclass(frozen=True)
class PressureSettings:
    min_setpoint_m: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_MIN_SETPOINT_M", "35")))
    max_setpoint_m: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_MAX_SETPOINT_M", "70")))
    target_setpoint_m: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_TARGET_SETPOINT_M", "52")))


@dataclass(frozen=True)
class ScorecardSettings:
    water_unit_cost_usd_per_m3: float = field(
        default_factory=lambda: float(os.getenv("LEAKSENTINEL_WATER_UNIT_COST_USD_PER_M3", "1.8"))
    )
    co2e_kg_per_m3: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_CO2E_KG_PER_M3", "0.45")))
    baseline_nrw_pct: float = field(default_factory=lambda: float(os.getenv("LEAKSENTINEL_BASELINE_NRW_PCT", "24.0")))


@dataclass(frozen=True)
class StandardsSettings:
    default_profile_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_STANDARDS_PROFILE_PATH", "data/standards/building_profile.json"))
    )
    controls_catalog_path: Path = field(
        default_factory=lambda: Path(os.getenv("LEAKSENTINEL_STANDARDS_CATALOG_PATH", "data/standards/controls_catalog.json"))
    )


@dataclass(frozen=True)
class AppSettings:
    mode: str = field(default_factory=lambda: os.getenv("LEAKSENTINEL_MODE", "local"))  # local|bedrock
    paths: Paths = field(default_factory=Paths)
    bedrock: BedrockSettings = field(default_factory=BedrockSettings)
    impact: ImpactSettings = field(default_factory=ImpactSettings)
    flow_agent: FlowAgentSettings = field(default_factory=FlowAgentSettings)
    pressure: PressureSettings = field(default_factory=PressureSettings)
    scorecard: ScorecardSettings = field(default_factory=ScorecardSettings)
    standards: StandardsSettings = field(default_factory=StandardsSettings)

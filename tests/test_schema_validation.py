import pytest

from leaksentinel.bedrock.json_tools import (
    validate_audio_schema,
    validate_decision_schema,
    validate_thermal_schema,
)


def test_validate_decision_schema_ok() -> None:
    validate_decision_schema(
        {
            "decision": "INVESTIGATE",
            "confidence": 0.5,
            "rationale": ["a", "b"],
            "recommended_action": "Do something.",
            "evidence_weights": {"flow": 0.4, "thermal": 0.3, "audio": 0.2, "ops_override": 0.1},
        }
    )


def test_validate_decision_schema_conf_range() -> None:
    with pytest.raises(ValueError):
        validate_decision_schema(
            {
                "decision": "INVESTIGATE",
                "confidence": 1.5,
                "rationale": [],
                "recommended_action": "x",
                "evidence_weights": {},
            }
        )


def test_validate_thermal_schema_ok() -> None:
    validate_thermal_schema({"has_leak_signature": False, "confidence": 0.2, "explanation": "x"})


def test_validate_audio_schema_ok() -> None:
    validate_audio_schema({"leak_like": True, "confidence": 0.8, "explanation": "x"})


from __future__ import annotations

import pytest

from leaksentinel.act.ops_check import run_ops_check_act


class _FakeActClient:
    def get_workflow_definition(self, workflowDefinitionName: str):  # noqa: N802
        raise RuntimeError("not found")

    def create_workflow_definition(self, name: str, description: str):  # noqa: N802
        return {"name": name}

    def create_workflow_run(self, workflowDefinitionName: str, modelId: str, clientInfo: dict):  # noqa: N802
        return {"workflowRunId": "wfr-1"}

    def create_session(self, workflowDefinitionName: str, workflowRunId: str):  # noqa: N802
        return {"sessionId": "sess-1"}

    def create_act(self, **kwargs):  # noqa: ANN003
        return {"actId": "act-1"}

    def invoke_act_step(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("invoke step failed")


def test_ops_check_strict_fail_no_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_client(service_name: str, region_name: str):  # noqa: ARG001
        assert service_name == "nova-act"
        return _FakeActClient()

    monkeypatch.setattr("leaksentinel.act.ops_check.boto3.client", _fake_client)

    with pytest.raises(RuntimeError) as ei:
        run_ops_check_act(
            zone="zone-1",
            start="2026-02-05T02:00:00",
            end="2026-02-05T04:00:00",
            op_type=None,
        )
    msg = str(ei.value)
    assert "strict mode" in msg
    assert '"workflow_run_id": "wfr-1"' in msg
    assert '"session_id": "sess-1"' in msg
    assert '"act_id": "act-1"' in msg

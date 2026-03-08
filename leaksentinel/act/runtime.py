from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _utc_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ActRunLog:
    workflow_definition_name: str
    workflow_run_id: str
    session_id: str
    act_id: str
    steps: List[Dict[str, Any]]
    created_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_definition_name": self.workflow_definition_name,
            "workflow_run_id": self.workflow_run_id,
            "session_id": self.session_id,
            "act_id": self.act_id,
            "created_at_utc": self.created_at_utc,
            "steps": self.steps,
        }


def ensure_workflow_definition(*, client: Any, name: str, description: str) -> None:
    try:
        client.get_workflow_definition(workflowDefinitionName=name)
        return
    except Exception:
        pass
    client.create_workflow_definition(name=name, description=description)


def create_workflow_run(*, client: Any, workflow_definition_name: str, model_id: str) -> str:
    resp = client.create_workflow_run(
        workflowDefinitionName=workflow_definition_name,
        modelId=model_id,
        clientInfo={"compatibilityVersion": 1, "sdkVersion": "leaksentinel/0.1.0"},
    )
    return str(resp["workflowRunId"])


def create_session(*, client: Any, workflow_definition_name: str, workflow_run_id: str) -> str:
    resp = client.create_session(workflowDefinitionName=workflow_definition_name, workflowRunId=workflow_run_id)
    return str(resp["sessionId"])


def create_act(
    *,
    client: Any,
    workflow_definition_name: str,
    workflow_run_id: str,
    session_id: str,
    task: str,
    tool_specs: List[Dict[str, Any]],
) -> str:
    resp = client.create_act(
        workflowDefinitionName=workflow_definition_name,
        workflowRunId=workflow_run_id,
        sessionId=session_id,
        task=task,
        toolSpecs=tool_specs,
    )
    return str(resp["actId"])


def run_tool_loop(
    *,
    client: Any,
    workflow_definition_name: str,
    workflow_run_id: str,
    session_id: str,
    act_id: str,
    tool_impl: Any,
    max_steps: int = 10,
) -> Tuple[Optional[Dict[str, Any]], ActRunLog]:
    """
    Runs Nova Act tool-calling until it calls `return_result` or exhausts steps.

    Returns: (result_obj, log)
    """
    steps: List[Dict[str, Any]] = []
    prev_step_id: Optional[str] = None

    # First call: pass empty results to get the first set of calls (works with the API).
    # API requires at least 1 callResult even for the first step, but there is no prior callId yet.
    # We omit callId entirely and provide a bootstrap content block.
    call_results: List[Dict[str, Any]] = [{"content": [{"text": "bootstrap"}]}]

    result_obj: Optional[Dict[str, Any]] = None

    for _ in range(max_steps):
        resp = client.invoke_act_step(
            workflowDefinitionName=workflow_definition_name,
            workflowRunId=workflow_run_id,
            sessionId=session_id,
            actId=act_id,
            callResults=call_results,
            **({"previousStepId": prev_step_id} if prev_step_id else {}),
        )
        prev_step_id = str(resp.get("stepId") or "")
        calls = resp.get("calls") or []

        step_rec: Dict[str, Any] = {"stepId": prev_step_id, "calls": calls, "callResults": []}

        call_results = []
        for c in calls:
            call_id = str(c.get("callId") or "")
            name = str(c.get("name") or "")
            inp = c.get("input")  # document -> python dict

            if name == "return_result":
                # We expect the agent to call this tool with a JSON object containing the final answer.
                if isinstance(inp, dict):
                    result_obj = inp
                else:
                    try:
                        result_obj = json.loads(str(inp))
                    except Exception:
                        result_obj = {"raw": inp}

                call_results.append({"callId": call_id, "content": [{"text": "ok"}]})
                step_rec["callResults"].append({"callId": call_id, "tool": name, "ok": True})
                continue

            try:
                out_text = tool_impl(name=name, tool_input=inp)
                call_results.append({"callId": call_id, "content": [{"text": out_text}]})
                step_rec["callResults"].append({"callId": call_id, "tool": name, "ok": True})
            except Exception as e:
                call_results.append({"callId": call_id, "content": [{"text": f"error:{e}"}]})
                step_rec["callResults"].append({"callId": call_id, "tool": name, "ok": False, "error": str(e)})

        steps.append(step_rec)
        if result_obj is not None:
            break

    log = ActRunLog(
        workflow_definition_name=workflow_definition_name,
        workflow_run_id=workflow_run_id,
        session_id=session_id,
        act_id=act_id,
        steps=steps,
        created_at_utc=_utc_ts(),
    )
    return result_obj, log


def write_act_log(*, out_dir: Path, log: ActRunLog) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = log.created_at_utc.replace(":", "-")
    p = out_dir / f"act_run_{safe_ts}.json"
    p.write_text(json.dumps(log.to_dict(), indent=2), encoding="utf-8")
    return p

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import boto3

from leaksentinel.config import AppSettings
from leaksentinel.tools.ops import find_planned_ops
from leaksentinel.act.runtime import (
    create_act,
    create_session,
    create_workflow_run,
    ensure_workflow_definition,
    run_tool_loop,
    write_act_log,
)


def _tool_specs() -> list[dict[str, Any]]:
    # Nova Act expects JSON Schema under inputSchema.json (document).
    return [
        {
            "name": "query_planned_ops",
            "description": "Query planned operations for a zone and time window and return matching planned_op_id values.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "zone": {"type": "string"},
                        "start": {"type": "string", "description": "ISO timestamp"},
                        "end": {"type": "string", "description": "ISO timestamp"},
                        "op_type": {"type": ["string", "null"]},
                    },
                    "required": ["zone", "start", "end"],
                }
            },
        },
        {
            "name": "return_result",
            "description": "Return the final answer as a JSON object in the tool input (not as free text).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "planned_op_found": {"type": "boolean"},
                        "planned_op_ids": {"type": "array", "items": {"type": "string"}},
                        "summary": {"type": "string"},
                        "query": {"type": "object"},
                    },
                    "required": ["planned_op_found", "planned_op_ids", "summary"],
                }
            },
        },
    ]


def run_ops_check_act(*, zone: str, start: str, end: str, op_type: Optional[str] = None) -> Dict[str, Any]:
    settings = AppSettings()
    region = settings.bedrock.region
    model_id = os.getenv("NOVA_ACT_MODEL_ID", "nova-act-v1.0")

    client = boto3.client("nova-act", region_name=region)
    wfd = os.getenv("LEAKSENTINEL_ACT_WORKFLOW_NAME", "leaksentinel-ops-check")
    wfr: Optional[str] = None
    sess: Optional[str] = None
    act_id: Optional[str] = None

    def tool_impl(*, name: str, tool_input: Any) -> str:
        if name != "query_planned_ops":
            raise ValueError(f"unknown tool: {name}")
        if not isinstance(tool_input, dict):
            raise ValueError("tool_input must be a JSON object")
        z = str(tool_input.get("zone") or zone)
        s = str(tool_input.get("start") or start)
        e = str(tool_input.get("end") or end)
        t = tool_input.get("op_type", op_type)
        out = find_planned_ops(
            ops_db_path=settings.paths.ops_db_path,
            zone=z,
            start=s,
            end=e,
            op_type=(str(t) if t not in (None, "", "null") else None),
        )
        # Tool results are text; return JSON string for the agent.
        return json.dumps(out)

    try:
        ensure_workflow_definition(
            client=client,
            name=wfd,
            description="LeakSentinel demo workflow: use Nova Act tool-calling to validate planned ops.",
        )
        wfr = create_workflow_run(client=client, workflow_definition_name=wfd, model_id=model_id)
        sess = create_session(client=client, workflow_definition_name=wfd, workflow_run_id=wfr)
        task = (
            "You are an operations verification agent.\n"
            "Given a zone and time window, determine whether there is a planned operation overlapping the window.\n"
            "Use query_planned_ops exactly once.\n"
            "Then call return_result with {planned_op_found, planned_op_ids, summary, query}.\n"
            f"Inputs:\nzone={zone}\nstart={start}\nend={end}\nop_type={op_type or ''}\n"
        )
        act_id = create_act(
            client=client,
            workflow_definition_name=wfd,
            workflow_run_id=wfr,
            session_id=sess,
            task=task,
            tool_specs=_tool_specs(),
        )
        result, log = run_tool_loop(
            client=client,
            workflow_definition_name=wfd,
            workflow_run_id=wfr,
            session_id=sess,
            act_id=act_id,
            tool_impl=lambda name, tool_input: tool_impl(name=name, tool_input=tool_input),
            max_steps=8,
        )
        log_path = write_act_log(out_dir=Path("data/_reports/act_runs"), log=log)
        if result is None:
            raise RuntimeError("Nova Act did not call return_result within max steps.")

        result = dict(result)
        result["_runtime"] = {
            "region": region,
            "model_id": model_id,
            "workflow_definition_name": wfd,
            "workflow_run_id": wfr,
            "session_id": sess,
            "act_id": act_id,
            "log_path": str(log_path),
        }
        result["ok"] = True
        return result
    except Exception as e:
        ctx = {
            "region": region,
            "model_id": model_id,
            "workflow_definition_name": wfd,
            "workflow_run_id": wfr,
            "session_id": sess,
            "act_id": act_id,
        }
        raise RuntimeError(
            "Nova Act ops-check failed (strict mode). "
            f"context={json.dumps(ctx)} error={type(e).__name__}: {e}"
        ) from e

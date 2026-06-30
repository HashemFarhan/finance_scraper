from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import boto3

import storage
from core.loop_controller import LoopController

WORK_DIR = Path("/tmp/runs")

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("DDB_TABLE", "")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job = _extract_job(event)
    url = job.get("url")
    if not url:
        raise ValueError("url is required")

    job_id = job.get("job_id") or str(uuid.uuid4())

    _set_status(job_id, "running")

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    try:
        controller = LoopController(
            max_steps=int(job.get("max_steps", 5)),
            max_runtime_seconds=int(job.get("max_runtime", 120)),
            output_dir=WORK_DIR,
            headless=True,
            llm_model=job.get("model"),
        )

        result = asyncio.run(controller.run(url)).to_dict()
        result_key = storage.publish(job_id, result)

        _set_status(job_id, "done", result_key=result_key)

        return {
            "job_id": job_id,
            "result_key": result_key,
            "form_found": result.get("form_found"),
            "final_url": result.get("final_url"),
            "errors": result.get("errors", []),
        }

    except Exception as exc:
        _set_status(job_id, "failed", error=str(exc))
        raise


def _extract_job(event: dict[str, Any]) -> dict[str, Any]:
    records = event.get("Records")
    if records and isinstance(records, list):
        body = records[0].get("body", "{}")
        return json.loads(body) if isinstance(body, str) else body
    return event


def _set_status(job_id: str, status: str, **extra: Any) -> None:
    if not TABLE_NAME:
        return
    table = dynamodb.Table(TABLE_NAME)
    update_expr = "SET #s = :s"
    attr_names = {"#s": "status"}
    attr_values: dict[str, Any] = {":s": status}

    for key, value in extra.items():
        safe_key = f"#{key}"
        update_expr += f", {safe_key} = :{key}"
        attr_names[safe_key] = key
        attr_values[f":{key}"] = value

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )

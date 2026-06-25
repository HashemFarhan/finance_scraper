from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any

import storage
from core.loop_controller import LoopController

# /tmp is the only writable location in Lambda. A warm container reuses /tmp
# across invocations, so each run starts from a clean directory.
WORK_DIR = Path("/tmp/runs")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    url = event.get("url")
    if not url:
        raise ValueError("event.url is required")

    job_id = event.get("job_id") or str(uuid.uuid4())

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    controller = LoopController(
        max_steps=int(event.get("max_steps", 5)),
        max_runtime_seconds=int(event.get("max_runtime", 120)),
        output_dir=WORK_DIR,
        headless=True,
        llm_model=event.get("model"),
    )

    result = asyncio.run(controller.run(url)).to_dict()
    result_key = storage.publish(job_id, result)

    return {
        "job_id": job_id,
        "result_key": result_key,
        "form_found": result.get("form_found"),
        "final_url": result.get("final_url"),
        "errors": result.get("errors", []),
    }

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import boto3

s3 = boto3.client("s3")


def publish(job_id: str, result: dict[str, Any]) -> str:
    """Upload screenshots + result.json to S3 and rewrite local paths to S3 keys.

    The crawler writes screenshots to the local /tmp filesystem and records their
    absolute paths in result["screenshots"] (and inside each step). Those paths are
    meaningless to any client, so we upload each file once and replace every
    reference with its S3 object key.
    """
    bucket = os.environ["S3_BUCKET"]

    local_to_key: dict[str, str] = {}
    for local_path in _iter_screenshot_paths(result):
        if local_path in local_to_key:
            continue
        key = f"{job_id}/screenshots/{Path(local_path).name}"
        s3.upload_file(local_path, bucket, key, ExtraArgs={"ContentType": "image/png"})
        local_to_key[local_path] = key

    _rewrite_screenshot_paths(result, local_to_key)

    result_key = f"{job_id}/result.json"
    s3.put_object(
        Bucket=bucket,
        Key=result_key,
        Body=json.dumps(result, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    return result_key


def _iter_screenshot_paths(result: dict[str, Any]):
    yield from (p for p in result.get("screenshots", []) if p)
    for step in result.get("steps", []):
        yield from (p for p in step.get("screenshots", []) if p)


def _rewrite_screenshot_paths(result: dict[str, Any], mapping: dict[str, str]) -> None:
    result["screenshots"] = [mapping.get(p, p) for p in result.get("screenshots", [])]
    for step in result.get("steps", []):
        step["screenshots"] = [mapping.get(p, p) for p in step.get("screenshots", [])]

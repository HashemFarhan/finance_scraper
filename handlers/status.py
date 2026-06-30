from __future__ import annotations

import json
import os
from typing import Any

import boto3

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

TABLE_NAME = os.environ["DDB_TABLE"]
BUCKET = os.environ["S3_BUCKET"]
PRESIGN_EXPIRY = 3600


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job_id = (
        event.get("pathParameters", {}) or {}
    ).get("job_id") or event.get("job_id", "")

    if not job_id:
        return _response(400, {"error": "job_id is required"})

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"job_id": job_id}).get("Item")

    if not item:
        return _response(404, {"error": "Job not found"})

    status = item.get("status", "unknown")
    result: dict[str, Any] = {"job_id": job_id, "status": status}

    if status == "done":
        result_key = item.get("result_key")
        if result_key:
            result["result_url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET, "Key": result_key},
                ExpiresIn=PRESIGN_EXPIRY,
            )

    if status == "failed":
        result["error"] = item.get("error", "Unknown error")

    return _response(200, result)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }

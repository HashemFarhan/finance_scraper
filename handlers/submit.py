from __future__ import annotations

import json
import os
import uuid
from ipaddress import ip_address
from socket import gaierror, getaddrinfo
from typing import Any
from urllib.parse import urlparse

import boto3

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

TABLE_NAME = os.environ["DDB_TABLE"]
QUEUE_URL = os.environ["SQS_QUEUE_URL"]

MAX_STEPS_MIN = 1
MAX_STEPS_MAX = 20
MAX_RUNTIME_MIN = 10
MAX_RUNTIME_MAX = 900


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _response(400, {"error": str(exc)})

    url = body.get("url", "").strip()
    if not url:
        return _response(400, {"error": "url is required"})

    try:
        url = _validate_url(url)
    except ValueError as exc:
        return _response(400, {"error": str(exc)})

    max_steps = _bounded_int(body.get("max_steps", 5), MAX_STEPS_MIN, MAX_STEPS_MAX)
    max_runtime = _bounded_int(body.get("max_runtime", 120), MAX_RUNTIME_MIN, MAX_RUNTIME_MAX)
    model = body.get("model")

    job_id = str(uuid.uuid4())

    table = dynamodb.Table(TABLE_NAME)
    table.put_item(Item={
        "job_id": job_id,
        "status": "queued",
        "url": url,
        "max_steps": max_steps,
        "max_runtime": max_runtime,
    })

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "job_id": job_id,
            "url": url,
            "max_steps": max_steps,
            "max_runtime": max_runtime,
            "model": model,
        }),
    )

    return _response(202, {"job_id": job_id, "status": "queued"})


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if body is None:
        return event
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
    return body


def _validate_url(raw: str) -> str:
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("Invalid URL: no hostname.")

    try:
        results = getaddrinfo(parsed.hostname, None)
    except gaierror as exc:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}") from exc

    for _, _, _, _, sockaddr in results:
        addr = ip_address(sockaddr[0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError("URLs pointing to private/internal networks are not allowed.")

    return raw


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, n))


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }

from __future__ import annotations

import argparse
import asyncio
import json
import threading
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.loop_controller import LoopController
from utils.logging import configure_logging


ROOT = Path(__file__).resolve().parent
LATEST_RESULT = ROOT / "runs" / "result.json"
INSPECTION_LOCK = threading.Lock()


class ReportRequestHandler(SimpleHTTPRequestHandler):
    server_version = "ComplianceReportServer/0.1"

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/health":
            self._send_json({"ok": True})
            return
        if route == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/ui/")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route != "/api/inspect":
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API route")
            return

        try:
            payload = self._read_json()
            settings = InspectionSettings.from_payload(payload)
            if not INSPECTION_LOCK.acquire(blocking=False):
                self._send_json(
                    {"error": "Another inspection is already running."},
                    status=HTTPStatus.CONFLICT,
                )
                return
            try:
                result = asyncio.run(run_inspection(settings))
            finally:
                INSPECTION_LOCK.release()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"error": f"Inspection failed: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        LATEST_RESULT.parent.mkdir(parents=True, exist_ok=True)
        LATEST_RESULT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        self._send_json(result)

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid request length.") from exc
        if length <= 0:
            raise ValueError("Request body is required.")
        if length > 65_536:
            raise ValueError("Request body is too large.")
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


class InspectionSettings:
    def __init__(
        self,
        url: str,
        max_steps: int,
        max_runtime: int,
        headful: bool,
        use_llm: bool,
        model: str | None,
    ) -> None:
        self.url = url
        self.max_steps = max_steps
        self.max_runtime = max_runtime
        self.headful = headful
        self.use_llm = use_llm
        self.model = model

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "InspectionSettings":
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("URL is required.")
        parsed = urlparse(url if "://" in url else f"https://{url}")
        if not parsed.netloc:
            raise ValueError("Enter a valid URL or domain.")

        return cls(
            url=url,
            max_steps=bounded_int(payload.get("max_steps", 5), "max_steps", minimum=1, maximum=20),
            max_runtime=bounded_int(
                payload.get("max_runtime", 120), "max_runtime", minimum=10, maximum=900
            ),
            headful=bool(payload.get("headful", False)),
            use_llm=bool(payload.get("use_llm", True)),
            model=clean_optional_text(payload.get("model")),
        )


async def run_inspection(settings: InspectionSettings) -> dict[str, Any]:
    controller = LoopController(
        max_steps=settings.max_steps,
        max_runtime_seconds=settings.max_runtime,
        output_dir=ROOT / "runs",
        headless=not settings.headful,
        use_llm=settings.use_llm,
        llm_model=settings.model,
    )
    result = await controller.run(settings.url)
    return result.to_dict()


def bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def clean_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the inspection UI and local crawler API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    configure_logging(args.verbose)

    handler = partial(ReportRequestHandler, directory=str(ROOT))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving inspection UI at http://{args.host}:{args.port}/ui/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

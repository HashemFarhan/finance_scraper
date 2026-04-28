from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Navigate to a page, find a form, and extract compliance evidence."
    )
    parser.add_argument("url", help="Source URL to inspect.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the structured JSON result.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs"),
        help="Directory used for screenshots and run artifacts.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=5,
        help="Maximum navigation decisions before stopping.",
    )
    parser.add_argument(
        "--max-runtime",
        type=int,
        default=120,
        help="Maximum runtime in seconds for navigation before extraction.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Show the browser instead of running headless.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable the vision LLM and use heuristic navigation only.",
    )
    parser.add_argument(
        "--model",
        help="OpenAI-compatible vision model name. Defaults to OPENAI_MODEL or gpt-4o-mini.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


async def run(args: argparse.Namespace) -> dict:
    from core.loop_controller import LoopController

    controller = LoopController(
        max_steps=args.max_steps,
        max_runtime_seconds=args.max_runtime,
        output_dir=args.output_dir,
        headless=not args.headful,
        use_llm=not args.no_llm,
        llm_model=args.model,
    )
    result = await controller.run(args.url)
    return result.to_dict()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)

    try:
        payload = asyncio.run(run(args))
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            print(
                "Playwright is not installed. Run: pip install -r requirements.txt && playwright install chromium",
                file=sys.stderr,
            )
            return 2
        raise

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

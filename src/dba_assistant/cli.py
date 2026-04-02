from __future__ import annotations

import argparse
from pathlib import Path

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.service import execute_request
from dba_assistant.deep_agent_integration.config import load_app_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dba-assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("prompt")
    ask_parser.add_argument("--config", default=None)
    ask_parser.add_argument("--input", action="append", default=[], type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ask":
        config = load_app_config(args.config)
        request = normalize_raw_request(
            args.prompt,
            default_output_mode=config.runtime.default_output_mode,
            input_paths=args.input,
        )
        print(execute_request(request, config=config))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

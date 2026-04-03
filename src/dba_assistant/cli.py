from __future__ import annotations

import argparse
from dataclasses import replace
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
    ask_parser.add_argument("--profile", default=None)
    ask_parser.add_argument("--report-format", choices=("summary", "docx"), default=None)
    ask_parser.add_argument("--output", default=None, type=Path)
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
        request = _apply_cli_overrides(request, args)
        print(execute_request(request, config=config))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _apply_cli_overrides(request, args):
    if not hasattr(request, "runtime_inputs") or not hasattr(request, "rdb_overrides"):
        return request

    runtime_inputs = request.runtime_inputs
    if args.report_format is not None:
        runtime_inputs = replace(
            runtime_inputs,
            output_mode="summary" if args.report_format == "summary" else "report",
            report_format=None if args.report_format == "summary" else args.report_format,
        )
    if args.output is not None:
        runtime_inputs = replace(runtime_inputs, output_path=args.output)
    if args.input:
        runtime_inputs = replace(runtime_inputs, input_paths=tuple(args.input))

    rdb_overrides = request.rdb_overrides
    if args.profile is not None:
        rdb_overrides = replace(rdb_overrides, profile_name=args.profile)

    return replace(request, runtime_inputs=runtime_inputs, rdb_overrides=rdb_overrides)

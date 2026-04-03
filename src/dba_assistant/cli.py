"""Thin CLI — prompt + structured parameters only.

All business logic, request normalization, HITL, and capability selection
are delegated to the interface adapter and orchestrator layers.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dba_assistant.interface.adapter import handle_request
from dba_assistant.interface.hitl import CliApprovalHandler
from dba_assistant.interface.types import InterfaceRequest


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
        request = InterfaceRequest(
            prompt=args.prompt,
            input_paths=args.input,
            output_path=args.output,
            config_path=args.config,
            profile=args.profile,
            report_format=args.report_format,
        )
        result = handle_request(request, approval_handler=CliApprovalHandler())
        print(result)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

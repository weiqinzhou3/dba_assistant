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


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer value: {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("mysql-stage-batch-size must be > 0")
    return parsed


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
    ask_parser.add_argument(
        "--input-kind",
        choices=("local_rdb", "precomputed", "preparsed_mysql", "remote_redis"),
        default=None,
    )
    ask_parser.add_argument(
        "--path-mode",
        choices=(
            "auto",
            "database_backed_analysis",
            "preparsed_dataset_analysis",
            "direct_rdb_analysis",
        ),
        default=None,
    )
    ask_parser.add_argument("--redis-password", default=None)
    ask_parser.add_argument("--ssh-host", default=None)
    ask_parser.add_argument("--ssh-port", default=None, type=int)
    ask_parser.add_argument("--ssh-username", default=None)
    ask_parser.add_argument("--ssh-password", default=None)
    ask_parser.add_argument("--remote-rdb-path", default=None)
    ask_parser.add_argument(
        "--remote-rdb-path-source",
        choices=("user_override", "discovered", "fallback_default"),
        default=None,
    )
    ask_parser.add_argument("--fresh-rdb", action="store_true")
    ask_parser.add_argument("--mysql-host", default=None)
    ask_parser.add_argument("--mysql-port", default=None, type=int)
    ask_parser.add_argument("--mysql-user", default=None)
    ask_parser.add_argument("--mysql-database", default=None)
    ask_parser.add_argument("--mysql-password", default=None)
    ask_parser.add_argument("--mysql-table", default=None)
    ask_parser.add_argument("--mysql-query", default=None)
    ask_parser.add_argument("--mysql-stage-batch-size", default=None, type=_positive_int)
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
            input_kind=args.input_kind,
            path_mode=args.path_mode,
            redis_password=args.redis_password,
            ssh_host=args.ssh_host,
            ssh_port=args.ssh_port,
            ssh_username=args.ssh_username,
            ssh_password=args.ssh_password,
            remote_rdb_path=args.remote_rdb_path,
            remote_rdb_path_source=args.remote_rdb_path_source,
            require_fresh_rdb_snapshot=args.fresh_rdb or None,
            mysql_host=args.mysql_host,
            mysql_port=args.mysql_port,
            mysql_user=args.mysql_user,
            mysql_database=args.mysql_database,
            mysql_password=args.mysql_password,
            mysql_table=args.mysql_table,
            mysql_query=args.mysql_query,
            mysql_stage_batch_size=args.mysql_stage_batch_size,
        )
        result = handle_request(request, approval_handler=CliApprovalHandler())
        print(result)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

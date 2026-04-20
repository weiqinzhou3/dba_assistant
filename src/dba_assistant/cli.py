"""Thin CLI — prompt + structured parameters only.

All business logic, request normalization, HITL, and capability selection
are delegated to the interface adapter and orchestrator layers.
"""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from dba_assistant.deep_agent_integration.config import load_app_config
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
    ask_parser.add_argument("prompt", nargs="?", default=None)
    ask_parser.add_argument("--config", default=None)
    ask_parser.add_argument("--input", action="append", default=[], type=Path)
    ask_parser.add_argument("--profile", default=None)
    ask_parser.add_argument("--report-format", choices=("summary", "docx"), default=None)
    ask_parser.add_argument("--output", default=None, type=Path)
    ask_parser.add_argument(
        "--input-kind",
        choices=("local_rdb", "precomputed", "preparsed_mysql", "remote_redis", "redis_inspection"),
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
    ask_parser.add_argument("--stream", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ask":
        # Initial request from CLI flags
        initial_request = InterfaceRequest(
            prompt=args.prompt or "",
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

        approval_handler = CliApprovalHandler()
        thread_id = f"cli-session-{uuid.uuid4()}"
        streaming_enabled = args.stream or _config_cli_streaming_enabled(args.config)
        
        # State to carry across turns
        current_input_paths = list(args.input)
        current_mysql_host = args.mysql_host
        current_mysql_port = args.mysql_port
        current_mysql_user = args.mysql_user
        current_mysql_database = args.mysql_database
        current_mysql_table = args.mysql_table

        def _update_state(normalized: NormalizedRequest):
            nonlocal current_input_paths, current_mysql_host, current_mysql_port
            nonlocal current_mysql_user, current_mysql_database, current_mysql_table
            if normalized.runtime_inputs.input_paths:
                current_input_paths = list(normalized.runtime_inputs.input_paths)
            if normalized.runtime_inputs.mysql_host:
                current_mysql_host = normalized.runtime_inputs.mysql_host
            if normalized.runtime_inputs.mysql_port:
                current_mysql_port = normalized.runtime_inputs.mysql_port
            if normalized.runtime_inputs.mysql_user:
                current_mysql_user = normalized.runtime_inputs.mysql_user
            if normalized.runtime_inputs.mysql_database:
                current_mysql_database = normalized.runtime_inputs.mysql_database
            if normalized.runtime_inputs.mysql_table:
                current_mysql_table = normalized.runtime_inputs.mysql_table

        if args.prompt:
            # Execute the first turn if a prompt was provided
            print("\n--- DBA Assistant: Thinking... ---")
            if streaming_enabled:
                result, last_norm = handle_request(
                    initial_request,
                    approval_handler=approval_handler,
                    thread_id=thread_id,
                    event_handler=_print_cli_event,
                )
            else:
                result, last_norm = handle_request(
                    initial_request,
                    approval_handler=approval_handler,
                    thread_id=thread_id,
                )
            print(f"\n{result}")
            _update_state(last_norm)

        # Enter the Interactive REPL Loop
        print("\n--- Welcome to DBA Assistant Shell ---")
        print("--- (Ctrl+C or 'exit' to quit) ---")
        
        while True:
            try:
                user_input = input("\nDBA Assistant > ").strip()
                if not user_input or user_input.lower() in ("exit", "quit", "q"):
                    break
                
                # Merge current state into the new request
                follow_up = InterfaceRequest(
                    prompt=user_input,
                    config_path=args.config,
                    input_paths=current_input_paths,
                    mysql_host=current_mysql_host,
                    mysql_port=current_mysql_port,
                    mysql_user=current_mysql_user,
                    mysql_database=current_mysql_database,
                    mysql_table=current_mysql_table,
                    mysql_password=args.mysql_password, # Always use initial/env password
                    profile=args.profile,
                    report_format=args.report_format,
                    output_path=args.output,
                )
                
                print("\n--- Thinking... ---")
                if streaming_enabled:
                    result, last_norm = handle_request(
                        follow_up,
                        approval_handler=approval_handler,
                        thread_id=thread_id,
                        event_handler=_print_cli_event,
                    )
                else:
                    result, last_norm = handle_request(
                        follow_up,
                        approval_handler=approval_handler,
                        thread_id=thread_id,
                    )
                print(f"\n{result}")
                _update_state(last_norm)
                
            except KeyboardInterrupt:
                print("\nExiting interactive mode.")
                break
            except Exception as exc:
                print(f"\nError: {exc}")

        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _config_cli_streaming_enabled(config_path: str | None) -> bool:
    try:
        config = load_app_config(config_path)
    except Exception:
        return False
    return bool(getattr(config.runtime, "cli_streaming", False))


def _print_cli_event(event: dict[str, object]) -> None:
    event_type = str(event.get("type") or "")
    tool_name = str(event.get("tool_name") or "")
    if event_type == "tool_start" and tool_name:
        print(f"[tool:start] {tool_name}", flush=True)
    elif event_type == "tool_phase" and tool_name:
        phase = str(event.get("phase") or "")
        if phase:
            print(f"[tool:phase] {tool_name}: {phase}", flush=True)
    elif event_type == "tool_end" and tool_name:
        print(f"[tool:end] {tool_name}", flush=True)
    elif event_type == "tool_error" and tool_name:
        print(f"[tool:error] {tool_name}: {event.get('error')}", flush=True)


if __name__ == "__main__":
    import sys
    sys.exit(main())

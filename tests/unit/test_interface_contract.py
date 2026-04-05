"""Tests for input_kind/path_mode in the interface contract (WI-2)."""
from pathlib import Path

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.interface.types import InterfaceRequest


def test_interface_request_carries_input_kind_and_path_mode() -> None:
    request = InterfaceRequest(
        prompt="analyze rdb",
        input_kind="precomputed",
        path_mode="preparsed_dataset_analysis",
    )

    assert request.input_kind == "precomputed"
    assert request.path_mode == "preparsed_dataset_analysis"


def test_interface_request_defaults_to_none() -> None:
    request = InterfaceRequest(prompt="analyze rdb")

    assert request.input_kind is None
    assert request.path_mode is None


def test_interface_request_carries_mysql_fields() -> None:
    request = InterfaceRequest(
        prompt="analyze rdb",
        mysql_host="db.example",
        mysql_port=3307,
        mysql_user="analyst",
        mysql_database="analysis_db",
        mysql_password="secret",
        mysql_table="preparsed_keys",
        mysql_query="SELECT * FROM preparsed_keys",
    )

    assert request.mysql_host == "db.example"
    assert request.mysql_port == 3307
    assert request.mysql_user == "analyst"
    assert request.mysql_database == "analysis_db"
    assert request.mysql_password == "secret"
    assert request.mysql_table == "preparsed_keys"
    assert request.mysql_query == "SELECT * FROM preparsed_keys"


def test_interface_request_carries_ssh_fields() -> None:
    request = InterfaceRequest(
        prompt="analyze remote redis",
        redis_password="redis-secret",
        ssh_host="ssh.example",
        ssh_port=2222,
        ssh_username="root",
        ssh_password="secret",
        remote_rdb_path="/custom/override.rdb",
        remote_rdb_path_source="user_override",
        require_fresh_rdb_snapshot=True,
    )

    assert request.redis_password == "redis-secret"
    assert request.ssh_host == "ssh.example"
    assert request.ssh_port == 2222
    assert request.ssh_username == "root"
    assert request.ssh_password == "secret"
    assert request.remote_rdb_path == "/custom/override.rdb"
    assert request.remote_rdb_path_source == "user_override"
    assert request.require_fresh_rdb_snapshot is True


def test_interface_request_mysql_defaults_to_none() -> None:
    request = InterfaceRequest(prompt="analyze rdb")

    assert request.redis_password is None
    assert request.mysql_host is None
    assert request.mysql_port is None
    assert request.mysql_user is None
    assert request.mysql_database is None
    assert request.mysql_password is None
    assert request.mysql_table is None
    assert request.mysql_query is None
    assert request.ssh_host is None
    assert request.ssh_port is None
    assert request.ssh_username is None
    assert request.ssh_password is None


def test_runtime_inputs_carries_input_kind_and_path_mode() -> None:
    ri = RuntimeInputs(
        input_kind="local_rdb",
        path_mode="direct_rdb_analysis",
    )

    assert ri.input_kind == "local_rdb"
    assert ri.path_mode == "direct_rdb_analysis"


def test_runtime_inputs_defaults_to_none() -> None:
    ri = RuntimeInputs()

    assert ri.input_kind is None
    assert ri.path_mode is None


def test_runtime_inputs_carries_mysql_fields() -> None:
    ri = RuntimeInputs(
        mysql_host="db.example",
        mysql_port=3307,
        mysql_user="analyst",
        mysql_database="analysis_db",
        mysql_table="preparsed_keys",
        mysql_query="SELECT * FROM preparsed_keys",
    )

    assert ri.mysql_host == "db.example"
    assert ri.mysql_port == 3307
    assert ri.mysql_user == "analyst"
    assert ri.mysql_database == "analysis_db"
    assert ri.mysql_table == "preparsed_keys"
    assert ri.mysql_query == "SELECT * FROM preparsed_keys"


def test_runtime_inputs_carries_ssh_fields() -> None:
    ri = RuntimeInputs(
        ssh_host="ssh.example",
        ssh_port=2222,
        ssh_username="root",
        remote_rdb_path="/custom/override.rdb",
        remote_rdb_path_source="user_override",
        require_fresh_rdb_snapshot=True,
    )

    assert ri.ssh_host == "ssh.example"
    assert ri.ssh_port == 2222
    assert ri.ssh_username == "root"
    assert ri.remote_rdb_path == "/custom/override.rdb"
    assert ri.remote_rdb_path_source == "user_override"
    assert ri.require_fresh_rdb_snapshot is True


def test_secrets_carry_ssh_password() -> None:
    secrets = Secrets(ssh_password="secret")

    assert secrets.ssh_password == "secret"


def test_secrets_carry_redis_password() -> None:
    secrets = Secrets(redis_password="redis-secret")

    assert secrets.redis_password == "redis-secret"

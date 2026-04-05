import pytest

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import (
    RemoteRedisDiscoveryError,
    discover_remote_rdb,
)


class FakeRedisAdaptor:
    def __init__(
        self,
        *,
        ping_result=None,
        info_result=None,
        dir_result=None,
        dbfilename_result=None,
    ) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self._ping_result = ping_result if ping_result is not None else {"ok": True}
        self._info_result = (
            info_result
            if info_result is not None
            else {"rdb_last_save_time": 1710000000, "rdb_bgsave_in_progress": 0}
        )
        self._dir_result = (
            dir_result
            if dir_result is not None
            else {"available": True, "pattern": "dir", "data": {"dir": "/data/redis"}}
        )
        self._dbfilename_result = (
            dbfilename_result
            if dbfilename_result is not None
            else {
                "available": True,
                "pattern": "dbfilename",
                "data": {"dbfilename": "dump.rdb"},
            }
        )

    def ping(self, connection: RedisConnectionConfig) -> dict[str, object]:
        self.calls.append(("ping", None))
        return self._ping_result

    def info(self, connection: RedisConnectionConfig, *, section: str | None = None) -> dict[str, object]:
        self.calls.append(("info", section))
        return self._info_result

    def config_get(self, connection: RedisConnectionConfig, *, pattern: str) -> dict[str, object]:
        self.calls.append(("config_get", pattern))
        if pattern == "dir":
            return self._dir_result
        if pattern == "dbfilename":
            return self._dbfilename_result
        raise AssertionError(f"unexpected pattern: {pattern}")


def test_discover_remote_rdb_reports_path_and_source() -> None:
    adaptor = FakeRedisAdaptor()
    connection = RedisConnectionConfig(host="redis.example", port=6379)

    discovery = discover_remote_rdb(adaptor, connection)

    assert discovery == {
        "lastsave": 1710000000,
        "bgsave_in_progress": 0,
        "redis_dir": "/data/redis",
        "dbfilename": "dump.rdb",
        "rdb_path": "/data/redis/dump.rdb",
        "rdb_path_source": "discovered",
        "requires_confirmation": True,
    }
    assert adaptor.calls == [
        ("ping", None),
        ("info", "persistence"),
        ("config_get", "dir"),
        ("config_get", "dbfilename"),
    ]


def test_discover_remote_rdb_reports_ping_preflight_failure() -> None:
    adaptor = FakeRedisAdaptor(
        ping_result={
            "available": False,
            "error": {
                "kind": "authentication_failed",
                "message": "invalid username-password pair or user is disabled",
            },
        }
    )

    with pytest.raises(RemoteRedisDiscoveryError) as excinfo:
        discover_remote_rdb(adaptor, RedisConnectionConfig(host="redis.example"))

    error = excinfo.value
    assert error.kind == "authentication_failed"
    assert error.stage == "ping"
    assert "preflight failed at ping" in str(error)
    assert "invalid username-password pair" in str(error)
    assert "missing dir" not in str(error).lower()
    assert adaptor.calls == [("ping", None)]


def test_discover_remote_rdb_reports_permission_denied_for_config_dir() -> None:
    adaptor = FakeRedisAdaptor(
        dir_result={
            "available": False,
            "pattern": "dir",
            "error": {
                "kind": "permission_denied",
                "message": "NOPERM this user has no permissions to run the 'config|get' command",
            },
        }
    )

    with pytest.raises(RemoteRedisDiscoveryError) as excinfo:
        discover_remote_rdb(adaptor, RedisConnectionConfig(host="redis.example"))

    error = excinfo.value
    assert error.kind == "permission_denied"
    assert error.stage == "config_get(dir)"
    assert "preflight failed at config_get(dir)" in str(error)
    assert "permission_denied" in str(error)
    assert "config get dir" in str(error).lower()
    assert "missing dir" not in str(error).lower()


def test_discover_remote_rdb_reports_dbfilename_fetch_failure_reason() -> None:
    adaptor = FakeRedisAdaptor(
        dbfilename_result={
            "available": False,
            "pattern": "dbfilename",
            "error": {
                "kind": "timeout",
                "message": "timed out while waiting for response",
            },
        }
    )

    with pytest.raises(RemoteRedisDiscoveryError) as excinfo:
        discover_remote_rdb(adaptor, RedisConnectionConfig(host="redis.example"))

    error = excinfo.value
    assert error.kind == "timeout"
    assert error.stage == "config_get(dbfilename)"
    assert "preflight failed at config_get(dbfilename)" in str(error)
    assert "timed out while waiting for response" in str(error)
    assert "missing dbfilename" not in str(error).lower()


def test_discover_remote_rdb_only_reports_missing_field_when_response_shape_is_valid() -> None:
    adaptor = FakeRedisAdaptor(
        dir_result={"available": True, "pattern": "dir", "data": {}}
    )

    with pytest.raises(RemoteRedisDiscoveryError) as excinfo:
        discover_remote_rdb(adaptor, RedisConnectionConfig(host="redis.example"))

    error = excinfo.value
    assert error.kind == "missing_dir"
    assert error.stage == "config_get(dir)"
    assert "missing dir" in str(error).lower()


def test_discover_remote_rdb_reports_malformed_response_for_invalid_payload_shape() -> None:
    adaptor = FakeRedisAdaptor(
        dbfilename_result={"available": True, "pattern": "dbfilename", "data": ["dump.rdb"]}
    )

    with pytest.raises(RemoteRedisDiscoveryError) as excinfo:
        discover_remote_rdb(adaptor, RedisConnectionConfig(host="redis.example"))

    error = excinfo.value
    assert error.kind == "malformed_response"
    assert error.stage == "config_get(dbfilename)"
    assert "unexpected payload" in str(error).lower()

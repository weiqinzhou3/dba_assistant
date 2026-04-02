import pytest
from redis.exceptions import AuthenticationError, ConnectionError, ResponseError

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


class FakeRedisClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False

    def ping(self) -> bool:
        return True

    def info(self, section=None):
        return {"role": "master", "section": section}

    def config_get(self, pattern: str):
        return {"maxmemory": "0"}

    def slowlog_get(self, length: int):
        return [
            {
                "id": 1,
                "duration": 99,
                "command": "SET sensitive:key secret",
                "client_address": "127.0.0.1:5000",
            }
        ]

    def client_list(self):
        return [{"addr": "127.0.0.1:5000"}]

    def close(self) -> None:
        self.closed = True


class RestrictedRedisClient(FakeRedisClient):
    def config_get(self, pattern: str):
        raise ResponseError("NOPERM this user has no permissions to run the 'config|get' command")

    def slowlog_get(self, length: int):
        raise ResponseError("unknown command 'SLOWLOG', with args beginning with: 'GET'")

    def client_list(self):
        raise PermissionError("permission denied for CLIENT LIST")


class AuthFailingRedisClient(FakeRedisClient):
    def ping(self) -> bool:
        raise AuthenticationError("invalid username-password pair or user is disabled")

    def info(self, section=None):
        raise AuthenticationError("invalid username-password pair or user is disabled")

    def config_get(self, pattern: str):
        raise AuthenticationError("invalid username-password pair or user is disabled")

    def slowlog_get(self, length: int):
        raise AuthenticationError("invalid username-password pair or user is disabled")

    def client_list(self):
        raise AuthenticationError("invalid username-password pair or user is disabled")


class ConnectionFailingRedisClient(FakeRedisClient):
    def ping(self) -> bool:
        raise ConnectionError("connection lost")

    def info(self, section=None):
        raise ConnectionError("connection lost")

    def config_get(self, pattern: str):
        raise ConnectionError("connection lost")

    def slowlog_get(self, length: int):
        raise ConnectionError("connection lost")

    def client_list(self):
        raise ConnectionError("connection lost")


def test_redis_adaptor_wraps_read_only_commands() -> None:
    adaptor = RedisAdaptor(client_factory=FakeRedisClient)
    connection = RedisConnectionConfig(host="redis.example", port=6380, password="secret")

    assert adaptor.ping(connection) == {"ok": True}
    assert adaptor.info(connection, section="server")["role"] == "master"
    assert adaptor.config_get(connection, pattern="maxmemory*") == {
        "available": True,
        "pattern": "maxmemory*",
        "data": {"maxmemory": "0"},
    }
    assert adaptor.slowlog_get(connection, length=5) == {
        "available": True,
        "requested_length": 5,
        "count": 1,
        "entries": [{"id": 1, "duration": 99, "command": "SET"}],
    }
    assert adaptor.client_list(connection) == {"available": True, "count": 1}


def test_redis_adaptor_reports_unavailable_admin_probes() -> None:
    adaptor = RedisAdaptor(client_factory=RestrictedRedisClient)
    connection = RedisConnectionConfig(host="redis.example")

    config = adaptor.config_get(connection, pattern="maxmemory*")
    slowlog = adaptor.slowlog_get(connection, length=5)
    clients = adaptor.client_list(connection)

    assert config["available"] is False
    assert config["error"]["kind"] == "permission_denied"
    assert config["pattern"] == "maxmemory*"

    assert slowlog["available"] is False
    assert slowlog["error"]["kind"] == "command_unavailable"
    assert slowlog["requested_length"] == 5

    assert clients["available"] is False
    assert clients["error"]["kind"] == "permission_denied"


def test_redis_adaptor_normalizes_auth_and_connection_failures() -> None:
    auth_adaptor = RedisAdaptor(client_factory=AuthFailingRedisClient)
    connection_adaptor = RedisAdaptor(client_factory=ConnectionFailingRedisClient)
    connection = RedisConnectionConfig(host="redis.example")

    assert auth_adaptor.config_get(connection, pattern="maxmemory*") == {
        "available": False,
        "pattern": "maxmemory*",
        "error": {
            "kind": "authentication_failed",
            "message": "invalid username-password pair or user is disabled",
        },
    }
    assert auth_adaptor.slowlog_get(connection, length=5) == {
        "available": False,
        "requested_length": 5,
        "error": {
            "kind": "authentication_failed",
            "message": "invalid username-password pair or user is disabled",
        },
    }
    assert auth_adaptor.client_list(connection) == {
        "available": False,
        "error": {
            "kind": "authentication_failed",
            "message": "invalid username-password pair or user is disabled",
        },
    }

    assert connection_adaptor.config_get(connection, pattern="maxmemory*") == {
        "available": False,
        "pattern": "maxmemory*",
        "error": {"kind": "connection_failed", "message": "connection lost"},
    }
    assert connection_adaptor.slowlog_get(connection, length=5) == {
        "available": False,
        "requested_length": 5,
        "error": {"kind": "connection_failed", "message": "connection lost"},
    }
    assert connection_adaptor.client_list(connection) == {
        "available": False,
        "error": {"kind": "connection_failed", "message": "connection lost"},
    }


def test_redis_adaptor_wraps_ping_and_info_failures() -> None:
    auth_adaptor = RedisAdaptor(client_factory=AuthFailingRedisClient)
    connection_adaptor = RedisAdaptor(client_factory=ConnectionFailingRedisClient)
    connection = RedisConnectionConfig(host="redis.example")

    assert auth_adaptor.ping(connection) == {
        "available": False,
        "error": {
            "kind": "authentication_failed",
            "message": "invalid username-password pair or user is disabled",
        },
    }
    assert auth_adaptor.info(connection, section="server") == {
        "available": False,
        "error": {
            "kind": "authentication_failed",
            "message": "invalid username-password pair or user is disabled",
        },
    }

    assert connection_adaptor.ping(connection) == {
        "available": False,
        "error": {"kind": "connection_failed", "message": "connection lost"},
    }
    assert connection_adaptor.info(connection, section="server") == {
        "available": False,
        "error": {"kind": "connection_failed", "message": "connection lost"},
    }


@pytest.mark.parametrize("pattern", ["*", "requirepass", "clients*"])
def test_redis_adaptor_rejects_unknown_config_patterns(pattern: str) -> None:
    adaptor = RedisAdaptor(client_factory=FakeRedisClient)

    with pytest.raises(ValueError, match="config pattern"):
        adaptor.config_get(RedisConnectionConfig(host="redis.example"), pattern=pattern)


@pytest.mark.parametrize("length", [0, -1, 6, 99])
def test_redis_adaptor_rejects_invalid_slowlog_lengths(length: int) -> None:
    adaptor = RedisAdaptor(client_factory=FakeRedisClient)

    with pytest.raises(ValueError, match="slowlog length"):
        adaptor.slowlog_get(RedisConnectionConfig(host="redis.example"), length=length)

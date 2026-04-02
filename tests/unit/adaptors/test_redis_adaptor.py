from redis.exceptions import ResponseError

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

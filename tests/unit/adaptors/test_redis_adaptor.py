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
        return {"maxmemory": "0", "pattern": pattern}

    def slowlog_get(self, length: int):
        return [{"id": 1, "duration": 99, "length": length}]

    def client_list(self):
        return [{"addr": "127.0.0.1:5000"}]

    def close(self) -> None:
        self.closed = True


def test_redis_adaptor_wraps_read_only_commands() -> None:
    adaptor = RedisAdaptor(client_factory=FakeRedisClient)
    connection = RedisConnectionConfig(host="redis.example", port=6380, password="secret")

    assert adaptor.ping(connection) == {"ok": True}
    assert adaptor.info(connection, section="server")["role"] == "master"
    assert adaptor.config_get(connection, pattern="max*")["pattern"] == "max*"
    assert adaptor.slowlog_get(connection, length=5)[0]["length"] == 5
    assert adaptor.client_list(connection)[0]["addr"] == "127.0.0.1:5000"

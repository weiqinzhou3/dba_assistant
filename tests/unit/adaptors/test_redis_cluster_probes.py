from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


class FakeRedisClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False

    def execute_command(self, *parts):
        if parts == ("CLUSTER", "INFO"):
            return "cluster_state:ok\r\ncluster_known_nodes:3\r\n"
        if parts == ("CLUSTER", "NODES"):
            return (
                "07c37dfeb2352e0b7f3 10.0.0.1:6379@16379 master - 0 0 1 connected 0-5460\n"
                "2c9f9cfa10d1a2b3c4d 10.0.0.2:6379@16379 slave 07c37dfeb2352e0b7f3 0 0 2 connected\n"
            )
        raise AssertionError(parts)

    def close(self) -> None:
        self.closed = True


def test_redis_adaptor_collects_cluster_info_and_nodes_as_structured_read_only_probes() -> None:
    clients: list[FakeRedisClient] = []

    def factory(**kwargs):
        client = FakeRedisClient(**kwargs)
        clients.append(client)
        return client

    adaptor = RedisAdaptor(client_factory=factory)
    connection = RedisConnectionConfig(host="10.0.0.1", port=6379)

    cluster_info = adaptor.cluster_info(connection)
    cluster_nodes = adaptor.cluster_nodes(connection)

    assert cluster_info == {
        "available": True,
        "data": {"cluster_state": "ok", "cluster_known_nodes": "3"},
    }
    assert cluster_nodes["available"] is True
    assert cluster_nodes["count"] == 2
    assert cluster_nodes["nodes"][0]["role"] == "master"
    assert cluster_nodes["nodes"][1]["ip"] == "10.0.0.2"
    assert cluster_nodes["nodes"][1]["master_id"] == "07c37dfeb2352e0b7f3"
    assert all(client.closed for client in clients)

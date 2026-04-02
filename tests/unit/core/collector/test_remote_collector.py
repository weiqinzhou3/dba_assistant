import pytest

from dba_assistant.core.collector.remote_collector import RemoteCollector


class EchoRemoteCollector(RemoteCollector[str, str]):
    def collect_readonly(self, collector_input: str) -> str:
        return collector_input.upper()


def test_remote_collector_enforces_readonly_mode() -> None:
    with pytest.raises(ValueError, match="read-only"):
        EchoRemoteCollector(readonly=False)


def test_remote_collector_uses_collect_readonly() -> None:
    collector = EchoRemoteCollector()

    assert collector.collect("redis") == "REDIS"

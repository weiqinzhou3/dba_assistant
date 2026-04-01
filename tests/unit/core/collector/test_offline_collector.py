from pathlib import Path

import pytest

from dba_assistant.core.collector.offline_collector import OfflineCollector
from dba_assistant.core.collector.types import CollectedFile, OfflineCollectorInput


class EchoCollector(OfflineCollector[dict[str, str]]):
    def transform(
        self,
        collector_input: OfflineCollectorInput,
        files: list[CollectedFile],
    ) -> dict[str, str]:
        return {str(item.relative_path): item.text for item in files}


def test_offline_collector_reads_a_single_file(tmp_path: Path) -> None:
    source = tmp_path / "info.txt"
    source.write_text("role:master\n", encoding="utf-8")

    result = EchoCollector().collect(OfflineCollectorInput(source=source))

    assert result == {"info.txt": "role:master\n"}


def test_offline_collector_reads_directory_with_suffix_filter(tmp_path: Path) -> None:
    root = tmp_path / "inspection"
    root.mkdir()
    (root / "info.txt").write_text("used_memory:42\n", encoding="utf-8")
    (root / "notes.log").write_text("skip me\n", encoding="utf-8")

    result = EchoCollector().collect(
        OfflineCollectorInput(
            source=root,
            recursive=False,
            allowed_suffixes=(".txt",),
        )
    )

    assert result == {"info.txt": "used_memory:42\n"}


def test_offline_collector_rejects_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        EchoCollector().collect(OfflineCollectorInput(source=missing))

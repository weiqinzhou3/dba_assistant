"""Offline collector base for Phase 1 file-based inputs."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

from dba_assistant.core.collector.types import CollectedFile, ICollector, OfflineCollectorInput


TOutput = TypeVar("TOutput")


class OfflineCollector(ICollector[OfflineCollectorInput, TOutput], Generic[TOutput]):
    def collect(self, collector_input: OfflineCollectorInput) -> TOutput:
        source = collector_input.source
        if not source.exists():
            raise FileNotFoundError(f"Offline collection source does not exist: {source}")

        files = self._read_files(collector_input)
        return self.transform(collector_input, files)

    def _read_files(self, collector_input: OfflineCollectorInput) -> list[CollectedFile]:
        source = collector_input.source
        if source.is_file():
            return [self._read_file(source, source.parent, collector_input)]

        pattern = "**/*" if collector_input.recursive else "*"
        collected: list[CollectedFile] = []
        for path in sorted(item for item in source.glob(pattern) if item.is_file()):
            if collector_input.allowed_suffixes and path.suffix not in collector_input.allowed_suffixes:
                continue
            collected.append(self._read_file(path, source, collector_input))
        return collected

    def _read_file(
        self,
        path: Path,
        root: Path,
        collector_input: OfflineCollectorInput,
    ) -> CollectedFile:
        text = path.read_text(encoding=collector_input.encoding)
        relative_path = path.relative_to(root) if path.parent != root else Path(path.name)
        return CollectedFile(path=path, relative_path=relative_path, text=text)

    @abstractmethod
    def transform(
        self,
        collector_input: OfflineCollectorInput,
        files: list[CollectedFile],
    ) -> TOutput:
        raise NotImplementedError

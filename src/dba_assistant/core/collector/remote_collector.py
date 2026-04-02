"""Read-only remote collector base for Phase 2."""

from __future__ import annotations

from abc import abstractmethod
from typing import TypeVar

from dba_assistant.core.collector.types import ICollector


TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class RemoteCollector(ICollector[TInput, TOutput]):
    def __init__(self, *, readonly: bool = True) -> None:
        if not readonly:
            raise ValueError("Phase 2 remote collectors must remain read-only.")
        self.readonly = readonly

    def collect(self, collector_input: TInput) -> TOutput:
        return self.collect_readonly(collector_input)

    @abstractmethod
    def collect_readonly(self, collector_input: TInput) -> TOutput:
        raise NotImplementedError

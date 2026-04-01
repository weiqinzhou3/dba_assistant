"""Shared collector contracts for Phase 1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar


TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class ICollector(ABC, Generic[TInput, TOutput]):
    @abstractmethod
    def collect(self, collector_input: TInput) -> TOutput:
        raise NotImplementedError


@dataclass(frozen=True)
class OfflineCollectorInput:
    source: Path
    recursive: bool = False
    allowed_suffixes: tuple[str, ...] = ()
    encoding: str = "utf-8"


@dataclass(frozen=True)
class CollectedFile:
    path: Path
    relative_path: Path
    text: str

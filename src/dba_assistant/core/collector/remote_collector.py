"""Interface-only remote collector base for later phases."""

from __future__ import annotations

from typing import Generic, TypeVar

from dba_assistant.core.collector.types import ICollector


TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class RemoteCollector(ICollector[TInput, TOutput], Generic[TInput, TOutput]):
    """Phase 1 placeholder for future remote collectors."""

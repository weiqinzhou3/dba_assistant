"""Shared reporter contracts for Phase 1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Generic, TypeVar


class OutputMode(str, Enum):
    REPORT = "report"
    SUMMARY = "summary"


class ReportFormat(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"
    SUMMARY = "summary"


@dataclass(frozen=True)
class ReportOutputConfig:
    output_path: Path | None = None
    mode: OutputMode = OutputMode.REPORT
    format: ReportFormat = ReportFormat.DOCX
    template_name: str | None = None
    language: str = "zh-CN"


@dataclass(frozen=True)
class ReportArtifact:
    format: ReportFormat
    output_path: Path | None
    content: str | None = None


TAnalysis = TypeVar("TAnalysis")


class IReporter(ABC, Generic[TAnalysis]):
    @abstractmethod
    def render(self, analysis: TAnalysis, config: ReportOutputConfig) -> ReportArtifact:
        raise NotImplementedError

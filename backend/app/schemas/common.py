from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field


class SummaryItem(BaseModel):
    label: str
    value: Any


class ChineseSummary(BaseModel):
    title: str
    status: str = "unknown"
    risk_level: str = "low"
    execution_enabled: bool = False
    items: list[SummaryItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ChineseTable(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ChineseResult(BaseModel):
    summary: ChineseSummary
    table: ChineseTable
    artifact_path: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)

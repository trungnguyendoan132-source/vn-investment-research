from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
import math
from zoneinfo import ZoneInfo
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Mode(str, Enum):
    DEMO = "demo"
    SNAPSHOT = "snapshot"
    LIVE = "live"


class Source(StrictModel):
    id: str
    title: str = Field(max_length=400)
    url: str = Field(max_length=2000)
    kind: Literal["snapshot", "live", "synthetic", "user_supplied"]
    retrieved_at: datetime
    period: str | None = None
    sha256: str | None = None
    note: str = ""


class QualityIssue(StrictModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    component: str


class DatasetRefs(StrictModel):
    prices: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    macro: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    news: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ValuationAssumptions(StrictModel):
    target_pe: float | None = Field(default=None, gt=0, le=100)
    target_pb: float | None = Field(default=None, gt=0, le=20)
    shares_outstanding: float | None = Field(default=None, gt=0)
    shares_source: str | None = None

    @model_validator(mode="after")
    def validate_share_source(self):
        if self.shares_outstanding is not None and not self.shares_source:
            raise ValueError("Số cổ phiếu lưu hành phải đi kèm nguồn, không suy từ vốn điều lệ")
        return self


class AnalysisRequest(StrictModel):
    ticker: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9]{2,10}$")
    as_of: date = Field(default_factory=today)
    start_year: int = Field(default=2021, ge=2000, le=2100)
    end_year: int = Field(default=2025, ge=2000, le=2100)
    mode: Mode = Mode.SNAPSHOT
    risk_profile: Literal["conservative", "balanced", "growth"] = "balanced"
    horizon_months: int = Field(default=12, ge=1, le=60)
    sections: list[Literal["macro", "sector", "financial", "market", "news", "valuation"]] = Field(
        default_factory=lambda: ["macro", "sector", "financial", "market", "news", "valuation"]
    )
    news_limit: int = Field(default=5, ge=1, le=10)
    use_ai: bool = False
    use_jev: bool = False
    datasets: DatasetRefs = Field(default_factory=DatasetRefs)
    valuation: ValuationAssumptions = Field(default_factory=ValuationAssumptions)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value):
        return str(value).strip().upper()

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_year > self.end_year or self.end_year > self.as_of.year:
            raise ValueError("Khoảng năm không hợp lệ so với ngày chốt dữ liệu")
        if not self.sections or len(set(self.sections)) != len(self.sections):
            raise ValueError("Chọn ít nhất một mục; không lặp mục báo cáo")
        if self.as_of > today():
            raise ValueError("Ngày chốt dữ liệu không được nằm trong tương lai")
        return self


class Metric(StrictModel):
    key: str
    label: str
    value: float | None
    unit: Literal["VND", "ratio", "percent", "days", "shares"] = "ratio"
    formula: str
    source_ids: list[str] = Field(default_factory=list)
    note: str = ""


class FinancialYear(StrictModel):
    year: int
    facts: dict[str, float | None]
    metrics: list[Metric]
    source_ids: list[str]


class NewsArticle(StrictModel):
    title: str = Field(max_length=300)
    text: str = Field(max_length=100000)
    url: str
    published_at: date
    source_id: str
    ticker: str
    themes: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)


class Section(StrictModel):
    title: str
    status: Literal["ok", "partial", "unavailable"]
    summary: str
    rows: list[dict[str, str | float | int | None]] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Report(StrictModel):
    schema_version: str = "1.0.0"
    ticker: str
    company_name: str
    sector_name: str
    request: AnalysisRequest
    generated_at: datetime = Field(default_factory=utcnow)
    status: Literal["complete", "partial"]
    decision: str
    financial_years: list[FinancialYear]
    sections: dict[str, Section]
    news: list[NewsArticle]
    sources: list[Source]
    issues: list[QualityIssue]
    opportunities: list[str]
    risks: list[str]
    ai: dict = Field(default_factory=lambda: {"status": "disabled", "claims": [], "note": "AI chỉ bật khi người dùng yêu cầu và cấu hình khóa riêng."})
    jev: dict = Field(default_factory=lambda: {"status": "disabled", "note": "Jev chưa được yêu cầu."})

    @model_validator(mode="after")
    def source_links_resolve(self):
        ids = {source.id for source in self.sources}
        if len(ids) != len(self.sources):
            raise ValueError("Mã nguồn bằng chứng bị trùng")
        referenced = {sid for section in self.sections.values() for sid in section.source_ids}
        referenced.update(sid for year in self.financial_years for sid in year.source_ids)
        referenced.update(sid for year in self.financial_years for metric in year.metrics for sid in metric.source_ids)
        referenced.update(article.source_id for article in self.news)
        if not referenced.issubset(ids):
            raise ValueError("Báo cáo tham chiếu nguồn không tồn tại")
        return self


def finite(value) -> float | None:
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None

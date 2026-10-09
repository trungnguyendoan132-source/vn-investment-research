from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
import math
from zoneinfo import ZoneInfo
from typing import Literal
from urllib.parse import urlsplit

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
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    title: str = Field(min_length=1, max_length=400)
    url: str = Field(min_length=1, max_length=2000)
    kind: Literal["snapshot", "live", "synthetic", "user_supplied"]
    retrieved_at: datetime
    period: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    note: str = ""
    published_at: datetime | None = None
    published_on: date | None = None
    publication_precision: Literal["day", "timestamp", "unknown"] = "unknown"
    period_start: date | None = None
    period_end: date | None = None
    period_type: Literal["annual", "quarterly", "half_year", "ttm", "unknown"] = "unknown"
    report_basis: Literal["consolidated", "separate", "unknown"] = "unknown"
    unit: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, max_length=16)
    mapping_version: str | None = Field(default=None, max_length=80)
    dataset_version: str | None = Field(default=None, max_length=120)
    verification_status: Literal["unknown", "unverified", "verified", "quarantined", "synthetic", "provider_observed"] = "unknown"

    @model_validator(mode="after")
    def period_order(self):
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("Ngày đầu kỳ phải trước ngày cuối kỳ")
        if self.verification_status == "synthetic" and self.kind != "synthetic":
            raise ValueError("Nguồn synthetic phải được gắn kind synthetic")
        if self.kind == "synthetic" and self.verification_status in {"verified", "provider_observed"}:
            raise ValueError("Dữ liệu giả lập không được gắn nhãn xác minh nguồn thật")
        if self.publication_precision == "day" and self.published_on is None:
            raise ValueError("Độ chính xác ngày cần published_on")
        if self.publication_precision == "timestamp" and self.published_at is None:
            raise ValueError("Độ chính xác dấu thời gian cần published_at")
        return self

    @field_validator("url")
    @classmethod
    def valid_source_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
            return value
        if value.startswith("urn:") and len(value.split(":")) >= 3 and not any(c.isspace() for c in value):
            return value
        raise ValueError("Nguồn cần URL HTTP(S) hoặc URN có tên rõ ràng")

    @field_validator("retrieved_at", "published_at")
    @classmethod
    def aware_timestamp(cls, value):
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Dấu thời gian phải có múi giờ")
        return value


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
    mode: Mode = Mode.LIVE
    risk_profile: Literal["conservative", "balanced", "growth"] = "balanced"
    horizon_months: int = Field(default=12, ge=1, le=60)
    sections: list[Literal["macro", "sector", "financial", "market", "news", "valuation"]] = Field(
        default_factory=lambda: ["macro", "sector", "financial", "market", "news", "valuation"]
    )
    news_limit: int = Field(default=5, ge=1, le=10)
    use_ai: bool = True
    use_jev: bool = True
    datasets: DatasetRefs = Field(default_factory=DatasetRefs)
    valuation: ValuationAssumptions = Field(default_factory=ValuationAssumptions)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value):
        if not isinstance(value, str):
            raise ValueError("Mã cổ phiếu phải là chuỗi ký tự")
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_range(self):
        if self.mode == Mode.DEMO:
            if "use_ai" not in self.model_fields_set:
                self.use_ai = False
            if "use_jev" not in self.model_fields_set:
                self.use_jev = False
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
    year: int = Field(ge=1900, le=2100)
    facts: dict[str, float | None]
    metrics: list[Metric]
    source_ids: list[str]
    fact_metadata: dict[str, dict] = Field(default_factory=dict)
    quality_issues: list[QualityIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def metadata_keys_exist(self):
        if not set(self.fact_metadata).issubset(self.facts):
            raise ValueError("Metadata tham chiếu chỉ tiêu tài chính không tồn tại")
        return self


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
    schema_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
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
        if self.ticker != self.request.ticker:
            raise ValueError("Mã báo cáo khác mã yêu cầu")
        years = [year.year for year in self.financial_years]
        if len(years) != len(set(years)):
            raise ValueError("Báo cáo có kỳ tài chính trùng")
        ids = {source.id for source in self.sources}
        if len(ids) != len(self.sources):
            raise ValueError("Mã nguồn bằng chứng bị trùng")
        referenced = {sid for section in self.sections.values() for sid in section.source_ids}
        referenced.update(sid for year in self.financial_years for sid in year.source_ids)
        referenced.update(sid for year in self.financial_years for metric in year.metrics for sid in metric.source_ids)
        referenced.update(article.source_id for article in self.news)
        for year in self.financial_years:
            for metadata in year.fact_metadata.values():
                source_id, source_ids = metadata.get("source_id"), metadata.get("source_ids", [])
                if source_id is not None and not isinstance(source_id, str):
                    raise ValueError("source_id metadata phải là chuỗi")
                if not isinstance(source_ids, list) or any(not isinstance(sid, str) for sid in source_ids):
                    raise ValueError("source_ids metadata phải là danh sách chuỗi")
                if source_id:
                    referenced.add(source_id)
                referenced.update(source_ids)
        for claim in self.ai.get("claims", []):
            if (not isinstance(claim, dict) or not isinstance(claim.get("source_ids"), list) or
                    not claim["source_ids"] or any(not isinstance(sid, str) for sid in claim["source_ids"])):
                raise ValueError("AI claim không đúng contract")
            referenced.update(claim["source_ids"])
        for result in (self.ai, self.jev):
            if result.get("status") not in {"disabled", "unavailable", "error", "ok"}:
                raise ValueError("Trạng thái AI/Jev không hợp lệ")
        if any(article.ticker != self.ticker for article in self.news):
            raise ValueError("Tin tức khác mã báo cáo")
        if not referenced.issubset(ids):
            raise ValueError("Báo cáo tham chiếu nguồn không tồn tại")
        return self


def finite(value) -> float | None:
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None

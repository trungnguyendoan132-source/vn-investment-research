from datetime import date

import pandas as pd

from vnresearch.analysis.financial import financial_analysis
from vnresearch.analysis.quality import verified_financial_rows
from vnresearch.analysis.valuation import value_company
from vnresearch.domain.models import ValuationAssumptions


def observation(year, value, status="verified", basis="consolidated"):
    facts = {"revenue": value, "net_income": value / 10, "total_assets": value * 2,
             "equity": value, "eps": 10.0}
    metadata = {key: {"status": "usable", "verification_status": status, "report_basis": basis,
                      "period_type": "annual", "unit": "VND/share" if key == "eps" else "VND"}
                for key in facts}
    return {"year": year, "facts": facts, "fact_metadata": metadata, "source_ids": [str(year)]}


def test_unverified_values_remain_in_evidence_only():
    raw = [observation(2025, 100, "unverified")]
    safe = verified_financial_rows(raw)
    assert safe[0]["facts"]["eps"] is None
    assert safe[0]["fact_metadata"]["eps"]["observed_value"] == 10
    assert raw[0]["facts"]["eps"] == 10
    assert verified_financial_rows(raw, require_verified=False)[0]["facts"]["eps"] == 10


def test_ratios_do_not_mix_reporting_basis():
    rows = [observation(2024, 100, basis="separate"), observation(2025, 120)]
    calculated = financial_analysis(rows)[-1]
    metrics = {item.key: item.value for item in calculated.metrics}
    assert metrics["revenue_growth_yoy"] is None
    assert metrics["roe"] is None


def test_average_balance_metric_links_both_original_sources():
    result = financial_analysis([observation(2024, 100), observation(2025, 120)])[-1]
    assert next(item for item in result.metrics if item.key == "roe").source_ids == ["2024", "2025"]


def test_unknown_price_basis_cannot_create_valuation():
    year = financial_analysis([observation(2025, 100)])[-1]
    prices = pd.DataFrame([{"date": date(2026, 10, 8), "close": 100.0}])
    result = value_company(year, prices, ValuationAssumptions(target_pe=20), date(2026, 10, 9))
    assert result.status == "partial"
    assert next(row["Giá trị"] for row in result.rows if str(row["Chỉ tiêu"]).startswith("P/E")) is None
    assert not any("Giá kịch bản" in str(row["Chỉ tiêu"]) for row in result.rows)


def test_interim_observations_are_separate_from_annual_metrics(monkeypatch, tmp_path):
    from vnresearch.analysis.pipeline import analyze
    from vnresearch.domain.models import AnalysisRequest, Source, utcnow
    annual = observation(2025, 100)
    annual["source_ids"] = ["annual"]
    def source(sid):
        return Source(id=sid, title="Controlled fixture", url="https://example.test/filing", kind="user_supplied", retrieved_at=utcnow())
    monkeypatch.setattr("vnresearch.analysis.pipeline.company", lambda *a, **kw: {
        "name": "Controlled company", "industry": "Chứng khoán", "sector": "Dịch vụ tài chính"})
    monkeypatch.setattr("vnresearch.data.autoload.ensure_fixture_filings", lambda *a, **kw: {"status": "ready", "issues": []})
    interim = pd.DataFrame([{"period_end": "2026-06-30", "verification_status": "verified", "report_basis": "consolidated",
                             "published_on": "2026-08-14", "filing_id": "half-year-fixture", "metric_key": key,
                             "value": value, "source_id": "interim"}
                            for key, value in [("revenue", 60.0), ("net_income", 6.0), ("eps", 3.0)]])

    def load(*args, **kwargs):
        if kwargs.get("period_type") == "half_year":
            return interim, [source("interim")]
        return pd.DataFrame({"ticker": ["SSI"]}), [source("annual")]

    monkeypatch.setattr("vnresearch.analysis.pipeline.load_raw", load)
    monkeypatch.setattr("vnresearch.analysis.pipeline.extract_facts", lambda *a: [annual])
    report = analyze(AnalysisRequest(ticker="SSI", mode="snapshot", as_of=date(2026, 10, 9),
                                     sections=["financial"], use_ai=False, use_jev=False), filing_dir=tmp_path)
    assert [year.year for year in report.financial_years] == [2025]
    assert report.financial_years[0].facts["revenue"] == 100
    rows = report.sections["financial"].rows
    assert any(row["Giá trị"] == 60 and str(row["Chỉ tiêu"]).startswith("half_year") for row in rows)
    assert "interim" in report.sections["financial"].source_ids

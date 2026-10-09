from datetime import date

import pandas as pd
import pytest

from vnresearch.analysis.valuation import value_company
from vnresearch.domain.models import FinancialYear, ValuationAssumptions


def fake_year(year: int = 2024, eps: float = 5000.0, equity_parent: float = 1000000.0):
    return FinancialYear(
        year=year,
        facts={"eps": eps, "equity_parent": equity_parent},
        metrics=[],
        source_ids=["src-1"],
        fact_metadata={
            "eps": {"verification_status": "verified", "unit": "VND/share", "source_id": "src-1"},
            "equity_parent": {"verification_status": "verified", "unit": "VND", "source_id": "src-1"},
        },
    )


def fake_prices(close: float = 80000.0, as_of: date = date(2026, 10, 9)):
    prices = pd.DataFrame([{"date": as_of, "close": close, "ticker": "FPT"}])
    prices.attrs["price_basis"] = "raw"
    return prices


def test_valuation_bull_base_bear_scenarios():
    yr = fake_year(eps=5000.0)
    prices = fake_prices(close=80000.0)
    assumptions = ValuationAssumptions(target_pe=20.0)
    as_of = date(2026, 10, 9)

    sec = value_company(yr, prices, assumptions, as_of)
    assert sec.status == "ok"
    row_dict = {r["Chỉ tiêu"]: r["Giá trị"] for r in sec.rows}

    # Base price: 20 * 5000 = 100,000
    assert row_dict["Giá kịch bản P/E (VND)"] == 100000.0
    # Bull price: (20 * 1.15) * 5000 = 115,000
    assert row_dict["Kịch bản Khả quan (Bull +15% P/E) (VND)"] == 115000.0
    # Bear price: (20 * 0.85) * 5000 = 85,000
    assert row_dict["Kịch bản Thận trọng (Bear -15% P/E) (VND)"] == 85000.0
    # Sensitivity -10%: 18 * 5000 = 90,000
    assert row_dict["Độ nhạy P/E (-10%) (VND)"] == 90000.0
    # Sensitivity +10%: 22 * 5000 = 110,000
    assert row_dict["Độ nhạy P/E (+10%) (VND)"] == 110000.0
    assert "giả định minh họa trên bội số, không phải dự báo giá" in sec.summary
    assert sec.source_ids == ["market", "src-1"]


def test_valuation_sector_pe_benchmark():
    yr = fake_year(eps=4000.0)
    prices = fake_prices(close=60000.0)
    assumptions = ValuationAssumptions()
    as_of = date(2026, 10, 9)

    sec = value_company(yr, prices, assumptions, as_of, sector_pe=18.0)
    row_dict = {r["Chỉ tiêu"]: r["Giá trị"] for r in sec.rows}

    assert row_dict["P/E trung vị ngành tham chiếu"] == 18.0
    assert row_dict["Giá ngụ ý theo P/E trung vị ngành (VND)"] == 72000.0
    assert row_dict["Chênh lệch so với giá ngụ ý ngành"] == pytest.approx(0.2)
    assert "đầu vào do bên gọi cung cấp" in sec.summary


def test_quarantined_facts_block_scenarios_even_when_marked_verified():
    year = fake_year()
    for metadata in year.fact_metadata.values():
        metadata["status"] = "quarantined"
    section = value_company(year, fake_prices(), all_assumptions(), date(2026, 10, 9), sector_pe=18)
    assert_no_valuation(section)


def test_valuation_bank_specific_note():
    yr = fake_year(eps=3000.0)
    prices = fake_prices(close=30000.0)
    assumptions = ValuationAssumptions()
    as_of = date(2026, 10, 9)

    sec_bank = value_company(yr, prices, assumptions, as_of, is_bank=True)
    assert "Ngân hàng: P/B là phương pháp định giá chủ đạo" in sec_bank.summary

    sec_non_bank = value_company(yr, prices, assumptions, as_of, is_bank=False)
    assert "Ngân hàng: P/B là phương pháp định giá chủ đạo" not in sec_non_bank.summary


def all_assumptions():
    return ValuationAssumptions(target_pe=20, target_pb=2, shares_outstanding=100,
                               shares_source="Controlled share-count fixture")


def assert_no_valuation(section):
    rows = {row["Chỉ tiêu"]: row["Giá trị"] for row in section.rows}
    assert section.status == "partial"
    assert rows["P/E trên EPS năm 2024, không phải TTM"] is None
    assert rows["P/B"] is None
    assert not any(any(term in label for term in ("kịch bản", "Kịch bản", "Độ nhạy", "ngành"))
                   for label in rows)


@pytest.mark.parametrize("status", ["unverified", "unknown", "quarantined"])
def test_unverified_facts_block_all_scenarios_and_sector_reference(status):
    year = fake_year()
    for metadata in year.fact_metadata.values():
        metadata["verification_status"] = status
    result = value_company(year, fake_prices(), all_assumptions(), date(2026, 10, 9), sector_pe=18)
    assert_no_valuation(result)


@pytest.mark.parametrize("basis", [None, "unknown", "split_adjusted", "adjusted"])
def test_unknown_or_adjusted_price_blocks_all_scenarios_and_sector_reference(basis):
    prices = fake_prices()
    if basis is None:
        prices.attrs.clear()
    else:
        prices.attrs["price_basis"] = basis
    result = value_company(fake_year(), prices, all_assumptions(), date(2026, 10, 9), sector_pe=18)
    assert_no_valuation(result)


@pytest.mark.parametrize("price_date", [date(2026, 10, 1), date(2026, 10, 10), None, "bad-date"])
def test_stale_future_or_invalid_price_date_blocks_valuation(price_date):
    result = value_company(fake_year(), fake_prices(as_of=price_date), all_assumptions(),
                           date(2026, 10, 9), sector_pe=18)
    assert_no_valuation(result)


@pytest.mark.parametrize("price", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_nonfinite_or_nonpositive_price_is_missing_and_blocks_valuation(price):
    result = value_company(fake_year(), fake_prices(close=price), all_assumptions(),
                           date(2026, 10, 9), sector_pe=18)
    assert_no_valuation(result)
    assert result.rows[0]["Giá trị"] is None


@pytest.mark.parametrize("sector_pe", [float("nan"), float("inf"), float("-inf"), 0, -1, True, "bad"])
def test_invalid_sector_multiple_is_rejected_explicitly(sector_pe):
    with pytest.raises(ValueError, match="sector_pe"):
        value_company(fake_year(), fake_prices(), all_assumptions(), date(2026, 10, 9),
                      sector_pe=sector_pe)


def test_bank_pb_remains_valid_when_verified_eps_is_negative():
    result = value_company(fake_year(eps=-500), fake_prices(close=30000), all_assumptions(),
                           date(2026, 10, 9), True, 18)
    rows = {row["Chỉ tiêu"]: row["Giá trị"] for row in result.rows}
    assert result.status == "ok"
    assert rows["P/E trên EPS năm 2024, không phải TTM"] is None
    assert rows["P/B"] == 3
    assert rows["Giá kịch bản P/B (VND)"] == 20000
    assert rows["Kịch bản Khả quan (Bull +15% P/B) (VND)"] == 23000
    assert rows["Kịch bản Thận trọng (Bear -15% P/B) (VND)"] == 17000
    assert rows["Độ nhạy P/B (-10%) (VND)"] == 18000
    assert rows["Độ nhạy P/B (+10%) (VND)"] == 22000
    assert not any("ngành" in label or "kịch bản P/E" in label for label in rows)


def test_equity_verification_gate_does_not_disable_verified_eps():
    year = fake_year()
    year.fact_metadata["equity_parent"]["verification_status"] = "unverified"
    result = value_company(year, fake_prices(), all_assumptions(), date(2026, 10, 9), sector_pe=18)
    rows = {row["Chỉ tiêu"]: row["Giá trị"] for row in result.rows}
    assert rows["P/E trên EPS năm 2024, không phải TTM"] == 16
    assert rows["Giá kịch bản P/E (VND)"] == 100000
    assert rows["P/B"] is None
    assert "Giá kịch bản P/B (VND)" not in rows


def test_nonfinite_facts_are_not_used_after_model_mutation():
    year = fake_year()
    year.facts.update(eps=float("inf"), equity_parent=float("nan"))
    result = value_company(year, fake_prices(), all_assumptions(), date(2026, 10, 9), sector_pe=18)
    assert_no_valuation(result)


def test_arithmetic_overflow_does_not_emit_infinite_scenario_prices():
    result = value_company(fake_year(eps=1e308), fake_prices(), ValuationAssumptions(target_pe=20),
                           date(2026, 10, 9), sector_pe=18)
    assert result.status == "partial"
    assert not any("kịch bản" in str(row["Chỉ tiêu"]) or "ngành" in str(row["Chỉ tiêu"])
                   for row in result.rows)
    assert "Kết quả tính không hữu hạn" in result.summary


def test_explicit_demo_opt_out_retains_scenarios_with_synthetic_price_basis():
    year = fake_year()
    year.fact_metadata.clear()
    prices = fake_prices()
    prices.attrs["price_basis"] = "synthetic"
    result = value_company(year, prices, all_assumptions(), date(2026, 10, 9), require_verified=False)
    assert result.status == "ok"
    assert any(row["Chỉ tiêu"] == "Giá kịch bản P/E (VND)" for row in result.rows)

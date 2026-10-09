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
    )


def fake_prices(close: float = 80000.0, as_of: date = date(2026, 10, 9)):
    return pd.DataFrame([{"date": as_of, "close": close, "ticker": "FPT"}])


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


def test_valuation_bank_specific_note():
    yr = fake_year(eps=3000.0)
    prices = fake_prices(close=30000.0)
    assumptions = ValuationAssumptions()
    as_of = date(2026, 10, 9)

    sec_bank = value_company(yr, prices, assumptions, as_of, is_bank=True)
    assert "Ngân hàng: P/B là phương pháp định giá chủ đạo" in sec_bank.summary

    sec_non_bank = value_company(yr, prices, assumptions, as_of, is_bank=False)
    assert "Ngân hàng: P/B là phương pháp định giá chủ đạo" not in sec_non_bank.summary

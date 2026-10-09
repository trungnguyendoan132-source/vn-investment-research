from vnresearch.analysis.financial import financial_analysis


def annual(year, **facts):
    return {"year": year, "facts": facts, "source_ids": []}


def metrics(rows, bank=False):
    return {metric.key: metric.value for metric in financial_analysis(rows, is_bank=bank)[-1].metrics}


def test_current_ratio_uses_current_items():
    result = metrics([annual(2024, total_assets=1000, total_liabilities=500, current_assets=300, current_liabilities=100)])
    assert result["current_ratio"] == 3


def test_yoy_requires_adjacent_year():
    result = metrics([annual(2022, revenue=100), annual(2024, revenue=121)])
    assert result["revenue_growth_yoy"] is None


def test_yoy_zero_and_true_adjacent():
    assert metrics([annual(2023, revenue=100), annual(2024, revenue=121)])["revenue_growth_yoy"] == 0.21
    assert metrics([annual(2023, revenue=0), annual(2024, revenue=121)])["revenue_growth_yoy"] is None


def test_missing_capex_does_not_become_zero():
    assert metrics([annual(2024, cfo=30, capex=None)])["fcf"] is None
    assert metrics([annual(2024, cfo=30, capex=0)])["fcf"] == 30


def test_ebit_is_not_ebitda():
    assert metrics([annual(2024, ebit=10, revenue=100)])["ebitda_margin"] is None


def test_roa_roe_use_average_balance():
    result = metrics([annual(2023, total_assets=100, equity=50), annual(2024, total_assets=300, equity=150, net_income=20)])
    assert result["roa"] == 0.1
    assert result["roe"] == 0.2


def test_banks_do_not_receive_manufacturing_liquidity_ratio():
    result = metrics([annual(2024, current_assets=300, current_liabilities=100)], bank=True)
    assert "current_ratio" not in result

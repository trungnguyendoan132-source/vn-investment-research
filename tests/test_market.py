from datetime import date

import pandas as pd
import pytest

from vnresearch.data.market import normalize_prices


def prices():
    return pd.DataFrame([{"ticker": "FPT", "date": "2026-10-08", "open": 99, "high": 105, "low": 95,
                          "close": 100, "volume": 10, "price_unit": "thousand_VND", "source_url": "https://example.org/prices"}])


def test_units_are_explicit_and_no_future_prices():
    frame = normalize_prices(prices(), "FPT", date(2026, 10, 9))
    assert frame.iloc[0].close == 100000
    assert normalize_prices(prices(), "FPT", date(2026, 10, 7)).empty


@pytest.mark.parametrize("column,value", [("price_unit", "auto"), ("high", 90), ("volume", -1), ("close", float("inf"))])
def test_bad_market_data_fails(column, value):
    frame = prices()
    frame[column] = value
    with pytest.raises(ValueError):
        normalize_prices(frame, "FPT", date(2026, 10, 9))


def test_duplicate_trading_date_rejected():
    with pytest.raises(ValueError):
        normalize_prices(pd.concat([prices(), prices()]), "FPT", date(2026, 10, 9))

"""All provider responses here are mocks. These tests never call KBS."""

from datetime import date
import hashlib
import json

import pandas as pd
import pytest
import requests

from vnresearch.data import providers
from vnresearch.data.market import apply_corporate_actions, load_prices, normalize_prices
from vnresearch.data.providers import MarketConfig, fetch_prices
from vnresearch.domain.models import Mode


AS_OF = date(2026, 10, 9)


def prices(**changes):
    row = {"ticker": "AAA", "date": "2026-10-08", "open": 99, "high": 105, "low": 95,
           "close": 100, "volume": 10, "price_unit": "VND", "price_basis": "raw",
           "source_url": "https://example.org/prices"}
    return pd.DataFrame([{**row, **changes}])


def issue_codes(frame):
    return {issue["code"] for issue in frame.attrs["quality_issues"]}


@pytest.mark.parametrize("column,value", [
    ("date", None), ("date", "2026-1-2"), ("date", "2026-10-08T09:00:00Z"),
    ("date", "2026-02-30"), ("source_url", "https:///prices"), ("source_url", "file:///local.csv"),
    ("source_url", "https://:secret@example.org/prices"), ("volume", 1.5), ("volume", True),
    ("volume", float(2**63)), ("volume", float("nan")), ("volume_unit", "lots"),
    ("open", 0), ("close", True), ("low", 110), ("high", 90), ("price_unit", "auto"),
    ("price_basis", "adjusted"), ("close", float("inf")),
])
def test_strict_ohlcv_source_volume_and_dates(column, value):
    with pytest.raises(ValueError):
        normalize_prices(prices(**{column: value}), "AAA", AS_OF)


def test_price_conversion_overflow_rejected():
    frame = prices(open=1e308, high=1e308, low=1e308, close=1e308, price_unit="thousand_VND")
    with pytest.raises(ValueError, match="Tràn số"):
        normalize_prices(frame, "AAA", AS_OF)


def test_future_rows_and_other_tickers_are_not_used():
    combined = pd.concat([prices(), prices(date="2026-10-10", close=104), prices(ticker="BBB", close=103)])
    normalized = normalize_prices(combined, "AAA", AS_OF)
    assert len(normalized) == 1 and normalized.iloc[0].close == 100


def test_mixed_demo_real_and_mixed_price_basis_rejected():
    with pytest.raises(ValueError, match="trộn"):
        normalize_prices(pd.concat([prices(), prices(date="2026-10-07", source_url="urn:demo:fixture")]), "AAA", AS_OF)
    with pytest.raises(ValueError, match="đồng nhất"):
        normalize_prices(pd.concat([prices(), prices(date="2026-10-07", price_basis="split_adjusted")]), "AAA", AS_OF)


def test_unknown_adjustment_suppresses_return_volatility_drawdown(tmp_path):
    frame = pd.concat([prices(date=str(day), close=100 + offset, high=150)
                       for offset, day in enumerate(pd.bdate_range("2026-09-01", "2026-10-08").date)])
    frame["price_basis"] = "unknown"
    path = tmp_path / "prices.csv"
    frame.to_csv(path, index=False)
    normalized, sources, section = load_prices("AAA", AS_OF, Mode.SNAPSHOT, path)
    assert "PRICE_ADJUSTMENT_UNKNOWN" in issue_codes(normalized)
    assert sources[0].sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert section.status == "partial"
    for key in ["Lợi suất giá 20 phiên", "Biến động năm hóa (252 phiên)", "Sụt giảm tối đa trong cửa sổ"]:
        assert section.rows[0][key] is None


def test_stale_and_synthetic_inputs_cannot_appear_complete(tmp_path):
    path = tmp_path / "prices.csv"
    prices(date="2026-09-01").to_csv(path, index=False)
    normalized, _, section = load_prices("AAA", AS_OF, Mode.SNAPSHOT, path)
    assert section.status == "partial" and "STALE_MARKET_PRICE" in issue_codes(normalized)
    prices(price_basis="synthetic").to_csv(path, index=False)
    normalized, sources, section = load_prices("AAA", AS_OF, Mode.LIVE, path)
    assert sources[0].kind == "synthetic" and section.status == "partial"
    assert {"SYNTHETIC_MARKET_INPUT", "SYNTHETIC_OUTSIDE_DEMO"}.issubset(issue_codes(normalized))


def actions(**changes):
    return pd.DataFrame([{ "ticker": "AAA", "ex_date": "2026-10-08", "action_type": "split",
                          "split_ratio": 2, "source_url": "https://example.org/action", **changes}])


def test_split_adjusts_only_analysis_prices_and_preserves_raw_prices():
    normalized = normalize_prices(pd.concat([prices(date="2026-10-07", close=100),
                                             prices(date="2026-10-08", open=50, high=55, low=45, close=50)]), "AAA", AS_OF)
    adjusted = apply_corporate_actions(normalized, actions(), AS_OF)
    assert adjusted.close.tolist() == [100, 50]
    assert adjusted.analysis_close.tolist() == [50, 50]
    assert adjusted.attrs["analysis_basis"] == "split_adjusted"
    assert "RAW_PRICE_RETURN" not in issue_codes(adjusted)
    assert normalized.analysis_close.tolist() == [100, 50]


def test_future_action_not_applied_and_cash_dividend_not_fabricated():
    normalized = normalize_prices(prices(), "AAA", AS_OF)
    future = apply_corporate_actions(normalized, actions(ex_date="2026-10-10"), AS_OF)
    assert future.analysis_close.tolist() == [100]
    dividend = apply_corporate_actions(normalized, actions(action_type="cash_dividend", cash_per_share=20), AS_OF)
    assert dividend.analysis_close.tolist() == [100]
    assert dividend.attrs["dividend_policy"] == "price_return_excludes_cash_dividends"


def test_unknown_price_basis_remains_unknown_after_supplied_split(tmp_path):
    path = tmp_path / "prices.csv"
    action_path = tmp_path / "actions.csv"
    prices(date="2026-10-07", price_basis="unknown").to_csv(path, index=False)
    actions().to_csv(action_path, index=False)
    frame, sources, section = load_prices("AAA", AS_OF, Mode.SNAPSHOT, path, actions_path=action_path)
    assert frame.attrs["analysis_basis"] == "unknown"
    assert "ADJUSTMENT_REQUIRES_RAW_BASIS" in issue_codes(frame)
    assert section.rows[0]["Sụt giảm tối đa trong cửa sổ"] is None
    assert sources[1].sha256 == hashlib.sha256(action_path.read_bytes()).hexdigest()


@pytest.mark.parametrize("changes", [
    {"split_ratio": 0}, {"split_ratio": True}, {"split_ratio": float("inf")}, {"ex_date": None},
    {"ex_date": "2026-1-2"}, {"action_type": "rights"}, {"source_url": "https:///action"},
    {"action_type": "cash_dividend", "cash_per_share": -1},
])
def test_invalid_corporate_action_rejected(changes):
    with pytest.raises(ValueError):
        apply_corporate_actions(normalize_prices(prices(), "AAA", AS_OF), actions(**changes), AS_OF)


def test_duplicate_and_double_adjustment_rejected():
    normalized = normalize_prices(prices(), "AAA", AS_OF)
    with pytest.raises(ValueError, match="trùng"):
        apply_corporate_actions(normalized, pd.concat([actions(), actions()]), AS_OF)
    adjusted = normalize_prices(prices(price_basis="split_adjusted"), "AAA", AS_OF)
    with pytest.raises(ValueError, match="lần hai"):
        apply_corporate_actions(adjusted, actions(), AS_OF)


class MockResponse:
    def __init__(self, document, status=200):
        self.payload = document if isinstance(document, bytes) else json.dumps(document).encode()
        self.status_code = status
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.payload

    def close(self):
        self.closed = True


class MockSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def response_document(**changes):
    return {"symbol": "AAA", "data_day": [{"t": "2026-10-08 00:00", "o": 99, "h": 105,
                                             "l": 95, "c": 100, "v": 10}], **changes}


def test_provider_archives_exact_response_and_never_claims_adjustment(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_LAST_REQUEST", 0)
    response = MockResponse(response_document())
    session = MockSession(response)
    frame, metadata = fetch_prices("AAA", date(2026, 10, 1), AS_OF, session=session,
                                   config=MarketConfig(archive_dir=tmp_path))
    digest = hashlib.sha256(response.payload).hexdigest()
    assert metadata["response_sha256"] == digest and (tmp_path / (digest + ".json")).read_bytes() == response.payload
    assert metadata["adjustment_basis"] == "unknown" and metadata["automatic_retries"] == 0
    assert frame.price_basis.tolist() == ["unknown"] and frame.volume_unit.tolist() == ["shares"]
    assert frame.iloc[0].close == 100 and len(session.calls) == 1 and response.closed
    assert session.calls[0][1]["allow_redirects"] is False


@pytest.mark.parametrize("document,status", [
    (response_document(symbol="BBB"), 200), (response_document(data_day={}), 200),
    (response_document(data_day=[{"t": "2026-11-01 00:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]), 200),
    (response_document(), 429), (response_document(), 302), (b"not JSON", 200), (b"x" * 1025, 200),
])
def test_provider_fails_without_retries(document, status, monkeypatch):
    monkeypatch.setattr(providers, "_LAST_REQUEST", 0)
    response = MockResponse(document, status)
    session = MockSession(response)
    with pytest.raises(ValueError):
        fetch_prices("AAA", date(2026, 10, 1), AS_OF, session=session, config=MarketConfig(maximum_bytes=1024))
    assert len(session.calls) == 1 and response.closed


def test_provider_network_failure_has_one_attempt(monkeypatch):
    monkeypatch.setattr(providers, "_LAST_REQUEST", 0)

    class FailedSession:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise requests.Timeout("mock timeout")

    session = FailedSession()
    with pytest.raises(ValueError, match="không tự retry"):
        fetch_prices("AAA", date(2026, 10, 1), AS_OF, session=session)
    assert session.calls == 1

from datetime import date

import pandas as pd
import pytest

from vnresearch.domain.models import Mode
from vnresearch.macro import provider


def _macro_row(indicator, year, value, source_url="https://api.worldbank.org/v2/test"):
    return {
        "indicator": indicator,
        "label": provider.WORLD_BANK_INDICATORS.get(indicator, ("Custom indicator", "unit", "annual"))[0],
        "year": year,
        "value": value,
        "unit": provider.WORLD_BANK_INDICATORS.get(indicator, ("Custom indicator", "unit", "annual"))[1],
        "source_url": source_url,
        "retrieved_at": "2026-10-09T00:00:00+00:00",
    }


def test_fetch_world_bank_keeps_year_contract_and_writer_columns(monkeypatch):
    calls = []

    class Response:
        url = "https://api.worldbank.org/v2/country/VNM/indicator/test?format=json"

        def __init__(self, code):
            self.code = code

        def raise_for_status(self):
            pass

        def json(self):
            if self.code == "NY.GDP.MKTP.KD.ZG":
                return [{"pages": 1}, [{"date": "2020", "value": 2.9}, {"date": "2019", "value": None}]]
            return [{"pages": 1}, []]

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(url.rsplit("/", 1)[-1])

    monkeypatch.setattr(provider.requests, "get", fake_get)
    frame = provider.fetch_world_bank(2019, 2020)

    assert list(frame.columns) == provider.FETCH_COLUMNS
    assert frame[["indicator", "year", "value"]].to_dict("records") == [
        {"indicator": "NY.GDP.MKTP.KD.ZG", "year": 2020, "value": 2.9}
    ]
    assert len(calls) == len(provider.WORLD_BANK_INDICATORS)
    assert all(call[1]["timeout"] == 20 for call in calls)


def test_snapshot_loads_existing_world_bank_year_csv_and_flags_missing_indicators(monkeypatch, tmp_path):
    macro_dir = tmp_path / "macro"
    macro_dir.mkdir()
    snapshot = macro_dir / "world_bank.csv"
    pd.DataFrame([_macro_row("NY.GDP.MKTP.KD.ZG", 2020, 2.9)]).to_csv(snapshot, index=False)
    monkeypatch.setattr(provider, "WORLD_BANK_CSV", snapshot)
    monkeypatch.setattr(provider, "ASSETS", tmp_path)

    sources, section = provider.load_macro(date(2021, 6, 30), Mode.SNAPSHOT)

    observations = [row for row in section.rows if row["Loại dòng"] == "Quan sát vĩ mô"]
    quality = [row for row in section.rows if row["Loại dòng"] == "Chất lượng dữ liệu"]
    assert len(observations) == 1
    assert observations[0]["Kỳ gần nhất"] == "2020"
    assert observations[0]["Giá trị"] == pytest.approx(2.9)
    assert section.status == "partial"
    assert len(quality) == len(provider.WORLD_BANK_INDICATORS) - 1
    assert any(row["Mã chỉ tiêu"] == "FP.CPI.TOTL.ZG" for row in quality)
    assert sources[0].verification_status == "unverified"
    assert "vintage công bố" in sources[0].note


def test_invalid_missing_and_future_observations_are_reported_and_excluded(monkeypatch, tmp_path):
    macro_dir = tmp_path / "macro"
    macro_dir.mkdir()
    snapshot = macro_dir / "world_bank.csv"
    rows = [
        _macro_row("NY.GDP.MKTP.KD.ZG", 2020, "bad"),
        _macro_row("FP.CPI.TOTL.ZG", 2021, 3.0),
    ]
    pd.DataFrame(rows).to_csv(snapshot, index=False)
    monkeypatch.setattr(provider, "WORLD_BANK_CSV", snapshot)
    monkeypatch.setattr(provider, "ASSETS", tmp_path)

    sources, section = provider.load_macro(date(2020, 12, 31), Mode.SNAPSHOT)

    assert sources == []
    assert section.status == "unavailable"
    diagnostics = [row for row in section.rows if row["Loại dòng"] == "Chất lượng dữ liệu"]
    gdp_errors = [row for row in diagnostics if row["Mã chỉ tiêu"] == "NY.GDP.MKTP.KD.ZG"]
    cpi_errors = [row for row in diagnostics if row["Mã chỉ tiêu"] == "FP.CPI.TOTL.ZG"]
    assert any("không phải số" in row["Ghi chú"] for row in gdp_errors)
    assert any("chưa kết thúc" in row["Ghi chú"] for row in cpi_errors)
    assert any("Không có quan sát hợp lệ" in row["Ghi chú"] for row in diagnostics)


def test_live_world_bank_rows_never_claim_point_in_time_vintage(monkeypatch, tmp_path):
    monkeypatch.setattr(provider, "ASSETS", tmp_path)
    monkeypatch.setattr(
        provider,
        "fetch_world_bank",
        lambda start, end: pd.DataFrame([_macro_row("NY.GDP.MKTP.KD.ZG", 2017, 6.8)]),
    )

    sources, section = provider.load_macro(date(2018, 12, 31), Mode.LIVE)

    observation = next(row for row in section.rows if row["Loại dòng"] == "Quan sát vĩ mô")
    assert observation["Vintage point-in-time"] == "chưa xác minh"
    assert "vintage đã xác minh" in section.summary
    assert section.status == "partial"
    assert sources[0].verification_status == "unverified"


def test_invalid_publication_date_is_reported_separately_from_missing_date(monkeypatch, tmp_path):
    macro_dir = tmp_path / "macro"
    macro_dir.mkdir()
    snapshot = macro_dir / "world_bank.csv"
    rows = [
        {**_macro_row("NY.GDP.MKTP.KD.ZG", 2020, 2.9, "https://example.org/macro"), "published_at": "not-a-date"},
        {**_macro_row("FP.CPI.TOTL.ZG", 2020, 3.2, "https://example.org/macro"), "published_at": ""},
    ]
    pd.DataFrame(rows).to_csv(snapshot, index=False)
    monkeypatch.setattr(provider, "WORLD_BANK_CSV", snapshot)
    monkeypatch.setattr(provider, "ASSETS", tmp_path)

    _, section = provider.load_macro(date(2021, 6, 30), Mode.SNAPSHOT)

    observations = {
        row["Mã chỉ tiêu"]: row
        for row in section.rows
        if row["Loại dòng"] == "Quan sát vĩ mô"
    }
    diagnostics = [
        row for row in section.rows if row["Loại dòng"] == "Chất lượng dữ liệu"
    ]
    assert observations["NY.GDP.MKTP.KD.ZG"]["Trạng thái ngày công bố"] == "không hợp lệ"
    assert observations["NY.GDP.MKTP.KD.ZG"]["published_at"] is None
    assert observations["FP.CPI.TOTL.ZG"]["Trạng thái ngày công bố"] == "không được cung cấp"
    assert not any(
        row["Mã chỉ tiêu"] == "FP.CPI.TOTL.ZG" and "Ngày công bố được cung cấp" in row["Ghi chú"]
        for row in diagnostics
    )
    assert any(
        row["Mã chỉ tiêu"] == "NY.GDP.MKTP.KD.ZG" and "Ngày công bố được cung cấp nhưng không hợp lệ" in row["Ghi chú"]
        for row in diagnostics
    )
    assert section.status == "partial"


def test_unknown_indicator_is_kept_with_visible_definition_warning(monkeypatch, tmp_path):
    macro_dir = tmp_path / "macro"
    macro_dir.mkdir()
    snapshot = macro_dir / "world_bank.csv"
    pd.DataFrame([_macro_row("CUSTOM.X", 2020, 4.2, "https://example.org/macro")]).to_csv(snapshot, index=False)
    monkeypatch.setattr(provider, "WORLD_BANK_CSV", snapshot)
    monkeypatch.setattr(provider, "ASSETS", tmp_path)

    _, section = provider.load_macro(date(2021, 6, 30), Mode.SNAPSHOT)

    assert any(row["Mã chỉ tiêu"] == "CUSTOM.X" and row["Giá trị"] == 4.2 for row in section.rows)
    assert any(
        row["Mã chỉ tiêu"] == "CUSTOM.X" and "ngoài danh mục" in row["Ghi chú"]
        for row in section.rows
        if row["Loại dòng"] == "Chất lượng dữ liệu"
    )
    assert section.status == "partial"

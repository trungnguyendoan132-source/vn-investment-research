"""Offline regression tests; generated document bytes are protocol fixtures, not issuer evidence."""

from copy import deepcopy
from datetime import date
import hashlib
import json

import pandas as pd
import pytest

from vnresearch.data.coverage import coverage_report
from vnresearch.data.filings import import_filing, load_filings, validate_filing
from vnresearch.data.fundamentals import company, company_universe, extract_facts, file_source, load_raw
from vnresearch.data.snapshots import _parquet, read_parquet, read_release, seal_release


DOCUMENT = b"Offline filing protocol fixture, not a real issuer PDF."


def envelope(**changes):
    item = {"ticker": "XFIX", "fiscal_year": 2025, "period_start": "2025-01-01",
            "period_end": "2025-12-31", "period_type": "annual", "published_on": "2026-03-27",
            "consolidation": "consolidated", "report_url": "https://example.org/XFIX-2025.pdf",
            "original_sha256": hashlib.sha256(DOCUMENT).hexdigest(), "verification_status": "verified",
            "verification_note": "Offline generated protocol fixture only.",
            "facts": [{"key": "revenue", "value": 120, "unit": "VND", "page": 2}]}
    return {**item, **changes}


def imported(tmp_path, item, name="input.json", *, document=DOCUMENT):
    metadata = tmp_path / name
    metadata.write_text(json.dumps(item), encoding="utf-8")
    original = None
    if document is not None:
        original = tmp_path / (name + ".document")
        original.write_bytes(document)
    return import_filing(metadata, tmp_path / "filings", original_document=original)


def raw_facts(values, *, year=2025, **metadata):
    return pd.DataFrame([{ "ticker": "XFIX", "year": year, "source_id": "fixture",
                          "item_code": code, "value": value, **metadata} for code, value in values.items()])


def codes(observation):
    return {issue["code"] for issue in observation["quality_issues"]}


def test_parquet_cache_and_source_use_exact_current_bytes(tmp_path):
    folder = tmp_path / "balance_sheet"
    folder.mkdir()
    path = folder / "TEST.parquet"
    raw_facts({"bs_tong_tai_san": 10}).to_parquet(path)
    first, first_hash, first_bytes = read_parquet(path)
    raw_facts({"bs_tong_tai_san": 20}).to_parquet(path)
    second, second_hash, second_bytes = read_parquet(path)
    assert first_hash != second_hash
    assert first.iloc[0].value == 10 and second.iloc[0].value == 20
    assert first_hash == hashlib.sha256(first_bytes).hexdigest()
    assert second_hash == hashlib.sha256(second_bytes).hexdigest()
    source = file_source(path, payload=second_bytes, digest=second_hash, base=tmp_path)
    assert source.sha256 == second_hash
    with pytest.raises(ValueError, match="parsed bytes"):
        file_source(path, payload=second_bytes, digest=first_hash, base=tmp_path)
    with pytest.raises(ValueError, match="parsed bytes"):
        _parquet(first_hash, second_bytes)


def test_sealed_snapshot_relative_paths_and_tamper_guard(tmp_path, monkeypatch):
    original = tmp_path / "input" / "balance_sheet"
    original.mkdir(parents=True)
    raw_facts({"bs_tong_tai_san": 10}).to_parquet(original / "TEST.parquet")
    monkeypatch.chdir(tmp_path)
    release = seal_release(tmp_path / "input", tmp_path / "releases")
    entries, version = read_release(release.relative_to(tmp_path))
    assert release.name == version and len(entries) == 1
    assert seal_release(tmp_path / "input", tmp_path / "releases") == release
    (release / "balance_sheet" / "TEST.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity failed"):
        read_release(release)


def test_load_raw_returns_copy_and_content_version_changes(tmp_path):
    directory = tmp_path / "balance_sheet"
    directory.mkdir()
    path = directory / "TEST.parquet"
    raw_facts({"bs_tong_tai_san": 10}).to_parquet(path)
    first, sources = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path)
    first["value"] = 999
    second, _ = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path)
    assert second.iloc[0].value == 10
    old_version = second.iloc[0].dataset_version
    raw_facts({"bs_tong_tai_san": 20}).to_parquet(path)
    latest, latest_sources = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path)
    assert latest.iloc[0].value == 20 and latest.iloc[0].dataset_version != old_version
    assert sources[0].sha256 != latest_sources[0].sha256
    assert latest.iloc[0].file_sha256 == latest_sources[0].sha256


def test_empty_configured_directory_uses_packaged_legacy_without_certifying_it(tmp_path):
    raw, sources = load_raw(["FPT"], 2025, 2025, dataset_dir=tmp_path / "not-yet-created")
    row = extract_facts(raw, "FPT")[0]
    assert row["facts"]["revenue"] > 0
    assert row["fact_metadata"]["revenue"]["verification_status"] == "unverified"
    assert sources and all(source.kind == "snapshot" for source in sources)
    assert "LEGACY_PROVENANCE_UNVERIFIED" in codes(row)
    (tmp_path / "release.json").write_text('{"schema_version":"1.0.0","files":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="no file inventory"):
        load_raw(["FPT"], 2025, 2025, dataset_dir=tmp_path)


def test_company_catalog_refresh_is_content_cached_and_copied(tmp_path):
    path = tmp_path / "companies.csv"
    path.write_text("Mã CK,Tên Doanh Nghiệp\nXFIX,First\n", encoding="utf-8")
    first = company_universe(path)
    first.loc["XFIX", "Tên Doanh Nghiệp"] = "caller mutation"
    assert company_universe(path).loc["XFIX", "Tên Doanh Nghiệp"] == "First"
    path.write_text("Mã CK,Tên Doanh Nghiệp\nBBB,Second\n", encoding="utf-8")
    assert company_universe(path).index.tolist() == ["BBB"]
    path.write_text("Mã CK\nXFIX\nXFIX\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trùng"):
        company_universe(path)


@pytest.mark.parametrize("revenue_code,income_code,parent_code", [
    ("is_tong_thu_nhap_hoat_dong", "is_loi_nhuan_sau_thue", None),
    ("is_doanh_thu_hoat_dong", "is_loi_nhuan_ke_toan_sau_thue", "is_loi_nhuan_sau_thue_phan_bo_cho_chu_so_huu"),
    ("is_doanh_thu_thuan_tu_hoat_dong_kinh_doanh_bao_hiem", "is_loi_nhuan_sau_thue", "is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan"),
])
def test_sector_template_exact_mapping(revenue_code, income_code, parent_code):
    values = {revenue_code: 120, income_code: 20, "is_doanh_so_thuan": 999}
    if parent_code:
        values[parent_code] = 18
    row = extract_facts(raw_facts(values), "XFIX")[0]
    assert row["facts"]["revenue"] == 120 and row["facts"]["net_income"] == 20
    if parent_code:
        assert row["facts"]["net_income_parent"] == 18


def test_conflicting_code_fails_and_conflicting_alias_quarantines():
    one = raw_facts({"is_doanh_so_thuan": 100})
    two = raw_facts({"is_doanh_so_thuan": 101})
    with pytest.raises(ValueError, match="xung đột"):
        extract_facts(pd.concat([one, two]), "XFIX")
    row = extract_facts(raw_facts({"is_doanh_so_thuan": 100, "is_doanh_thu_thuan": 101}), "XFIX")[0]
    assert row["facts"]["revenue"] is None
    assert row["fact_metadata"]["revenue"]["status"] == "quarantined"
    assert "AMBIGUOUS_FACT_ALIAS" in codes(row)


def test_eps_wrong_column_and_wrong_unit_are_quarantined():
    row = extract_facts(raw_facts({"is_lai_co_ban_tren_co_phieu": 2000000000000,
                                  "is_loi_nhuan_cua_co_dong_cua_cong_ty_me": 2000000000000}), "XFIX")[0]
    assert row["facts"]["eps"] is None and "EPS_INCONSISTENT" in codes(row)
    frame = raw_facts({"is_lai_co_ban_tren_co_phieu": 2000}, unit="VND")
    row = extract_facts(frame, "XFIX")[0]
    assert row["facts"]["eps"] is None and "FINANCIAL_UNIT_MISMATCH" in codes(row)


def test_eps_uses_same_period_weighted_average_shares():
    row = extract_facts(raw_facts({"is_lai_co_ban_tren_co_phieu": 2500,
                                  "is_loi_nhuan_cua_co_dong_cua_cong_ty_me": 100000,
                                  "is_so_co_phieu_binh_quan": 100}), "XFIX")[0]
    assert row["facts"]["eps"] is None and "EPS_INCONSISTENT" in codes(row)


def test_equity_basis_requires_accounting_identity():
    values = {"bs_tong_tai_san": 150, "bs_no_phai_tra": 100, "bs_von_chu_so_huu": 40,
              "bs_loi_ich_cua_co_dong_khong_kiem_soat": 10}
    row = extract_facts(raw_facts(values), "XFIX")[0]
    assert row["facts"]["equity"] == 50 and row["facts"]["equity_parent"] == 40
    assert row["fact_metadata"]["equity"]["raw_value"] == 40
    assert row["fact_metadata"]["equity"]["selected_value"] == 50
    assert "EQUITY_BASIS_NORMALIZED" in codes(row)
    values["bs_tong_tai_san"] = 999
    row = extract_facts(raw_facts(values), "XFIX")[0]
    assert row["facts"]["equity_parent"] is None and "EQUITY_BASIS_AMBIGUOUS" in codes(row)


def test_legacy_sign_guards_and_missing_ebitda():
    row = extract_facts(raw_facts({"cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac": 4,
                                  "cf_khau_hao_tscd": -2, "is_ebit": 10}), "XFIX")[0]
    assert row["facts"]["capex"] is None and row["facts"]["depreciation"] is None
    assert row["facts"]["ebitda"] is None
    assert {"CAPEX_SIGN_UNVERIFIED", "DEPRECIATION_SIGN_UNVERIFIED"}.issubset(codes(row))


@pytest.mark.parametrize("key,code,sign,value,expected", [
    ("capex", "cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac", "outflow_negative", -4, 4),
    ("capex", "cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac", "outflow_negative", 4, None),
    ("capex", "cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac", "canonical", -4, None),
    ("interest_expense", "is_chi_phi_lai_vay", "expense_negative", -3, 3),
    ("interest_expense", "is_chi_phi_lai_vay", "canonical", -3, None),
])
def test_imported_sign_convention_not_silently_abs(key, code, sign, value, expected):
    row = extract_facts(raw_facts({code: value}, filing_id="fixture", verification_status="verified",
                                  report_basis="consolidated", published_on="2026-03-27",
                                  period_start="2025-01-01", period_end="2025-12-31",
                                  sign_convention=sign), "XFIX")[0]
    assert row["facts"][key] == expected
    if expected is not None:
        assert row["fact_metadata"][key]["selected_value"] == expected


def test_derived_verification_requires_all_inputs_verified():
    frame = raw_facts({"is_loi_nhuan_truoc_thue": 10, "is_chi_phi_lai_vay": 2,
                       "cf_khau_hao_tscd": 3}, verification_status="verified")
    row = extract_facts(frame, "XFIX")[0]
    assert row["facts"]["ebitda"] == 15
    assert row["fact_metadata"]["ebitda"]["verification_status"] == "verified"
    frame.loc[frame.item_code.eq("is_chi_phi_lai_vay"), "verification_status"] = "unverified"
    row = extract_facts(frame, "XFIX")[0]
    assert row["fact_metadata"]["ebit"]["verification_status"] == "unverified"
    assert row["fact_metadata"]["ebitda"]["verification_status"] == "unverified"


def test_filing_publication_precision_and_original_document_required():
    item = validate_filing(envelope(), DOCUMENT)
    assert item["published_at"] is None and item["publication_precision"] == "day"
    assert item["facts"][0]["page"] == 2
    with pytest.raises(ValueError, match="verified"):
        validate_filing(envelope())
    with pytest.raises(ValueError, match="checksum"):
        validate_filing(envelope(), b"different")
    with pytest.raises(ValueError, match="múi giờ"):
        validate_filing(envelope(published_at="2026-03-27T09:00:00"), DOCUMENT)


@pytest.mark.parametrize("changes", [
    {"published_on": None}, {"published_on": "20260327"}, {"published_on": "2025-12-30"},
    {"consolidation": "unknown"}, {"period_type": "TTM"}, {"fiscal_year": True},
    {"report_url": "https:///filing.pdf"}, {"report_url": "https://:password@example.org/a"},
    {"facts": [{"key": "eps", "value": 1000, "unit": "VND", "page": 2}]},
    {"facts": [{"key": "revenue", "value": float("inf"), "unit": "VND", "page": 2}]},
    {"facts": [{"key": "revenue", "value": 1000, "unit": "VND", "page": True}]},
])
def test_filing_invalid_metadata_rejected(changes):
    with pytest.raises(ValueError):
        validate_filing(envelope(**changes), DOCUMENT)


def test_filing_scale_does_not_double_scale_canonical_values():
    reported = envelope(facts=[{"key": "total_assets", "value": 3, "unit": "VND", "scale": 1000000,
                               "value_basis": "reported", "page": 2}])
    converted = validate_filing(reported, DOCUMENT)
    assert converted["facts"][0]["value"] == 3000000
    assert validate_filing(converted, DOCUMENT)["facts"][0]["value"] == 3000000
    canonical = envelope(facts=[{"key": "total_assets", "value": 3000000, "unit": "VND",
                                "scale": 1000000, "page": 2}])
    assert validate_filing(canonical, DOCUMENT)["facts"][0]["value"] == 3000000


def test_filing_import_is_immutable_and_cutoff_applies_to_current_and_prior(tmp_path):
    release = imported(tmp_path, envelope())
    prior = envelope(fiscal_year=2024, period_start="2024-01-01", period_end="2024-12-31",
                     comparative=True, comparison_source_fiscal_year=2025,
                     facts=[{"key": "revenue", "value": 100, "unit": "VND", "page": 2}])
    imported(tmp_path, prior, name="prior.json")
    assert imported(tmp_path, envelope()) == release
    before, sources = load_raw(["XFIX"], 2024, 2025, dataset_dir=tmp_path / "empty",
                               filing_dir=tmp_path / "filings", as_of=date(2026, 3, 26))
    assert before.empty and not sources
    current, sources = load_raw(["XFIX"], 2024, 2025, dataset_dir=tmp_path / "empty",
                                filing_dir=tmp_path / "filings", as_of=date(2026, 3, 27))
    observations = extract_facts(current, "XFIX")
    assert [row["year"] for row in observations] == [2024, 2025]
    assert [row["facts"]["revenue"] for row in observations] == [100, 120]
    meta = observations[-1]["fact_metadata"]["revenue"]
    assert meta["source_page"] == 2 and meta["original_sha256"] == hashlib.sha256(DOCUMENT).hexdigest()
    assert meta["published_on"] == "2026-03-27" and meta["published_at"] is None
    assert {source.sha256 for source in sources} == {hashlib.sha256(DOCUMENT).hexdigest()}
    (release / "filing.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        load_filings(tmp_path / "filings", ["XFIX"], 2024, 2025)


def test_verified_consolidated_filing_wins_without_legacy_fact_backfill(tmp_path):
    folder = tmp_path / "balance_sheet"
    folder.mkdir()
    raw_facts({"bs_tong_tai_san": 999, "is_doanh_so_thuan": 999}).to_parquet(folder / "TEST.parquet")
    imported(tmp_path, envelope(consolidation="separate", facts=[{"key": "revenue", "value": 90,
                                                                 "unit": "VND", "page": 2}]), "separate.json")
    imported(tmp_path, envelope(), "consolidated.json")
    raw, _ = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path, filing_dir=tmp_path / "filings")
    row = extract_facts(raw, "XFIX")[0]
    assert row["facts"]["revenue"] == 120 and row["facts"]["total_assets"] is None
    assert row["fact_metadata"]["revenue"]["report_basis"] == "consolidated"


def test_unverified_filing_does_not_overwrite_legacy_and_periods_do_not_mix(tmp_path):
    folder = tmp_path / "income_statement"
    folder.mkdir()
    raw_facts({"is_doanh_so_thuan": 100}).to_parquet(folder / "TEST.parquet")
    imported(tmp_path, envelope(verification_status="unverified"), "unverified.json", document=None)
    imported(tmp_path, envelope(period_type="quarterly", period_start="2025-10-01"), "quarter.json")
    annual, _ = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path, filing_dir=tmp_path / "filings")
    row = extract_facts(annual, "XFIX")[0]
    assert row["facts"]["revenue"] == 100 and "UNVERIFIED_FILING_NOT_APPLIED" in codes(row)
    quarter, _ = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path, filing_dir=tmp_path / "filings",
                          period_type="quarterly")
    assert len(quarter) == 1 and quarter.iloc[0].period_type == "quarterly"
    assert extract_facts(quarter, "XFIX") == []


def test_ambiguous_same_day_revision_cannot_be_selected_automatically(tmp_path):
    imported(tmp_path, envelope(), "first.json")
    changed = deepcopy(envelope())
    changed["facts"][0]["value"] = 121
    imported(tmp_path, changed, "second.json")
    raw, _ = load_raw(["XFIX"], 2025, 2025, dataset_dir=tmp_path / "empty", filing_dir=tmp_path / "filings")
    with pytest.raises(ValueError, match="Multiple filing revisions"):
        extract_facts(raw, "XFIX")


def test_missing_company_identity_and_coverage_are_explicit(tmp_path):
    imported(tmp_path, envelope())
    catalog = tmp_path / "companies.csv"
    catalog.write_text("Mã CK,Tên Doanh Nghiệp\nBBB,Other\n", encoding="utf-8")
    item = company("XFIX", catalog_path=catalog, dataset_dir=tmp_path / "empty", filing_dir=tmp_path / "filings")
    assert item["identity_status"] == "unknown" and item["exchange"] == "unknown"
    assert item["quality_issues"][0]["code"] == "MISSING_COMPANY_IDENTITY"
    report = coverage_report(tickers=["XFIX", "ZZZZ"], dataset_dir=tmp_path / "empty",
                             filing_dir=tmp_path / "filings")
    assert report["queried_tickers"] == 2 and report["available_tickers"] == 1
    assert report["rows"][0]["periods"][0]["verified_facts"] == ["revenue"]
    assert report["rows"][1]["status"] == "unavailable"

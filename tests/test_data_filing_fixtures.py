"""Metadata regressions for selected issuer observations, not repeat visual certification."""

from datetime import date
import json
from pathlib import Path, PureWindowsPath

import pytest

from vnresearch.data.filings import validate_filing


FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "verified-filings"


@pytest.mark.parametrize("ticker,published_on,eps,assets", [
    ("SSI", "2026-03-27", 2053, 94049979396183),
    ("VCB", "2026-03-27", 3854, 2442279166000000),
    ("FPT", "2026-03-19", 5216, 88141991634625),
])
def test_selected_original_metadata_preserved(ticker, published_on, eps, assets):
    item = json.loads((FIXTURES / f"{ticker}_2025_verified_filing.json").read_text(encoding="utf-8"))
    facts = {fact["key"]: fact for fact in item["facts"]}
    assert len(facts) == 11 and item["verification_status"] == "verified"
    assert item["consolidation"] == "consolidated" and item["period_type"] == "annual"
    assert item["published_on"] == published_on and item["published_at"] is None
    assert item["publication_precision"] == "day" and item["publication_evidence"]["date_only"] is True
    assert item["period_start"] == "2025-01-01" and item["period_end"] == "2025-12-31"
    assert facts["eps"]["value"] == eps and facts["eps"]["unit"] == "VND/share"
    assert facts["eps"]["scale"] == 1
    assert facts["total_assets"]["value"] == assets
    assert facts["total_assets"]["value"] == facts["total_liabilities"]["value"] + facts["equity"]["value"]
    assert all(1 <= fact["page"] <= item["verification_context"]["page_count"] for fact in item["facts"])
    assert len(item["original_sha256"]) == 64
    with pytest.raises(ValueError, match="verified"):
        validate_filing(item)
    validated = validate_filing({**item, "verification_status": "unverified"})
    assert validated["facts"][0]["value"] == facts["total_assets"]["value"]


@pytest.mark.parametrize("ticker", ["SSI", "VCB", "FPT"])
def test_comparative_is_available_on_source_report_publication_not_backdated(ticker):
    current = json.loads((FIXTURES / f"{ticker}_2025_verified_filing.json").read_text(encoding="utf-8"))
    prior = json.loads((FIXTURES / f"{ticker}_2024_comparative_verified_filing.json").read_text(encoding="utf-8"))
    assert prior["comparative"] is True and prior["comparison_source_fiscal_year"] == 2025
    assert prior["fiscal_year"] == 2024 and prior["period_start"] == "2024-01-01"
    assert prior["period_end"] == "2024-12-31" and len(prior["facts"]) == 4
    assert prior["published_on"] == current["published_on"]
    assert prior["published_at"] is None and prior["original_sha256"] == current["original_sha256"]
    assert prior["report_url"] == current["report_url"]
    assert date.fromisoformat(prior["published_on"]).year == 2026
    assert {fact["key"] for fact in prior["facts"]} == {"total_assets", "equity", "revenue", "net_income"}


def test_fixture_metadata_contains_no_author_machine_absolute_paths():
    def check(value):
        if isinstance(value, dict):
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
        elif isinstance(value, str):
            assert not PureWindowsPath(value).is_absolute()
            assert not value.startswith("/Users/")

    for path in FIXTURES.glob("*.json"):
        check(json.loads(path.read_text(encoding="utf-8")))

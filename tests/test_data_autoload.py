"""Automatic-source transport tests use generated document bytes and mocked HTTP."""

from datetime import date
import hashlib
import json

import pytest

from vnresearch.data.autoload import ensure_fixture_filings
from vnresearch.data.filings import import_filing
from vnresearch.data.fundamentals import extract_facts, load_raw


DOCUMENT = b"Generated autoload protocol fixture, not issuer evidence."
DIGEST = hashlib.sha256(DOCUMENT).hexdigest()
AS_OF = date(2026, 10, 9)


def seed(year=2025, **changes):
    return {"ticker": "FPT", "fiscal_year": year, "period_start": f"{year}-01-01",
            "period_end": f"{year}-12-31", "period_type": "annual", "published_on": "2026-03-19",
            "consolidation": "consolidated", "report_url": "https://fpt.com/api/media/offline-test.pdf",
            "original_sha256": DIGEST, "verification_status": "verified",
            "verification_note": "Generated offline transport fixture only.",
            "verification_context": {"original_local_path": "offline-test.pdf"},
            "facts": [{"key": "revenue", "value": 120 if year == 2025 else 100, "unit": "VND", "page": 1}],
            **changes}


def seeds(tmp_path, *items):
    folder = tmp_path / "seeds"
    folder.mkdir(exist_ok=True)
    for offset, item in enumerate(items):
        (folder / f"{offset}.json").write_text(json.dumps(item), encoding="utf-8")
    return folder


class MockResponse:
    def __init__(self, payload=DOCUMENT, status=200):
        self.status_code, self.payload, self.closed = status, payload, False

    def iter_content(self, chunk_size):
        yield self.payload

    def close(self):
        self.closed = True


class MockSession:
    def __init__(self, response=None):
        self.response, self.calls = response or MockResponse(), []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_automatic_bootstrap_one_download_for_current_and_prior(tmp_path):
    folder = seeds(tmp_path, seed(2025), seed(2024))
    session = MockSession()
    result = ensure_fixture_filings(tmp_path / "filings", "FPT", 2024, 2025, AS_OF,
                                    seed_directory=folder, session=session)
    assert result["status"] == "ready" and len(result["imported_releases"]) == 2
    assert len(session.calls) == result["downloaded_documents"] == 1
    assert session.calls[0][1]["allow_redirects"] is False
    assert session.calls[0][1]["timeout"] == (5, 20) and session.response.closed
    raw, _ = load_raw(["FPT"], 2024, 2025, dataset_dir=tmp_path / "empty", filing_dir=tmp_path / "filings")
    rows = extract_facts(raw, "FPT")
    assert [row["facts"]["revenue"] for row in rows] == [100, 120]
    second = MockSession()
    repeated = ensure_fixture_filings(tmp_path / "filings", "FPT", 2024, 2025, AS_OF,
                                      seed_directory=folder, session=second)
    assert repeated["status"] == "ready" and repeated["cache_hits"] == 1 and not second.calls


def test_existing_release_note_changes_do_not_create_duplicate_revisions(tmp_path):
    previous = seed(verification_note="Previous offline test note.",
                    verification_context={"original_local_path": "old-author-machine-path.pdf"})
    metadata, original = tmp_path / "old.json", tmp_path / "old.document"
    metadata.write_text(json.dumps(previous), encoding="utf-8")
    original.write_bytes(DOCUMENT)
    existing = import_filing(metadata, tmp_path / "filings", original_document=original)
    session = MockSession()
    result = ensure_fixture_filings(tmp_path / "filings", "FPT", 2025, 2025, AS_OF,
                                    seed_directory=seeds(tmp_path, seed()), session=session)
    assert result["status"] == "ready" and result["imported_releases"] == [str(existing)]
    assert len(list((tmp_path / "filings").glob("*/filing.json"))) == 1 and not session.calls


def test_original_cache_reuse_is_hash_checked(tmp_path):
    cache = tmp_path / "originals"
    cache.mkdir()
    (cache / "offline-test.pdf").write_bytes(DOCUMENT)
    session = MockSession()
    result = ensure_fixture_filings(tmp_path / "filings", "FPT", 2025, 2025, AS_OF,
                                    seed_directory=seeds(tmp_path, seed()), original_cache=cache, session=session)
    assert result["status"] == "ready" and result["cache_hits"] == 1 and not session.calls


@pytest.mark.parametrize("response", [MockResponse(status=403), MockResponse(status=302), MockResponse(payload=b"changed")])
def test_blocked_or_changed_original_is_structured_unavailable_one_attempt(tmp_path, response):
    session = MockSession(response)
    result = ensure_fixture_filings(tmp_path / "filings", "FPT", 2024, 2025, AS_OF,
                                    seed_directory=seeds(tmp_path, seed(2025), seed(2024)), session=session)
    assert result["status"] == "unavailable" and not result["imported_releases"]
    assert len(session.calls) == 1 and len(result["issues"]) == 1
    assert result["issues"][0]["code"] == "AUTOMATIC_FILING_UNAVAILABLE"
    assert response.closed and not list((tmp_path / "filings").glob("*/filing.json"))


def test_cutoff_and_uncovered_ticker_do_not_download(tmp_path):
    folder, session = seeds(tmp_path, seed()), MockSession()
    before = ensure_fixture_filings(tmp_path / "filings", "FPT", 2025, 2025, date(2026, 3, 18),
                                    seed_directory=folder, session=session)
    assert before["status"] == "unavailable" and before["issues"][0]["code"] == "AUTOMATIC_FILING_NOT_PUBLISHED"
    missing = ensure_fixture_filings(tmp_path / "filings", "ZZZZ", 2025, 2025, AS_OF,
                                     seed_directory=folder, session=session)
    assert missing["issues"][0]["code"] == "NO_CURATED_VERIFIED_FILINGS" and not session.calls


def test_half_year_bootstrap_is_separate_and_default_annual_skips_it(tmp_path):
    half = seed(2026, period_type="half_year", period_end="2026-06-30", published_on="2026-08-14")
    folder, session = seeds(tmp_path, half), MockSession()
    annual = ensure_fixture_filings(tmp_path / "filings", "FPT", 2026, 2026, AS_OF,
                                    seed_directory=folder, session=session)
    assert annual["status"] == "unavailable" and not session.calls
    assert annual["issues"][0]["code"] == "NO_CURATED_VERIFIED_FILINGS"
    result = ensure_fixture_filings(tmp_path / "filings", "FPT", 2026, 2026, AS_OF,
                                    seed_directory=folder, session=session, period_type="half_year")
    assert result["status"] == "ready" and result["period_type"] == "half_year"
    raw, _ = load_raw(["FPT"], 2026, 2026, dataset_dir=tmp_path / "empty", filing_dir=tmp_path / "filings",
                      period_type="half_year")
    assert len(raw) == 1 and raw.iloc[0].period_end == "2026-06-30"
    assert extract_facts(raw, "FPT") == []


def test_automatic_downloader_never_follows_arbitrary_host(tmp_path):
    session = MockSession()
    result = ensure_fixture_filings(tmp_path / "filings", "FPT", 2025, 2025, AS_OF,
                                    seed_directory=seeds(tmp_path, seed(report_url="https://example.org/file.pdf")),
                                    session=session)
    assert result["status"] == "unavailable" and not session.calls
    assert "allowlist" in result["issues"][0]["message"]


def test_tampered_cached_document_is_not_trusted(tmp_path):
    directory = tmp_path / "filings"
    cache = directory / "original-cache"
    cache.mkdir(parents=True)
    (cache / f"{DIGEST}.document").write_bytes(b"tampered")
    session = MockSession(MockResponse(payload=b"changed upstream"))
    result = ensure_fixture_filings(directory, "FPT", 2025, 2025, AS_OF,
                                    seed_directory=seeds(tmp_path, seed()), session=session)
    assert result["status"] == "unavailable" and len(session.calls) == 1


def test_packaged_and_example_envelopes_match():
    from pathlib import Path
    from vnresearch.platform.settings import ASSETS

    examples = Path(__file__).resolve().parents[1] / "examples" / "verified-filings"
    packaged = ASSETS / "verified_filings"
    assert len(list(packaged.glob("*.json"))) >= 6
    for path in packaged.glob("*.json"):
        assert json.loads(path.read_bytes()) == json.loads((examples / path.name).read_bytes())

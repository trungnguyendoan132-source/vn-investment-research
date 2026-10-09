"""Automatically install bounded, curated issuer evidence; never certify unknown filings."""

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

import requests

from vnresearch.data.filings import import_filing, valid_url, validate_filing
from vnresearch.platform.settings import ASSETS


OFFICIAL_HOSTS = frozenset({"fpt.com", "www.ssi.com.vn", "www.vietcombank.com.vn"})
MAXIMUM_DOCUMENT_BYTES = 50 * 1024 * 1024


def _issue(code, message, severity="warning"):
    return {"code": code, "message": message, "severity": severity, "component": "financial"}


def _existing_release(directory: Path, seed: dict, original: Path):
    payload = original.read_bytes()
    expected = validate_filing(seed, payload)
    identity = ("ticker", "fiscal_year", "period_start", "period_end", "period_type", "consolidation",
                "published_on", "published_at", "original_sha256", "verification_status")
    for path in sorted(directory.glob("*/filing.json")):
        if not re.fullmatch(r"[a-f0-9]{64}", path.parent.name):
            continue
        serialized = path.read_bytes()
        item = json.loads(serialized)
        if not all(item.get(field) == expected.get(field) for field in identity):
            continue
        if hashlib.sha256(serialized).hexdigest() != path.parent.name:
            raise ValueError("Existing filing release identity mismatch")
        stored_original = path.parent / "original.document"
        if not stored_original.is_file():
            continue
        item = validate_filing(item, stored_original.read_bytes())
        by_key = {fact["key"]: fact for fact in item["facts"]}
        expected_by_key = {fact["key"]: fact for fact in expected["facts"]}
        if by_key == expected_by_key:
            return path.parent
    return None


def _cached_document(directory: Path, digest: str, seed: dict, original_cache: Path | None):
    candidates = [directory / "original-cache" / f"{digest}.document"]
    if original_cache:
        original_cache = Path(original_cache).resolve()
        candidates.append(original_cache / f"{digest}.document")
        name = Path(seed.get("verification_context", {}).get("original_local_path", "")).name
        if name and name == seed.get("verification_context", {}).get("original_local_path"):
            candidates.append(original_cache / name)
    candidates.extend(path for path in directory.glob("*/original.document")
                      if re.fullmatch(r"[a-f0-9]{64}", path.parent.name))
    for path in candidates:
        if not path.is_file() or path.stat().st_size > MAXIMUM_DOCUMENT_BYTES:
            continue
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() == digest:
            return path
    return None


def _download(seed: dict, directory: Path, session):
    url, digest = seed["report_url"], seed["original_sha256"]
    parsed = urlsplit(url)
    if not valid_url(url) or parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError("Curated filing URL is outside the official HTTPS host allowlist")
    started = time.monotonic()
    response = session.get(url, headers={"Accept": "application/pdf", "User-Agent": "VNResearch/0.2"},
                           timeout=(5, 20), stream=True, allow_redirects=False)
    try:
        if response.status_code != 200:
            raise ValueError(f"Official filing HTTP {response.status_code}; no automatic retry or substitution")
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAXIMUM_DOCUMENT_BYTES:
                raise ValueError("Official filing exceeds 50 MB")
            if time.monotonic() - started > 30:
                raise ValueError("Official filing exceeded the download time bound")
            chunks.append(chunk)
        payload = b"".join(chunks)
    finally:
        response.close()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Official filing original SHA-256 mismatch; document not installed")
    cache = directory / "original-cache"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{digest}.document"
    handle, staging_name = tempfile.mkstemp(prefix=".download-", dir=cache)
    staging = Path(staging_name)
    try:
        with os.fdopen(handle, "wb") as writer:
            writer.write(payload)
        os.replace(staging, target)
    finally:
        if staging.exists() and staging.resolve().parent == cache.resolve():
            staging.unlink()
    return target


def ensure_fixture_filings(directory: Path, ticker: str, start: int, end: int, as_of: date,
                           *, session=None, original_cache: Path | None = None,
                           seed_directory: Path | None = None, period_type: str = "annual") -> dict:
    """Return availability and issues; one fetch per distinct original SHA-256 per call.

    Only packaged, visually reviewed issuer observations are candidates. Their publication
    dates must precede the cutoff. Existing exact original bytes are reused. Financial facts
    are not synthesized when a document is missing, blocked, changed or outside coverage.
    """
    ticker = str(ticker).strip().upper()
    directory = Path(directory).resolve()
    result = {"ticker": ticker, "period_type": period_type, "status": "unavailable", "imported_releases": [],
              "selected_envelopes": [], "downloaded_documents": 0, "cache_hits": 0, "issues": []}
    if (not re.fullmatch(r"[A-Z0-9]{2,10}", ticker) or start > end or not isinstance(as_of, date)
            or period_type not in {"annual", "half_year", "quarterly"}):
        result["issues"].append(_issue("AUTOMATIC_FILING_INVALID_REQUEST", "Ticker, year range or cutoff is invalid", "error"))
        return result
    seeds, future = [], False
    seed_directory = Path(seed_directory or ASSETS / "verified_filings")
    for path in sorted(seed_directory.glob("*.json")):
        try:
            seed = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(seed, dict):
                raise ValueError("Seed must be a JSON object")
            if seed.get("ticker") != ticker or not start <= seed.get("fiscal_year", 0) <= end:
                continue
            if seed.get("period_type") != period_type:
                continue
            validate_filing({**seed, "verification_status": "unverified"})
            published = date.fromisoformat(seed["published_on"])
            if published > as_of:
                future = True
                continue
            if seed.get("verification_status") != "verified":
                raise ValueError("Automatic seed must contain reviewed filing observations")
            seeds.append((path, seed))
            result["selected_envelopes"].append(path.name)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            result["issues"].append(_issue("AUTOMATIC_FILING_SEED_INVALID", f"Invalid seed {path.name}: {exc}", "error"))
    if not seeds:
        code = "AUTOMATIC_FILING_NOT_PUBLISHED" if future else "NO_CURATED_VERIFIED_FILINGS"
        message = "Reviewed issuer report is published after the cutoff" if future else "No reviewed issuer observations cover this ticker/year range"
        result["issues"].append(_issue(code, message))
        return result
    directory.mkdir(parents=True, exist_ok=True)
    documents = {}
    client = session or requests.Session()
    try:
        for metadata, seed in seeds:
            digest = seed["original_sha256"]
            try:
                if digest not in documents:
                    original = _cached_document(directory, digest, seed, original_cache)
                    if original:
                        result["cache_hits"] += 1
                        documents[digest] = original
                    else:
                        try:
                            documents[digest] = _download(seed, directory, client)
                            result["downloaded_documents"] += 1
                        except (ValueError, OSError, requests.RequestException) as exc:
                            detail = type(exc).__name__ if isinstance(exc, requests.RequestException) else str(exc)
                            documents[digest] = _issue("AUTOMATIC_FILING_UNAVAILABLE", f"{ticker}: {detail}", "error")
                original = documents[digest]
                if isinstance(original, dict):
                    if original not in result["issues"]:
                        result["issues"].append(original)
                    continue
                validate_filing(seed, original.read_bytes())
                release = _existing_release(directory, seed, original)
                if release is None:
                    release = import_filing(metadata, directory, original_document=original)
                result["imported_releases"].append(str(release))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                result["issues"].append(_issue("AUTOMATIC_FILING_IMPORT_FAILED", f"{metadata.name}: {exc}", "error"))
    finally:
        if session is None:
            client.close()
    count = len(result["imported_releases"])
    result["status"] = "ready" if count == len(seeds) else "partial" if count else "unavailable"
    return result

"""Coverage is distinct from verified financial correctness."""

from datetime import date
from pathlib import Path

import pandas as pd

from vnresearch.data.fundamentals import company_universe, extract_facts, load_raw, snapshot_release
from vnresearch.data.snapshots import _parquet


def coverage_report(*, tickers: list[str] | None = None, start: int = 2024, end: int = 2025,
                    as_of: date | None = None, dataset_dir: Path | None = None,
                    filing_dir: Path | None = None, period_type: str = "annual") -> dict:
    directory, entries, release = snapshot_release(dataset_dir)
    catalogue = company_universe()
    snapshot_tickers = set()
    for _, payload, digest in entries:
        snapshot_tickers.update(_parquet(digest, payload).ticker.unique())
    selected = sorted(set(tickers) if tickers is not None else set(catalogue.index) | snapshot_tickers)
    raw, sources = load_raw(selected, start, end, as_of=as_of, dataset_dir=directory,
                            filing_dir=filing_dir, period_type=period_type)
    by_ticker = {ticker: group for ticker, group in raw.groupby("ticker")} if not raw.empty else {}
    rows = []
    for ticker in selected:
        group = by_ticker.get(ticker, pd.DataFrame())
        record = {"ticker": ticker, "identity_status": "catalog_unverified" if ticker in catalogue.index else "unknown",
                  "has_legacy_snapshot": ticker in snapshot_tickers, "period_type": period_type,
                  "years_present": sorted(int(y) for y in group.year.unique()) if not group.empty else [],
                  "status": "unavailable", "periods": []}
        if not group.empty:
            if period_type == "annual":
                try:
                    observations = extract_facts(group, ticker)
                    for observation in observations:
                        states = {key: metadata.get("status", "missing") for key, metadata in observation["fact_metadata"].items()}
                        verified = [key for key, metadata in observation["fact_metadata"].items()
                                    if metadata.get("verification_status") == "verified" and metadata.get("status") == "usable"]
                        record["periods"].append({"year": observation["year"], "fact_states": states,
                                                  "verified_facts": verified, "quality_issues": observation["quality_issues"],
                                                  "source_ids": observation["source_ids"]})
                except ValueError as exc:
                    record["error"] = str(exc)
            else:
                record["periods"] = group[["year", "period_start", "period_end", "published_on", "report_basis", "verification_status"]].drop_duplicates().where(pd.notna(group), None).to_dict("records")
            record["status"] = "partial"
        rows.append(record)
    return {"schema_version": "1.0.0", "dataset_version": release, "start_year": start, "end_year": end,
            "as_of": as_of.isoformat() if as_of else None, "period_type": period_type,
            "catalogue_tickers": len(catalogue), "snapshot_tickers": len(snapshot_tickers),
            "catalogue_without_legacy_snapshot": len(set(catalogue.index) - snapshot_tickers),
            "snapshot_without_catalogue": sorted(snapshot_tickers - set(catalogue.index)),
            "queried_tickers": len(selected), "available_tickers": sum(row["status"] != "unavailable" for row in rows),
            "sources": [source.model_dump(mode="json") for source in sources], "rows": rows,
            "note": "Coverage is not independent verification. No unknown value is replaced by zero; no listing history is invented."}

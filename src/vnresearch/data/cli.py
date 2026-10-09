import argparse
from datetime import date
import json
from pathlib import Path

from vnresearch.data.coverage import coverage_report
from vnresearch.data.autoload import ensure_fixture_filings
from vnresearch.data.filings import import_filing, validate_filing
from vnresearch.data.providers import MarketConfig, capabilities, fetch_prices
from vnresearch.data.snapshots import read_release, seal_release


def main():
    parser = argparse.ArgumentParser(prog="python -m vnresearch.data.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    importing = commands.add_parser("import-filing")
    importing.add_argument("metadata", type=Path)
    importing.add_argument("--directory", type=Path, required=True)
    importing.add_argument("--original-document", type=Path)
    bootstrap = commands.add_parser("bootstrap-filings")
    bootstrap.add_argument("--ticker", required=True)
    bootstrap.add_argument("--directory", type=Path, required=True)
    bootstrap.add_argument("--start-year", type=int, default=2024)
    bootstrap.add_argument("--end-year", type=int, default=2025)
    bootstrap.add_argument("--as-of", type=date.fromisoformat, required=True)
    bootstrap.add_argument("--original-cache", type=Path)
    bootstrap.add_argument("--period-type", choices=["annual", "half_year", "quarterly"], default="annual")
    sealing = commands.add_parser("seal-snapshot")
    sealing.add_argument("source", type=Path)
    sealing.add_argument("--directory", type=Path, required=True)
    validating = commands.add_parser("validate")
    target = validating.add_mutually_exclusive_group(required=True)
    target.add_argument("--snapshot", type=Path)
    target.add_argument("--filing", type=Path)
    validating.add_argument("--original-document", type=Path)
    coverage = commands.add_parser("coverage")
    coverage.add_argument("--ticker", action="append")
    coverage.add_argument("--start-year", type=int, default=2024)
    coverage.add_argument("--end-year", type=int, default=2025)
    coverage.add_argument("--as-of", type=date.fromisoformat)
    coverage.add_argument("--period-type", choices=["annual", "half_year", "quarterly"], default="annual")
    coverage.add_argument("--dataset-dir", type=Path)
    coverage.add_argument("--filing-dir", type=Path)
    coverage.add_argument("--output", type=Path)
    commands.add_parser("capabilities")
    fetching = commands.add_parser("fetch-prices")
    fetching.add_argument("--ticker", required=True)
    fetching.add_argument("--start", type=date.fromisoformat, required=True)
    fetching.add_argument("--end", type=date.fromisoformat, required=True)
    fetching.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "import-filing":
            result = {"release": str(import_filing(args.metadata, args.directory, original_document=args.original_document).resolve())}
        elif args.command == "bootstrap-filings":
            result = ensure_fixture_filings(args.directory, args.ticker, args.start_year, args.end_year,
                                            args.as_of, original_cache=args.original_cache, period_type=args.period_type)
        elif args.command == "seal-snapshot":
            result = {"release": str(seal_release(args.source, args.directory).resolve())}
        elif args.command == "validate":
            if args.snapshot:
                entries, version = read_release(args.snapshot)
                result = {"dataset_version": version, "files": len(entries), "integrity": "checked", "financial_accuracy": "not_certified"}
            else:
                original = args.original_document.read_bytes() if args.original_document else None
                item = validate_filing(json.loads(args.filing.read_text(encoding="utf-8")), original)
                result = {"ticker": item["ticker"], "facts": len(item["facts"]), "verification_status": item["verification_status"]}
        elif args.command == "coverage":
            if args.start_year > args.end_year:
                raise ValueError("Khoảng năm không hợp lệ")
            result = coverage_report(tickers=args.ticker, start=args.start_year, end=args.end_year,
                                     as_of=args.as_of, dataset_dir=args.dataset_dir, filing_dir=args.filing_dir,
                                     period_type=args.period_type)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8", newline="\n")
                result = {"output": str(args.output.resolve()), "queried_tickers": result["queried_tickers"], "available_tickers": result["available_tickers"]}
        elif args.command == "fetch-prices":
            frame, metadata = fetch_prices(args.ticker, args.start, args.end, config=MarketConfig(archive_dir=args.directory))
            args.directory.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.directory / "prices.csv", index=False, lineterminator="\n")
            (args.directory / "provider.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8", newline="\n")
            result = {"rows": len(frame), "output": str(args.directory.resolve()), "provider": metadata}
        else:
            result = capabilities()
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Data error: {exc}\n")


if __name__ == "__main__":
    main()

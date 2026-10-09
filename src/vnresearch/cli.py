import argparse
from datetime import date
import json
from pathlib import Path
import sys

from vnresearch.analysis.pipeline import analyze
from vnresearch.domain.models import AnalysisRequest, ValuationAssumptions, today
from vnresearch.platform.settings import Settings, require_local_bind
from vnresearch.reports.export import export_report


def main():
    parser = argparse.ArgumentParser(prog="vnresearch")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Khởi động Web và API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    report = commands.add_parser("report", help="Tạo báo cáo từ CLI")
    report.add_argument("--ticker", required=True)
    report.add_argument("--mode", choices=["demo", "snapshot", "live"], default="live")
    report.add_argument("--as-of", type=date.fromisoformat, default=today())
    report.add_argument("--start-year", type=int, default=2021)
    report.add_argument("--end-year", type=int, default=2025)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--prices-csv", type=Path)
    report.add_argument("--macro-csv", type=Path)
    report.add_argument("--news-csv", type=Path)
    report.add_argument("--target-pe", type=float)
    report.add_argument("--ai", action=argparse.BooleanOptionalAction, default=None,
                        help="Mặc định tự gọi LLM trong chế độ thực; --no-ai tắt rõ ràng")
    report.add_argument("--jev", action=argparse.BooleanOptionalAction, default=None,
                        help="Mặc định tự gọi Jev trong chế độ thực; --no-jev tắt rõ ràng")
    inspect = commands.add_parser("inspect-pdf", help="Trích bằng chứng theo trang, đánh dấu trang cần OCR")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--annual-report", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn
            from vnresearch.api.app import create_app
            settings = Settings.from_env()
            require_local_bind(args.host, settings)
            uvicorn.run(create_app(settings), host=args.host, port=args.port)
        elif args.command == "inspect-pdf":
            from vnresearch.intelligence.documents import inspect_document
            print(json.dumps(inspect_document(args.path, args.annual_report), ensure_ascii=False, indent=2))
        else:
            flags = {key: value for key, value in {"use_ai": args.ai, "use_jev": args.jev}.items() if value is not None}
            request = AnalysisRequest(ticker=args.ticker, as_of=args.as_of, mode=args.mode,
                                      start_year=args.start_year, end_year=args.end_year,
                                      **flags,
                                      valuation=ValuationAssumptions(target_pe=args.target_pe))
            inputs = {kind: path for kind, path in {"prices": args.prices_csv, "macro": args.macro_csv, "news": args.news_csv}.items() if path}
            result = analyze(request, inputs, lambda phase, percent: print(f"{percent:3}% {phase}", file=sys.stderr))
            manifest = export_report(result, args.output)
            print(json.dumps({"ticker": result.ticker, "status": result.status,
                              "mode": args.mode, "output": str(args.output.resolve()), "files": manifest["files"]}, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

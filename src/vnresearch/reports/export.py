import hashlib
from pathlib import Path

from vnresearch.domain.models import Report
from vnresearch.platform.jobs import atomic_json
from vnresearch.reports.pdf import render_pdf


def export_report(report: Report, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "report.json", report.model_dump(mode="json"))
    render_pdf(report, directory / "report.pdf")
    manifest = {"schema_version": "1.0.0", "ticker": report.ticker, "mode": report.request.mode.value,
                "status": report.status, "sources": [source.model_dump(mode="json") for source in report.sources],
                "files": {name: {"sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
                                 "bytes": (directory / name).stat().st_size}
                          for name in ["report.json", "report.pdf"]}}
    atomic_json(directory / "manifest.json", manifest)
    return manifest

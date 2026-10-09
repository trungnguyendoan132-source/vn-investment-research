"""TV6 Demo Artifacts QA Test Suite."""
import hashlib
import json
from pathlib import Path

import pymupdf
from reportlab.graphics.shapes import Rect
from reportlab.lib import colors
from vnresearch.domain.models import Report
from vnresearch.reports.export import export_report
from vnresearch.reports.pdf import render_pdf_to_images, revenue_chart

root_dir = Path(__file__).resolve().parents[1]


def test_demo_fixture_structure():
    candidates = [
        root_dir / "demo/fixtures/demo_report.json",
        root_dir / "repo/demo/fixtures/demo_report.json",
        root_dir / "TV6/demo_report.json",
    ]
    fixture_file = next((c for c in candidates if c.exists()), None)
    assert fixture_file is not None, "demo_report.json must exist"
    data = json.loads(fixture_file.read_text(encoding="utf-8"))
    report = Report.model_validate(data)
    assert report.ticker in {"FPT", "FMC", "VCB", "HPG"}
    assert report.request.mode.value == "demo"
    assert len(report.sections) >= 3


def test_checked_in_demo_artifact_matches_its_manifest():
    artifact_dir = root_dir / "docs/evidence/tv6-demo"
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    for name, metadata in manifest["files"].items():
        artifact = artifact_dir / name
        assert artifact.stat().st_size == metadata["bytes"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == metadata["sha256"]


def test_pdf_export_and_clean_unicode(tmp_path):
    fixture_file = root_dir / "demo/fixtures/demo_report.json"
    data = json.loads(fixture_file.read_text(encoding="utf-8"))
    report = Report.model_validate(data)

    manifest = export_report(report, tmp_path)
    pdf_file = tmp_path / "report.pdf"
    assert pdf_file.exists()
    assert pdf_file.stat().st_size > 10000

    # Test manifest SHA256 integrity
    for name, meta in manifest["files"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == meta["sha256"]

    # Test PDF text and render images
    images = render_pdf_to_images(pdf_file, tmp_path / "images")
    assert len(images) >= 3

    with pymupdf.open(pdf_file) as doc:
        for idx, page in enumerate(doc):
            text = page.get_text()
            assert "\ufffd" not in text, f"Unicode replacement character on page {idx + 1}"
            assert "\u25a0" not in text, f"Missing square symbol on page {idx + 1}"
            assert "MINH HỌA" in text or "giả lập" in text, f"Missing demo warning on page {idx + 1}"


def test_pdf_chart_draws_losses_below_zero_baseline():
    from types import SimpleNamespace

    report = SimpleNamespace(financial_years=[
        SimpleNamespace(year=2024, facts={"revenue": 100_000_000_000, "net_income": 10_000_000_000}),
        SimpleNamespace(year=2025, facts={"revenue": 110_000_000_000, "net_income": -8_000_000_000}),
    ])
    chart = revenue_chart(report)
    loss_color = colors.HexColor("#DC2626")
    loss_bars = [shape for shape in chart.contents
                 if isinstance(shape, Rect) and shape.fillColor == loss_color and shape.y < 110]
    assert len(loss_bars) == 1

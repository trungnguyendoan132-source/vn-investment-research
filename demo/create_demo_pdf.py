"""TV6 Demo Artifacts Generator & PDF Image QA Validator.
Tạo báo cáo PDF demo, trích xuất hình ảnh kiểm tra từng trang, và kiểm tra mã băm SHA-256.
"""
import hashlib
import json
from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure src is on sys.path
root_dir = Path(__file__).resolve().parents[1]
for src_candidate in [root_dir / "src", root_dir / "repo/src"]:
    if src_candidate.exists() and str(src_candidate) not in sys.path:
        sys.path.insert(0, str(src_candidate))

import pymupdf
from vnresearch.domain.models import Report
from vnresearch.reports.export import export_report
from vnresearch.reports.pdf import render_pdf_to_images


def main():
    candidates = [
        root_dir / "demo/fixtures/demo_report.json",
        root_dir / "repo/demo/fixtures/demo_report.json",
        root_dir / "TV6/demo_report.json",
    ]
    fixture_file = next((c for c in candidates if c.exists()), None)
    if not fixture_file:
        print(f"Error: Fixture demo_report.json not found in {candidates}")
        sys.exit(1)

    data = json.loads(fixture_file.read_text(encoding="utf-8"))
    report = Report.model_validate(data)

    out_dir = root_dir / "var/demo-FPT"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = export_report(report, out_dir)
    pdf_path = out_dir / "report.pdf"

    print(f"[OK] Đã xuất báo cáo PDF: {pdf_path}")
    print(f"[OK] Kích thước PDF: {pdf_path.stat().st_size:,} bytes")

    # Render ảnh từng trang bằng PyMuPDF
    img_dir = out_dir / "images"
    images = render_pdf_to_images(pdf_path, img_dir, dpi=150)
    print(f"[OK] Đã render {len(images)} trang ảnh QA:")
    for img in images:
        print(f"     - {img.name} ({img.stat().st_size:,} bytes)")

    # Kiểm tra text không có lỗi Unicode
    with pymupdf.open(pdf_path) as doc:
        for idx, page in enumerate(doc):
            text = page.get_text()
            assert "\ufffd" not in text, f"Lỗi font Unicode (ký tự thay thế) tại trang {idx + 1}"
            assert "\u25a0" not in text, f"Lỗi font (ô vuông khuyết) tại trang {idx + 1}"
            if report.request.mode.value == "demo":
                assert "MINH HỌA" in text or "giả lập" in text, f"Thiếu nhãn minh họa tại trang {idx + 1}"

    print(f"[OK] Kiểm tra Unicode: Hoàn toàn không có lỗi font hoặc ký tự thay thế.")
    print(f"[OK] SHA-256 PDF: {manifest['files']['report.pdf']['sha256']}")
    print(f"[OK] SHA-256 JSON: {manifest['files']['report.json']['sha256']}")


if __name__ == "__main__":
    main()

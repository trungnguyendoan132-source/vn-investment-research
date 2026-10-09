from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, KeepTogether

from vnresearch.domain.models import Mode, Report
from vnresearch.platform.settings import ASSETS


NAVY, TEAL, GRAY = colors.HexColor("#132B45"), colors.HexColor("#008F86"), colors.HexColor("#64748B")
pdfmetrics.registerFont(TTFont("VNResearch", str(ASSETS / "fonts/DejaVuSans.ttf")))
pdfmetrics.registerFontFamily("VNResearch", normal="VNResearch", bold="VNResearch", italic="VNResearch", boldItalic="VNResearch")
STYLES = getSampleStyleSheet()
for name in ["Normal", "Title", "Heading1", "Heading2", "BodyText"]:
    STYLES[name].fontName = "VNResearch"
STYLES["Normal"].fontSize = 9
STYLES["Normal"].leading = 14
STYLES["Title"].fontSize = 22
STYLES["Title"].leading = 29
STYLES["Title"].alignment = TA_LEFT
STYLES["Title"].textColor = NAVY
STYLES["Heading1"].fontSize = 13
STYLES["Heading1"].leading = 19
STYLES["Heading1"].textColor = NAVY
STYLES["Heading1"].spaceBefore = 15
STYLES["Heading1"].spaceAfter = 7
SMALL = ParagraphStyle("SmallVN", parent=STYLES["Normal"], fontSize=7.5, leading=11, textColor=GRAY, wordWrap="CJK")


def paragraph(value, style=None, raw_html=False):
    text = str(value).replace("\n", "<br/>") if raw_html else escape(str(value)).replace("\n", "<br/>")
    return Paragraph(text, style or STYLES["Normal"])


def formatted(value):
    if value is None:
        return "Chưa có dữ liệu"
    if isinstance(value, float):
        return f"{value:,.3f}" if abs(value) < 100 else f"{value:,.0f}"
    return str(value)


def table(rows, widths=None):
    keys = list(rows[0])
    num_cols = len(keys)
    if widths is None:
        if num_cols == 2:
            widths = [180, 331]
        elif num_cols == 3:
            widths = [150, 150, 211]
        elif num_cols == 4:
            widths = [160, 120, 70, 161]
        elif num_cols == 5:
            widths = [110, 100, 100, 100, 101]
        else:
            widths = [511 / num_cols] * num_cols
    cells = [[paragraph(key, SMALL) for key in keys]]
    cells.extend([[paragraph(formatted(row.get(key)), SMALL) for key in keys] for row in rows])
    obj = LongTable(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    obj.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5F2F1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEAL),
    ]))
    return obj


def revenue_chart(report: Report):
    rev_obs = [(row.year, row.facts.get("revenue")) for row in report.financial_years]
    rev_obs = [(y, v / 1e9) for y, v in rev_obs if v is not None and v >= 0]
    ni_obs = {
        row.year: row.facts.get("net_income") / 1e9 if row.facts.get("net_income") is not None else None
        for row in report.financial_years
    }
    if len(rev_obs) < 2:
        return None
    maximum = max([value for _, value in rev_obs] + [abs(value) for value in ni_obs.values() if value is not None]) or 1
    drawing = Drawing(511, 220)
    baseline = 110
    scale = 70 / maximum
    num_years = len(rev_obs)
    slot_width = 460 / num_years
    bar_width = min(24, slot_width * 0.32)
    drawing.add(Line(20, baseline, 490, baseline, strokeColor=GRAY, strokeWidth=0.7))
    for index, (year, rev_val) in enumerate(rev_obs):
        base_left = 32 + index * slot_width
        rev_height = rev_val * scale
        drawing.add(Rect(base_left, baseline, bar_width, rev_height, fillColor=TEAL, strokeColor=None))
        drawing.add(String(base_left, baseline + rev_height + 4, f"{rev_val:,.0f}", fontName="VNResearch", fontSize=7, fillColor=NAVY))
        ni_val = ni_obs.get(year)
        if ni_val is not None:
            ni_left = base_left + bar_width + 3
            is_loss = ni_val < 0
            ni_height = abs(ni_val) * scale
            ni_y = baseline - ni_height if is_loss else baseline
            ni_color = colors.HexColor("#DC2626") if is_loss else NAVY
            label_y = ni_y - 12 if is_loss else ni_y + ni_height + 4
            drawing.add(Rect(ni_left, ni_y, bar_width, ni_height, fillColor=ni_color, strokeColor=None))
            drawing.add(String(ni_left, label_y, f"{ni_val:,.0f}", fontName="VNResearch", fontSize=7, fillColor=ni_color))
        drawing.add(String(base_left + bar_width * 0.5, 8, str(year), fontName="VNResearch", fontSize=8, fillColor=GRAY))
    drawing.add(String(0, 210, "Doanh thu & LNST qua các năm (tỷ VND); giá trị âm nằm dưới mốc 0", fontName="VNResearch", fontSize=9, fillColor=NAVY))
    drawing.add(Rect(325, 193, 8, 8, fillColor=TEAL, strokeColor=None))
    drawing.add(String(337, 194, "Doanh thu", fontName="VNResearch", fontSize=7.5, fillColor=NAVY))
    drawing.add(Rect(397, 193, 8, 8, fillColor=NAVY, strokeColor=None))
    drawing.add(String(409, 194, "LNST", fontName="VNResearch", fontSize=7.5, fillColor=NAVY))
    drawing.add(Rect(452, 193, 8, 8, fillColor=colors.HexColor("#DC2626"), strokeColor=None))
    drawing.add(String(464, 194, "Lỗ", fontName="VNResearch", fontSize=7.5, fillColor=colors.HexColor("#B91C1C")))
    return drawing


def render_pdf_to_images(pdf_path: Path, output_dir: Path | None = None, dpi: int = 150) -> list[Path]:
    import pymupdf
    dest = output_dir or pdf_path.parent / "pdf_pages"
    dest.mkdir(parents=True, exist_ok=True)
    images = []
    with pymupdf.open(pdf_path) as doc:
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            img_file = dest / f"page_{page_idx + 1}.png"
            pix.save(str(img_file))
            images.append(img_file)
    return images


def render_pdf(report: Report, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".pdf.tmp")
    story = [paragraph("VN EQUITY LAB", STYLES["Heading1"]),
             paragraph(f"{report.ticker} | Báo cáo phân tích đầu tư", STYLES["Title"]),
             paragraph(f"<b>{escape(report.company_name)}</b> · Ngành: {escape(report.sector_name)}", raw_html=True),
             paragraph(f"Ngày chốt dữ liệu: {report.request.as_of} | Hồ sơ rủi ro: {report.request.risk_profile} | Tầm nhìn: {report.request.horizon_months} tháng"),
             Spacer(1, 10)]

    decision_box = [
        {"Hạng mục": "Quyết định & Khuyến nghị", "Chi tiết": report.decision},
        {"Hạng mục": "Trạng thái báo cáo", "Chi tiết": f"{report.status.upper()} (Chế độ: {report.request.mode.value.upper()})"},
    ]
    story += [table(decision_box, [140, 371]), Spacer(1, 8)]

    if report.request.mode == Mode.DEMO:
        story += [
            paragraph("<b>⚠️ BÁO CÁO MINH HỌA - DỮ LIỆU GIẢ LẬP:</b> Giá, vĩ mô và tin tức trong chế độ demo là dữ liệu giả lập có nhãn. BCTC là snapshot kế thừa. Không dùng báo cáo này để đưa ra quyết định đầu tư thực tế.",
                      ParagraphStyle("DemoWarning", parent=STYLES["Normal"], textColor=colors.HexColor("#DC2626"), fontSize=8, leading=12), raw_html=True),
            Spacer(1, 8)
        ]

    story += [paragraph("Điều kiện cơ hội cần kiểm chứng", STYLES["Heading1"])]
    story += [paragraph("• " + item) for item in report.opportunities]
    story += [paragraph("Rủi ro và giả định", STYLES["Heading1"])]
    story += [paragraph("• " + item) for item in report.risks]

    for key, section in report.sections.items():
        story += [paragraph(section.title, STYLES["Heading1"]), paragraph(section.summary),
                  paragraph("Nguồn: " + (", ".join(section.source_ids) or "Chưa có"), SMALL), Spacer(1, 6)]
        if key == "financial":
            chart = revenue_chart(report)
            if chart:
                story.append(chart)
        if section.rows:
            rows = section.rows[:14] if key == "sector" else section.rows
            widths = [160, 120, 70, 161] if key == "financial" else None
            story.append(table(rows, widths))
            if key == "sector" and len(section.rows) > 14:
                story.append(paragraph(f"Hiển thị 14/{len(section.rows)} dòng; bảng đầy đủ nằm trong report.json.", SMALL))
        if key == "news":
            for article in report.news:
                for snippet in article.snippets[:2]:
                    story += [Spacer(1, 5), paragraph(f"[{article.source_id}] {snippet}", SMALL)]

    if report.request.use_ai:
        story += [paragraph("Tổng hợp bằng API AI", STYLES["Heading1"]), paragraph(report.ai.get("note", ""), SMALL)]
        for claim in report.ai.get("claims", []):
            story.append(paragraph(claim["text"] + " [" + ", ".join(claim["source_ids"]) + "]"))

    if report.request.use_jev:
        story += [paragraph("Quyết định nghiên cứu từ Jev", STYLES["Heading1"]), paragraph(report.jev.get("note", ""), SMALL)]
        if report.jev.get("status") == "ok":
            story.append(table([{"Jev đề xuất": report.jev["proposed_decision"], "Sau kiểm tra dữ liệu": report.jev["applied_decision"],
                                 "Confidence model": report.jev["confidence"], "Cần review": str(report.jev["review_required"])}]))

    story += [paragraph("Chất lượng dữ liệu và giới hạn kiểm chứng", STYLES["Heading1"])]
    story += [paragraph(f"[{issue.severity.upper()}] {issue.code}: {issue.message}", SMALL) for issue in report.issues]

    story += [paragraph("Danh mục nguồn", STYLES["Heading1"])]
    for source in report.sources:
        lines = [paragraph(f"[{source.id}] {source.title}", SMALL),
                 paragraph(f"Loại: {source.kind} | Kỳ: {source.period or 'xem tài liệu'} | Đọc/tải: {source.retrieved_at.isoformat()}", SMALL),
                 paragraph(source.url, SMALL)]
        lines.append(paragraph(f"Kiểm chứng: {source.verification_status} | Phạm vi: {source.report_basis} | Kỳ: {source.period_type}", SMALL))
        if source.published_on or source.published_at:
            lines.append(paragraph(f"Công bố: {source.published_at.isoformat() if source.published_at else source.published_on} | Độ chính xác: {source.publication_precision}", SMALL))
        if source.note:
            lines.append(paragraph(source.note, SMALL))
        if source.sha256:
            lines.append(paragraph("SHA-256: " + source.sha256, SMALL))
        story += [KeepTogether(lines), Spacer(1, 6)]

    def page_frame(canvas, doc):
        canvas.saveState()
        if report.request.mode == Mode.DEMO:
            canvas.saveState()
            canvas.setFont("VNResearch", 36)
            canvas.setFillColor(colors.HexColor("#F8FAFC"))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "DỮ LIỆU MINH HỌA - CHẠY OFFLINE")
            canvas.restoreState()

        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 28, A4[0], 28, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("VNResearch", 8)
        tag = " | BÁO CÁO MINH HỌA" if report.request.mode == Mode.DEMO else ""
        canvas.drawString(42, A4[1] - 18, f"VN EQUITY LAB | {report.ticker}{tag}")
        canvas.setFillColor(GRAY)
        canvas.drawString(42, 24, f"{report.request.as_of} | {report.status.upper()}")
        canvas.drawRightString(A4[0] - 42, 24, f"Trang {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=42, rightMargin=42,
                      topMargin=46, bottomMargin=42, title=f"VN Equity Lab - {report.ticker}",
                      author="VN Equity Lab").build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    temporary.replace(output)
    return output

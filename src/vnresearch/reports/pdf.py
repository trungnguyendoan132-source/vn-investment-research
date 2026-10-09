from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect, String
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


def paragraph(value, style=None):
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style or STYLES["Normal"])


def formatted(value):
    if value is None:
        return "Chưa có dữ liệu"
    if isinstance(value, float):
        return f"{value:,.3f}" if abs(value) < 100 else f"{value:,.0f}"
    return str(value)


def table(rows, widths=None):
    keys = list(rows[0])
    cells = [[paragraph(key, SMALL) for key in keys]]
    cells.extend([[paragraph(formatted(row.get(key)), SMALL) for key in keys] for row in rows])
    obj = LongTable(cells, colWidths=widths or [511 / len(keys)] * len(keys), repeatRows=1, hAlign="LEFT")
    obj.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5F2F1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEAL),
    ]))
    return obj


def revenue_chart(report: Report):
    observations = [(row.year, row.facts.get("revenue")) for row in report.financial_years]
    observations = [(year, value / 1e9) for year, value in observations if value is not None and value >= 0]
    if len(observations) < 2:
        return None
    drawing = Drawing(511, 160)
    maximum = max(value for _, value in observations) or 1
    bar_width = min(62, 400 / len(observations))
    for index, (year, value) in enumerate(observations):
        left = 32 + index * (455 / len(observations))
        height = value / maximum * 105
        drawing.add(Rect(left, 25, bar_width, height, fillColor=TEAL, strokeColor=None))
        drawing.add(String(left, 10, str(year), fontName="VNResearch", fontSize=8, fillColor=GRAY))
        drawing.add(String(left, height + 32, f"{value:,.0f}", fontName="VNResearch", fontSize=8, fillColor=NAVY))
    drawing.add(String(0, 148, "Doanh thu / Tổng thu nhập hoạt động (tỷ VND)", fontName="VNResearch", fontSize=9, fillColor=NAVY))
    return drawing


def render_pdf(report: Report, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".pdf.tmp")
    story = [paragraph("VN EQUITY LAB", STYLES["Heading1"]),
             paragraph(f"{report.ticker} | Báo cáo phân tích đầu tư", STYLES["Title"]),
             paragraph(report.company_name), paragraph(f"Ngành: {report.sector_name}"),
             paragraph(f"Ngày chốt: {report.request.as_of} | Hồ sơ: {report.request.risk_profile} | Tầm nhìn: {report.request.horizon_months} tháng"),
             Spacer(1, 10), paragraph(report.decision), Spacer(1, 8)]
    if report.request.mode == Mode.DEMO:
        story += [paragraph("DỮ LIỆU MINH HỌA: giá, vĩ mô và tin tức giả lập; BCTC là snapshot kế thừa. Không dùng báo cáo này để quyết định đầu tư."), Spacer(1, 8)]
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
            widths = [165, 120, 50, 176] if key == "financial" else None
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
        if source.note:
            lines.append(paragraph(source.note, SMALL))
        if source.sha256:
            lines.append(paragraph("SHA-256: " + source.sha256, SMALL))
        story += [KeepTogether(lines), Spacer(1, 6)]

    def page_frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 28, A4[0], 28, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("VNResearch", 8)
        tag = " | MINH HỌA" if report.request.mode == Mode.DEMO else ""
        canvas.drawString(42, A4[1] - 18, f"VN EQUITY LAB | {report.ticker}{tag}")
        canvas.setFillColor(GRAY)
        canvas.drawString(42, 24, f"{report.request.as_of} | {report.status}")
        canvas.drawRightString(A4[0] - 42, 24, f"Trang {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=42, rightMargin=42,
                      topMargin=46, bottomMargin=42, title=f"VN Equity Lab - {report.ticker}",
                      author="VN Equity Lab").build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    temporary.replace(output)
    return output

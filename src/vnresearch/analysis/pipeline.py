from collections.abc import Callable
from datetime import date
import json
from pathlib import Path

from vnresearch.analysis.financial import financial_analysis
from vnresearch.analysis.valuation import value_company
from vnresearch.data.fundamentals import company, extract_facts, load_raw
from vnresearch.data.market import load_prices
from vnresearch.domain.models import AnalysisRequest, Mode, QualityIssue, Report, Section
from vnresearch.intelligence.news import load_news
from vnresearch.macro.provider import load_macro
from vnresearch.sector.compare import compare_sector
from vnresearch.platform.settings import ASSETS


def analyze(request: AnalysisRequest, input_paths: dict[str, Path] | None = None,
            progress: Callable[[str, int], None] | None = None) -> Report:
    inputs, issues, sources, sections = input_paths or {}, [], {}, {}
    progress = progress or (lambda phase, percent: None)

    def add_sources(items):
        for source in items:
            sources[source.id] = source

    def issue(component, exc):
        issues.append(QualityIssue(code="SOURCE_OR_VALIDATION_FAILED", component=component,
                                   message=str(exc), severity="error"))

    progress("financial", 10)
    profile = company(request.ticker)
    is_bank = profile["industry"] == "Ngân hàng" or profile["sector"] == "Ngân hàng"
    annual_end = min(request.end_year, request.as_of.year - 1)
    raw, source_items = load_raw([request.ticker], request.start_year - 1, annual_end)
    add_sources(source_items)
    computed = financial_analysis(extract_facts(raw, request.ticker), is_bank=is_bank)
    years = [row for row in computed if row.year >= request.start_year]
    latest = years[-1] if years else None
    financial_rows = []
    if latest:
        financial_rows = [{"Chỉ tiêu": metric.label, "Giá trị": metric.value,
                           "Đơn vị": metric.unit, "Công thức": metric.formula} for metric in latest.metrics]
        financial_rows += [{"Chỉ tiêu": label, "Giá trị": latest.facts.get(key), "Đơn vị": "VND", "Công thức": "Giá trị BCTC gốc"}
                           for key, label in [("revenue", "Doanh thu / Tổng thu nhập hoạt động"), ("net_income", "Lợi nhuận sau thuế"), ("total_assets", "Tổng tài sản"), ("equity", "Vốn chủ sở hữu")]]
    sections["financial"] = Section(title="Phân tích doanh nghiệp", status="ok" if latest else "unavailable",
                                    summary=f"BCTC năm {latest.year}, {len(years)} năm có dữ liệu. ROA/ROE dùng số bình quân; công thức tài chính không dùng LLM." if latest else "Không có BCTC cho mã và kỳ yêu cầu trong snapshot.",
                                    rows=financial_rows, source_ids=latest.source_ids if latest else [])
    issues.append(QualityIssue(code="SNAPSHOT_PROVENANCE", component="financial",
                              message="BCTC kế thừa là snapshot tối đa 2025; chưa đối chiếu độc lập báo cáo công bố và thời điểm công bố. Không dùng cho backtest point-in-time."))
    if latest and latest.year < annual_end:
        issues.append(QualityIssue(code="STALE_FINANCIAL_YEAR", component="financial",
                                  message=f"Kỳ BCTC gần nhất là {latest.year}; yêu cầu đến {annual_end}."))
    progress("market", 25)
    try:
        prices, source_items, sections["market"] = load_prices(request.ticker, request.as_of, request.mode, inputs.get("prices"))
        add_sources(source_items)
    except Exception as exc:
        import pandas as pd
        prices = pd.DataFrame()
        issue("market", exc)
        sections["market"] = Section(title="Giá và giao dịch", status="unavailable", summary=str(exc))
    progress("macro", 40)
    try:
        source_items, sections["macro"] = load_macro(request.as_of, request.mode, inputs.get("macro"))
        add_sources(source_items)
    except Exception as exc:
        issue("macro", exc)
        sections["macro"] = Section(title="Tổng quan vĩ mô", status="unavailable", summary=str(exc))
    progress("sector", 55)
    try:
        source_items, sections["sector"] = compare_sector(request.ticker, profile["sector"], latest.year if latest else annual_end, is_bank)
        add_sources(source_items)
    except Exception as exc:
        issue("sector", exc)
        sections["sector"] = Section(title="Phân tích ngành", status="unavailable", summary=str(exc))
    progress("news", 70)
    try:
        news, source_items, sections["news"] = load_news(request.ticker, request.as_of, request.mode, request.news_limit, inputs.get("news"))
        add_sources(source_items)
    except Exception as exc:
        issue("news", exc)
        news = []
        sections["news"] = Section(title="Tin tức và bằng chứng", status="unavailable", summary=str(exc))
    progress("valuation", 80)
    sections["valuation"] = value_company(latest, prices, request.valuation, request.as_of, is_bank=is_bank)
    opportunities, risks = [], []
    if latest:
        metrics = {metric.key: metric.value for metric in latest.metrics}
        growth = metrics.get("revenue_growth_yoy")
        roe = metrics.get("roe")
        cfo_ratio = metrics.get("cfo_to_income")
        fcf = metrics.get("fcf")
        if growth is not None and growth > 0:
            opportunities.append(f"Động lực tăng trưởng (Catalyst): Doanh thu/tổng thu nhập hoạt động tăng {growth:.1%} năm {latest.year}; cần đối chiếu tính bền vững và nguyên nhân tăng trưởng.")
        if roe is not None and roe > 0:
            opportunities.append(f"Hiệu quả sinh lời: ROE bình quân đạt {roe:.1%}; dùng bảng ngành cùng năm để đánh giá vị thế tương đối.")
        if fcf is not None and fcf > 0:
            opportunities.append(f"Chất lượng dòng tiền: Dòng tiền tự do (FCF) dương năm {latest.year}, củng cố năng lực tài chính và khả năng chi trả cổ tức.")
        opportunities.append(f"Tầm nhìn đầu tư: {request.horizon_months} tháng theo khẩu vị {request.risk_profile}; nhận định phụ thuộc vào việc hiện thực hóa kế hoạch lợi nhuận.")
        threshold = {"conservative": 1.0, "balanced": 0.8, "growth": 0.5}[request.risk_profile]
        if cfo_ratio is not None and cfo_ratio < threshold and latest.facts.get("net_income", 0) > 0:
            risks.append(f"Rủi ro dòng tiền: CFO/LNST = {cfo_ratio:.2f}, dưới ngưỡng sàng lọc {threshold:.2f} của hồ sơ {request.risk_profile}; cần đọc thuyết minh lưu chuyển tiền tệ.")
        if latest.facts.get("net_income") is not None and latest.facts["net_income"] < 0:
            risks.append("Doanh nghiệp báo lỗ trong kỳ gần nhất; P/E có thể không có ý nghĩa.")
    if is_bank:
        risks.append("Đặc thù ngân hàng: Cần kiểm tra NIM trên tài sản sinh lãi bình quân, tỷ lệ nợ xấu (NPL) và bao phủ nợ xấu từ nguồn đúng định nghĩa. Không áp hệ số thanh khoản doanh nghiệp sản xuất cho ngân hàng.")
    risks.append("Rủi ro định giá: Bội số thị trường chịu rủi ro biến động lãi suất vĩ mô và thanh khoản chung.")
    missing = [key for key in request.sections if sections[key].status != "ok"]
    for key in missing:
        issues.append(QualityIssue(code="INCOMPLETE_SECTION", component=key, message=sections[key].summary))
    snapshot = json.loads((ASSETS / "snapshot_manifest.json").read_text(encoding="utf-8"))
    if request.as_of < date.fromisoformat(snapshot["captured_on"]):
        issues.append(QualityIssue(code="HISTORICAL_VINTAGE_UNKNOWN", component="financial", severity="error",
                                  message="Ngày chốt lịch sử không bảo đảm dữ liệu đã tồn tại tại thời điểm đó; snapshot không có ngày công bố gốc."))
    if request.mode == Mode.DEMO:
        issues.append(QualityIssue(code="DEMO_DATA", component="report", severity="info", message="Giá, tin và vĩ mô ở chế độ demo là giả lập; BCTC vẫn là snapshot kế thừa."))
        decision = "MINH HỌA - KHÔNG DÙNG ĐỂ QUYẾT ĐỊNH ĐẦU TƯ"
    elif missing or any(i.severity == "error" for i in issues):
        decision = "CHƯA ĐỦ DỮ LIỆU - cần hoàn tất kiểm chứng và các mục còn thiếu trước khi nhận định đầu tư."
    else:
        decision = "Đã có các đầu vào phân tích; nhận định đầu tư cần xác minh BCTC, giá, sự kiện và giả định định giá."
    risks += ["Bội số định giá là giả định người dùng, không phải cam kết lợi nhuận.",
              "Thay đổi vốn, cổ tức, chia tách và báo cáo điều chỉnh có thể ảnh hưởng so sánh; cần kiểm tra nguồn trước khi sử dụng."]
    if not opportunities:
        opportunities.append("Chưa xác định điều kiện cơ hội bằng dữ liệu hiện có; không thay dữ liệu thiếu bằng nhận định suy đoán.")
    progress("report", 90)
    report = Report(ticker=request.ticker, company_name=profile["name"], sector_name=profile["sector"], request=request,
                  status="partial" if missing or any(i.severity == "error" for i in issues) else "complete",
                  decision=decision, financial_years=years, sections={key: sections[key] for key in request.sections},
                  news=news if "news" in request.sections else [], sources=list(sources.values()), issues=issues,
                  opportunities=opportunities, risks=risks)
    if request.use_ai:
        from vnresearch.analysis.ai import synthesize
        report.ai = synthesize(report)
        if report.ai["status"] != "ok":
            report.issues.append(QualityIssue(code="AI_UNAVAILABLE", component="ai", message=report.ai["note"]))
            report.status = "partial"
    if request.use_jev:
        from vnresearch.analysis.jev import evaluate
        report.jev = evaluate(report)
        if report.jev["status"] != "ok":
            report.issues.append(QualityIssue(code="JEV_UNAVAILABLE", component="jev", message=report.jev["note"]))
            report.status = "partial"
    return report

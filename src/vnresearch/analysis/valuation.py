from datetime import date

import pandas as pd

from vnresearch.domain.models import FinancialYear, Section, ValuationAssumptions


def value_company(year: FinancialYear | None, prices: pd.DataFrame, assumptions: ValuationAssumptions,
                  as_of: date, *, require_verified: bool = True) -> Section:
    if year is None or prices.empty:
        return Section(title="Định giá và kịch bản", status="unavailable",
                       summary="Cần BCTC và giá có nguồn. Không tạo giá mục tiêu khi thiếu đầu vào.")
    latest = prices.iloc[-1]
    price = float(latest.close)
    eps = year.facts.get("eps")
    equity = year.facts.get("equity_parent")
    if require_verified:
        if year.fact_metadata.get("eps", {}).get("verification_status") != "verified":
            eps = None
        if year.fact_metadata.get("equity_parent", {}).get("verification_status") != "verified":
            equity = None
    price_basis = prices.attrs.get("price_basis", "unknown")
    price_compatible = not require_verified or price_basis == "raw"
    shares = assumptions.shares_outstanding
    bvps = equity / shares if equity is not None and shares else None
    pe = price / eps if price_compatible and eps is not None and eps > 0 else None
    pb = price / bvps if price_compatible and bvps is not None and bvps > 0 else None
    rows = [{"Chỉ tiêu": "Giá đóng cửa (VND)", "Giá trị": price},
            {"Chỉ tiêu": f"EPS báo cáo năm {year.year} (VND/CP)", "Giá trị": eps},
            {"Chỉ tiêu": f"P/E trên EPS năm {year.year}, không phải TTM", "Giá trị": pe},
            {"Chỉ tiêu": "BVPS (VND/CP), theo số cổ phiếu có nguồn nhập", "Giá trị": bvps},
            {"Chỉ tiêu": "P/B", "Giá trị": pb}]
    for method, multiple, base in [("P/E", assumptions.target_pe, eps), ("P/B", assumptions.target_pb, bvps)]:
        if price_compatible and multiple and base and base > 0:
            scenario_price = multiple * base
            rows += [{"Chỉ tiêu": f"Bội số {method} do người dùng giả định", "Giá trị": multiple},
                     {"Chỉ tiêu": f"Giá kịch bản {method} (VND)", "Giá trị": scenario_price},
                     {"Chỉ tiêu": f"Chênh lệch kịch bản {method} so với giá hiện tại", "Giá trị": scenario_price / price - 1}]
    age = (as_of - latest.date).days
    note = f"Giá ngày {latest.date}, BCTC năm {year.year}. Kịch bản dùng bội số người dùng nhập, không phải giá trị nội tại đã kiểm chứng."
    if assumptions.shares_source:
        note += f" Nguồn số cổ phiếu: {assumptions.shares_source}."
    if age > 7:
        note += f" Giá cách ngày chốt {age} ngày; không đưa ra kết luận dựa trên giá hiện tại."
    if eps is None or eps <= 0:
        note += " EPS thiếu, chưa xác minh hoặc không dương: P/E chưa đủ điều kiện, để trống."
    if not price_compatible:
        note += " Chưa xác minh giá raw cùng cơ sở cổ phiếu với EPS; không dùng giá adjusted/unknown để tính P/E hay chênh lệch kịch bản."
    if bvps is None:
        note += " Thiếu vốn thuộc cổ đông công ty mẹ hoặc số cổ phiếu có nguồn: không tự dùng vốn toàn tập đoàn để tính BVPS."
    return Section(title="Định giá và kịch bản", status="ok" if pe is not None and age <= 7 else "partial",
                   summary=note, rows=rows, source_ids=sorted(set(year.source_ids + ["market"])))

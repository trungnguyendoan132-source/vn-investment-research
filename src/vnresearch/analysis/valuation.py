from datetime import date

import pandas as pd

from vnresearch.domain.models import FinancialYear, Section, ValuationAssumptions


def value_company(year: FinancialYear | None, prices: pd.DataFrame, assumptions: ValuationAssumptions,
                  as_of: date, is_bank: bool = False, sector_pe: float | None = None) -> Section:
    if year is None or prices.empty:
        return Section(title="Định giá và kịch bản", status="unavailable",
                       summary="Cần BCTC và giá có nguồn. Không tạo giá mục tiêu khi thiếu đầu vào.")
    latest = prices.iloc[-1]
    price = float(latest.close)
    eps = year.facts.get("eps")
    equity = year.facts.get("equity_parent")
    shares = assumptions.shares_outstanding
    bvps = equity / shares if equity is not None and shares else None
    pe = price / eps if eps is not None and eps > 0 else None
    pb = price / bvps if bvps is not None and bvps > 0 else None
    rows = [{"Chỉ tiêu": "Giá đóng cửa (VND)", "Giá trị": price},
            {"Chỉ tiêu": f"EPS báo cáo năm {year.year} (VND/CP)", "Giá trị": eps},
            {"Chỉ tiêu": f"P/E trên EPS năm {year.year}, không phải TTM", "Giá trị": pe},
            {"Chỉ tiêu": "BVPS (VND/CP), theo số cổ phiếu có nguồn nhập", "Giá trị": bvps},
            {"Chỉ tiêu": "P/B", "Giá trị": pb}]

    # Kịch bản định giá từ bội số giả định của người dùng
    for method, multiple, base in [("P/E", assumptions.target_pe, eps), ("P/B", assumptions.target_pb, bvps)]:
        if multiple and base and base > 0:
            scenario_price = multiple * base
            scenario_bull = (multiple * 1.15) * base
            scenario_bear = (multiple * 0.85) * base
            rows += [
                {"Chỉ tiêu": f"Bội số {method} do người dùng giả định", "Giá trị": multiple},
                {"Chỉ tiêu": f"Giá kịch bản {method} (VND)", "Giá trị": scenario_price},
                {"Chỉ tiêu": f"Chênh lệch kịch bản {method} so với giá hiện tại", "Giá trị": scenario_price / price - 1},
                {"Chỉ tiêu": f"Kịch bản Khả quan (Bull +15% {method}) (VND)", "Giá trị": scenario_bull},
                {"Chỉ tiêu": f"Kịch bản Thận trọng (Bear -15% {method}) (VND)", "Giá trị": scenario_bear},
                {"Chỉ tiêu": f"Độ nhạy {method} (-10%) (VND)", "Giá trị": (multiple * 0.9) * base},
                {"Chỉ tiêu": f"Độ nhạy {method} (+10%) (VND)", "Giá trị": (multiple * 1.1) * base},
            ]

    # Định giá tham chiếu theo trung vị ngành (nếu có)
    if sector_pe and eps and eps > 0:
        sector_implied_price = sector_pe * eps
        rows += [
            {"Chỉ tiêu": "P/E trung vị ngành tham chiếu", "Giá trị": sector_pe},
            {"Chỉ tiêu": "Giá ngụ ý theo P/E trung vị ngành (VND)", "Giá trị": sector_implied_price},
            {"Chỉ tiêu": "Chênh lệch so với giá ngụ ý ngành", "Giá trị": sector_implied_price / price - 1},
        ]

    age = (as_of - latest.date).days
    note = f"Giá ngày {latest.date}, BCTC năm {year.year}. Kịch bản dùng bội số người dùng nhập và phân tích kịch bản (Bull/Base/Bear), không phải cam kết lợi nhuận."
    if assumptions.shares_source:
        note += f" Nguồn số cổ phiếu: {assumptions.shares_source}."
    if is_bank:
        note += " Ngân hàng: P/B là phương pháp định giá chủ đạo kết hợp chất lượng tài sản và ROE; không áp dụng DCF thông thường."
    if age > 7:
        note += f" Giá cách ngày chốt {age} ngày; không đưa ra kết luận dựa trên giá hiện tại."
    if pe is None:
        note += " EPS thiếu hoặc không dương: P/E không có ý nghĩa, để trống."
    if bvps is None:
        note += " Thiếu vốn thuộc cổ đông công ty mẹ hoặc số cổ phiếu có nguồn: không tự dùng vốn toàn tập đoàn để tính BVPS."
    return Section(title="Định giá và kịch bản", status="ok" if pe is not None and age <= 7 else "partial",
                   summary=note, rows=rows, source_ids=sorted(set(year.source_ids + ["market"])))


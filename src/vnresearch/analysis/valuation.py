from datetime import date

import pandas as pd

from vnresearch.domain.models import FinancialYear, Section, ValuationAssumptions, finite


def _positive_finite(value) -> float | None:
    number = finite(value)
    return number if number is not None and number > 0 else None


def value_company(year: FinancialYear | None, prices: pd.DataFrame, assumptions: ValuationAssumptions,
                  as_of: date, is_bank: bool = False, sector_pe: float | None = None,
                  *, require_verified: bool = True) -> Section:
    if sector_pe is not None:
        if isinstance(sector_pe, bool) or _positive_finite(sector_pe) is None:
            raise ValueError("sector_pe phải là bội số hữu hạn và dương")
        sector_pe = float(sector_pe)
    if year is None or prices.empty:
        return Section(title="Định giá và kịch bản", status="unavailable",
                       summary="Cần BCTC và giá có nguồn. Không tạo giá mục tiêu khi thiếu đầu vào.")
    latest = prices.iloc[-1]
    price = _positive_finite(latest.get("close"))
    timestamp = pd.to_datetime(latest.get("date"), errors="coerce")
    price_date = timestamp.date() if not pd.isna(timestamp) else None
    age = (as_of - price_date).days if price_date is not None else None
    price_recent = age is not None and 0 <= age <= 7
    price_basis = prices.attrs.get("price_basis", "unknown")
    price_compatible = not require_verified or price_basis == "raw"
    price_usable = price is not None and price_recent and price_compatible

    eps = finite(year.facts.get("eps"))
    equity = finite(year.facts.get("equity_parent"))
    if require_verified:
        eps_metadata = year.fact_metadata.get("eps", {})
        equity_metadata = year.fact_metadata.get("equity_parent", {})
        if eps_metadata.get("verification_status") != "verified" or eps_metadata.get("status") == "quarantined":
            eps = None
        if equity_metadata.get("verification_status") != "verified" or equity_metadata.get("status") == "quarantined":
            equity = None
    shares = _positive_finite(assumptions.shares_outstanding)
    shares_source = assumptions.shares_source.strip() if assumptions.shares_source else None
    bvps = _positive_finite(equity / shares) if equity is not None and shares and shares_source else None
    pe = _positive_finite(price / eps) if price_usable and eps is not None and eps > 0 else None
    pb = _positive_finite(price / bvps) if price_usable and bvps is not None else None
    rows = [{"Chỉ tiêu": "Giá đóng cửa (VND)", "Giá trị": price},
            {"Chỉ tiêu": f"EPS báo cáo năm {year.year} (VND/CP)", "Giá trị": eps},
            {"Chỉ tiêu": f"P/E trên EPS năm {year.year}, không phải TTM", "Giá trị": pe},
            {"Chỉ tiêu": "BVPS (VND/CP), theo số cổ phiếu có nguồn nhập", "Giá trị": bvps},
            {"Chỉ tiêu": "P/B", "Giá trị": pb}]

    arithmetic_issue = False
    for method, multiple, base in [("P/E", assumptions.target_pe, eps), ("P/B", assumptions.target_pb, bvps)]:
        multiple = _positive_finite(multiple)
        if price_usable and multiple is not None and base is not None and base > 0:
            values = [_positive_finite((multiple * factor) * base) for factor in (1, 1.15, 0.85, 0.9, 1.1)]
            change = finite(values[0] / price - 1) if values[0] is not None else None
            if any(value is None for value in values) or change is None:
                arithmetic_issue = True
                continue
            scenario_price, scenario_bull, scenario_bear, sensitivity_low, sensitivity_high = values
            rows += [
                {"Chỉ tiêu": f"Bội số {method} do người dùng giả định", "Giá trị": multiple},
                {"Chỉ tiêu": f"Giá kịch bản {method} (VND)", "Giá trị": scenario_price},
                {"Chỉ tiêu": f"Chênh lệch kịch bản {method} so với giá hiện tại", "Giá trị": change},
                {"Chỉ tiêu": f"Kịch bản Khả quan (Bull +15% {method}) (VND)", "Giá trị": scenario_bull},
                {"Chỉ tiêu": f"Kịch bản Thận trọng (Bear -15% {method}) (VND)", "Giá trị": scenario_bear},
                {"Chỉ tiêu": f"Độ nhạy {method} (-10%) (VND)", "Giá trị": sensitivity_low},
                {"Chỉ tiêu": f"Độ nhạy {method} (+10%) (VND)", "Giá trị": sensitivity_high},
            ]

    if price_usable and sector_pe is not None and eps is not None and eps > 0:
        sector_implied_price = _positive_finite(sector_pe * eps)
        change = finite(sector_implied_price / price - 1) if sector_implied_price is not None else None
        if sector_implied_price is not None and change is not None:
            rows += [
                {"Chỉ tiêu": "P/E trung vị ngành tham chiếu", "Giá trị": sector_pe},
                {"Chỉ tiêu": "Giá ngụ ý theo P/E trung vị ngành (VND)", "Giá trị": sector_implied_price},
                {"Chỉ tiêu": "Chênh lệch so với giá ngụ ý ngành", "Giá trị": change},
            ]
        else:
            arithmetic_issue = True

    note = (f"Giá ngày {price_date or 'chưa xác định'}, BCTC năm {year.year}. "
            "Kịch bản Bull/Base/Bear dùng bội số người dùng giả định; mức +15%/-15% và độ nhạy +10%/-10% "
            "là giả định minh họa trên bội số, không phải dự báo giá hay cam kết lợi nhuận.")
    if shares_source:
        note += f" Nguồn số cổ phiếu: {shares_source}."
    if is_bank:
        note += " Ngân hàng: P/B là phương pháp định giá chủ đạo kết hợp chất lượng tài sản và ROE; không áp dụng DCF thông thường."
    if sector_pe is not None:
        note += " P/E ngành tham chiếu là đầu vào do bên gọi cung cấp; bộ tính này không tự xác nhận mẫu doanh nghiệp, kỳ hay nguồn của trung vị đó."
    if not price_recent:
        if age is not None and age > 7:
            note += f" Giá cách ngày chốt {age} ngày; không tính định giá hay kịch bản dựa trên giá hiện tại."
        else:
            note += " Ngày giá thiếu, không hợp lệ hoặc sau ngày chốt; không tính định giá hay kịch bản."
    if price is None:
        note += " Giá thiếu, không hữu hạn hoặc không dương; không tính định giá hay kịch bản."
    if eps is None or eps <= 0:
        note += " EPS thiếu, chưa xác minh hoặc không dương: P/E chưa đủ điều kiện, để trống."
    if not price_compatible:
        note += " Chưa xác minh giá raw cùng cơ sở cổ phiếu với EPS; không dùng giá adjusted/unknown để tính định giá hay kịch bản."
    if bvps is None:
        note += " Thiếu vốn thuộc cổ đông công ty mẹ dương đã xác minh hoặc số cổ phiếu có nguồn: không tự dùng vốn toàn tập đoàn để tính BVPS."
    if arithmetic_issue:
        note += " Kết quả tính không hữu hạn: để trống kịch bản hoặc tham chiếu ngành liên quan."
    return Section(title="Định giá và kịch bản",
                   status="ok" if (pe is not None or pb is not None) and not arithmetic_issue else "partial",
                   summary=note, rows=rows, source_ids=sorted(set(year.source_ids + ["market"])))

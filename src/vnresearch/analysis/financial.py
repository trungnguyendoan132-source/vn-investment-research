from vnresearch.domain.models import FinancialYear, Metric, finite
from vnresearch.analysis.quality import comparable_facts


def divide(numerator, denominator):
    a, b = finite(numerator), finite(denominator)
    return a / b if a is not None and b is not None and b != 0 else None


def financial_analysis(rows: list[dict], is_bank: bool = False) -> list[FinancialYear]:
    result, by_year = [], {row["year"]: row for row in rows}
    for row in sorted(rows, key=lambda item: item["year"]):
        facts, previous = row["facts"], by_year.get(row["year"] - 1)
        metrics = []

        def ratio(key, label, numerator, denominator, formula):
            source_ids = row["source_ids"]
            if key in {"roa", "roe"} and previous:
                source_ids = sorted(set(source_ids + previous["source_ids"]))
            metrics.append(Metric(key=key, label=label, value=divide(numerator, denominator),
                                  formula=formula, source_ids=source_ids))

        def avg(key):
            old = previous["facts"].get(key) if previous and comparable_facts(row, previous, key) else None
            current = facts.get(key)
            return (old + current) / 2 if old is not None and current is not None else None

        ratio("roa", "ROA trên tài sản bình quân", facts.get("net_income"), avg("total_assets"), "LNST / ((Tài sản T + Tài sản T-1) / 2)")
        ratio("roe", "ROE trên vốn chủ bình quân", facts.get("net_income"), avg("equity"), "LNST / ((VCSH T + VCSH T-1) / 2)")
        ratio("liabilities_to_assets", "Nợ phải trả / Tài sản", facts.get("total_liabilities"), facts.get("total_assets"), "Tổng nợ phải trả / Tổng tài sản; không đồng nhất với nợ vay")
        ratio("net_margin", "Biên lợi nhuận sau thuế", facts.get("net_income"), facts.get("revenue"), "LNST / Doanh thu thuần; ngân hàng dùng tổng thu nhập hoạt động")
        if not is_bank:
            ratio("current_ratio", "Thanh toán hiện hành", facts.get("current_assets"), facts.get("current_liabilities"), "Tài sản ngắn hạn / Nợ ngắn hạn")
            ratio("cfo_to_income", "CFO / LNST", facts.get("cfo"), facts.get("net_income"), "CFO / LNST")
            ratio("ebitda_margin", "Biên EBITDA", facts.get("ebitda"), facts.get("revenue"), "EBITDA / Doanh thu; chỉ có số khi EBITDA hoặc EBIT và khấu hao đủ dữ liệu")
            cfo, capex = facts.get("cfo"), facts.get("capex")
            metrics.append(Metric(key="fcf", label="Dòng tiền tự do", unit="VND",
                                  value=cfo - capex if cfo is not None and capex is not None else None,
                                  formula="CFO - CAPEX; thiếu CAPEX thì thiếu FCF", source_ids=row["source_ids"]))
        for key, label in [("revenue", "Tăng trưởng doanh thu YoY"), ("net_income", "Tăng trưởng LNST YoY")]:
            current = facts.get(key)
            old = previous["facts"].get(key) if previous and comparable_facts(row, previous, key) else None
            value = divide(current - old, abs(old)) if current is not None and old is not None else None
            metrics.append(Metric(key=key + "_growth_yoy", label=label, value=value,
                                  formula=f"({key} T - {key} T-1) / |{key} T-1|; T-1 phải liền kề",
                                  source_ids=sorted(set(row["source_ids"] + (previous["source_ids"] if previous else []))),
                                  note="Không tính khi thiếu năm trước" if previous is None else ""))
        result.append(FinancialYear(year=row["year"], facts=facts, metrics=metrics, source_ids=row["source_ids"],
                                   fact_metadata=row.get("fact_metadata", {}), quality_issues=row.get("quality_issues", [])))
    return result

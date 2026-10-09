import statistics
from datetime import date
from pathlib import Path

from vnresearch.analysis.financial import financial_analysis
from vnresearch.analysis.quality import verified_financial_rows
from vnresearch.data.fundamentals import company_universe, extract_facts, load_raw
from vnresearch.domain.models import Section


def compare_sector(ticker: str, sector: str, year: int, is_bank: bool, *, as_of: date | None = None,
                   filing_dir: Path | None = None, dataset_dir: Path | None = None, require_verified: bool = False):
    universe = company_universe()
    candidates = universe.loc[universe["Ngành ICB Cấp 2 (Supersector)"] == sector, "ticker"].tolist()
    raw, sources = load_raw(candidates, year - 1, year, as_of=as_of, filing_dir=filing_dir, dataset_dir=dataset_dir)
    rows, own = [], None
    for peer in candidates:
        observations = verified_financial_rows(extract_facts(raw, peer), require_verified=require_verified)
        computed = financial_analysis(observations, is_bank=is_bank)
        annual = next((row for row in computed if row.year == year), None)
        if not annual:
            continue
        if not any(annual.facts.get(key) is not None for key in ["revenue", "net_income", "total_assets", "equity"]):
            continue
        metrics = {m.key: m.value for m in annual.metrics}
        record = {"Mã": peer, "Năm": year, "ROE": metrics.get("roe"),
                  "ROA": metrics.get("roa"), "Biên LNST": metrics.get("net_margin"),
                  "Doanh thu YoY": metrics.get("revenue_growth_yoy")}
        rows.append(record)
        if peer == ticker:
            own = record
    if not rows:
        return sources, Section(title="Phân tích ngành", status="unavailable", summary=f"Ngành {sector}: thiếu dữ liệu so sánh cùng năm {year}.")
    medians = {"Mã": "TRUNG VỊ NGÀNH", "Năm": year}
    for key in ["ROE", "ROA", "Biên LNST", "Doanh thu YoY"]:
        values = [row[key] for row in rows if row[key] is not None]
        medians[key] = statistics.median(values) if values else None
    ordered = ([own] if own else []) + [medians] + sorted([row for row in rows if row != own], key=lambda row: row["Mã"])
    return sources, Section(title="Phân tích ngành", status="ok" if len(rows) >= 3 else "partial",
                             summary=f"{sector}: {len(rows)} doanh nghiệp có dữ liệu năm {year}; trung vị tính trên các giá trị có dữ liệu, không gán số thiếu bằng 0. Các chỉ số bình quân cần năm {year - 1}. Tỷ số lưu dạng phần số: 0,1 tương đương 10%.",
                             rows=ordered, source_ids=[source.id for source in sources])

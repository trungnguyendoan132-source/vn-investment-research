from functools import lru_cache
import hashlib
from pathlib import Path

import pandas as pd

from vnresearch.domain.models import Source, utcnow
from vnresearch.platform.settings import ASSETS


UPSTREAM = "https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/"
FACT_CODES = {
    "total_assets": ["bs_tong_tai_san", "bs_tong_cong_tai_san"],
    "current_assets": ["bs_tai_san_ngan_han", "bs_tong_tai_san_ngan_han"],
    "current_liabilities": ["bs_no_ngan_han", "bs_tong_no_ngan_han"],
    "total_liabilities": ["bs_no_phai_tra", "bs_tong_no_phai_tra"],
    "equity": ["bs_von_chu_so_huu_4d280b22", "bs_von_chu_so_huu_6cda78ae", "bs_von_chu_so_huu", "bs_von_va_cac_quy"],
    "equity_parent": ["bs_von_chu_so_huu_cua_cong_ty_me", "bs_von_thuoc_chu_so_huu_cua_cong_ty_me"],
    "noncontrolling_interest": ["bs_loi_ich_cua_co_dong_khong_kiem_soat", "bs_loi_ich_co_dong_khong_kiem_soat", "bs_loi_ich_cua_co_dong_thieu_so"],
    "revenue": ["is_doanh_so_thuan", "is_doanh_thu_thuan", "is_tong_thu_nhap_hoat_dong"],
    "net_income": ["is_lai_lo_thuan_sau_thue", "is_loi_nhuan_sau_thue_thu_nhap_doanh_nghiep", "is_loi_nhuan_ke_toan_sau_thue"],
    "net_income_parent": ["is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_loi_nhuan_sau_thue_cua_co_dong_cong_ty_me"],
    "ebt": ["is_lai_lo_rong_truoc_thue", "is_tong_loi_nhuan_ke_toan_truoc_thue", "is_loi_nhuan_truoc_thue"],
    "interest_expense": ["is_trong_do_chi_phi_lai_vay", "is_chi_phi_lai_vay"],
    "ebit": ["is_ebit"], "ebitda": ["is_ebitda"],
    "depreciation": ["cf_khau_hao_tai_san_co_dinh", "cf_khau_hao_tscd", "cf_khau_hao_tscd_va_bat_dong_san_dau_tu"],
    "cfo": ["cf_luu_chuyen_tien_thuan_tu_cac_hoat_dong_san_xuat_kinh_doanh", "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh", "cf_luu_chuyen_thuan_tu_hoat_dong_kinh_doanh_chung_khoan"],
    "capex": ["cf_tien_chi_de_mua_sam_xay_dung_tscd_va_cac_tai_san_dai_han_khac", "cf_tien_chi_mua_sam_xay_dung_tscd_va_cac_tai_san_dai_han_khac", "cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac"],
    "eps": ["is_lai_co_ban_tren_co_phieu", "is_lai_co_ban_tren_co_phieu_eps"],
}


@lru_cache(maxsize=1)
def company_universe() -> pd.DataFrame:
    frame = pd.read_csv(ASSETS / "companies.csv", dtype=str).fillna("")
    frame["ticker"] = frame["Mã CK"].str.strip().str.upper()
    return frame.drop_duplicates("ticker").set_index("ticker", drop=False)


def company(ticker: str) -> dict:
    universe = company_universe()
    if ticker not in universe.index:
        raise ValueError(f"Không có mã {ticker} trong danh mục; dữ liệu nhập ngoài cần ánh xạ doanh nghiệp")
    row = universe.loc[ticker]
    return {"ticker": ticker, "name": row.get("Tên Doanh Nghiệp", ticker),
            "sector": row.get("Ngành ICB Cấp 2 (Supersector)", "Chưa phân loại"),
            "industry": row.get("Ngành ICB Cấp 1 (Industry)", "Chưa phân loại"),
            "exchange": row.get("Sàn giao dịch", ""), "website": row.get("Trang chủ (Website)", "")}


def file_source(path: Path) -> Source:
    relative = path.relative_to(ASSETS / "bctc").as_posix()
    return Source(id="bctc-" + relative.replace("/", "-").replace(".parquet", ""),
                  title=f"BCTC đóng gói: {relative}", kind="snapshot",
                  url=UPSTREAM + "src/arminer/data/bctc_data/" + relative,
                  retrieved_at=utcnow(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  note="Snapshot upstream, tối đa 2025. Thời điểm công bố ban đầu chưa được xác minh; không dùng làm dữ liệu point-in-time cho backtest.")


@lru_cache(maxsize=6)
def _load(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def load_raw(tickers: list[str], start: int, end: int) -> tuple[pd.DataFrame, list[Source]]:
    frames, sources = [], []
    for path in sorted((ASSETS / "bctc").glob("*/*.parquet")):
        frame = _load(str(path))
        selected = frame.loc[frame.ticker.isin(tickers) & frame.year.between(start, end)]
        if not selected.empty:
            selected = selected.copy()
            source = file_source(path)
            selected["source_id"] = source.id
            frames.append(selected)
            sources.append(source)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), sources)


def extract_facts(raw: pd.DataFrame, ticker: str) -> list[dict]:
    if raw.empty:
        return []
    selected = raw.loc[raw.ticker == ticker]
    rows = []
    for year, group in selected.groupby("year"):
        facts = {}
        for key, codes in FACT_CODES.items():
            facts[key] = None
            for code in codes:
                candidates = group.loc[group.item_code == code, "value"].dropna()
                if candidates.empty:
                    continue
                unique = candidates.unique()
                if len(unique) > 1:
                    raise ValueError(f"Giá trị BCTC xung đột: {ticker}/{year}/{code}; phải chọn nguồn rõ ràng")
                value = float(unique[0])
                facts[key] = abs(value) if key in {"interest_expense", "depreciation", "capex"} else value
                break
        if facts["equity_parent"] is None and facts["equity"] is not None and facts["noncontrolling_interest"] is not None:
            facts["equity_parent"] = facts["equity"] - facts["noncontrolling_interest"]
        if facts["ebit"] is None and facts["ebt"] is not None and facts["interest_expense"] is not None:
            facts["ebit"] = facts["ebt"] + facts["interest_expense"]
        if facts["ebitda"] is None and facts["ebit"] is not None and facts["depreciation"] is not None:
            facts["ebitda"] = facts["ebit"] + facts["depreciation"]
        rows.append({"year": int(year), "facts": facts, "source_ids": sorted(group.source_id.unique())})
    return sorted(rows, key=lambda item: item["year"])

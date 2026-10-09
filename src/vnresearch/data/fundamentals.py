from functools import lru_cache
from datetime import date
import hashlib
from io import BytesIO
import math
import os
from pathlib import Path

import pandas as pd

from vnresearch.domain.models import Source, utcnow
from vnresearch.platform.settings import ASSETS
from vnresearch.data.filings import load_filings, source_optional
from vnresearch.data.snapshots import _parquet, clear_cache, read_parquet, read_release


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

MAPPING_VERSION = "2.0.0"
FACT_CODES["net_income"] += ["is_loi_nhuan_sau_thue"]
FACT_CODES["ebt"] += ["is_tong_loi_nhuan_truoc_thue"]
FACT_CODES["revenue"] += ["is_doanh_thu_hoat_dong", "is_doanh_thu_thuan_tu_hoat_dong_kinh_doanh_bao_hiem"]
FACT_CODES["net_income_parent"] += ["is_loi_nhuan_sau_thue_phan_bo_cho_chu_so_huu", "is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan"]
FACT_CODES["weighted_average_shares"] = ["is_so_co_phieu_binh_quan", "is_so_luong_co_phieu_binh_quan_gia_quyen"]
FACT_CODES["diluted_eps"] = ["is_thu_nhap_pha_loang_tren_co_phieu", "is_lai_suy_giam_tren_co_phieu"]

TEMPLATE_CODES = {
    "bank": {"revenue": ["is_tong_thu_nhap_hoat_dong"], "net_income": ["is_loi_nhuan_sau_thue"],
             "ebt": ["is_tong_loi_nhuan_truoc_thue"]},
    "broker": {"revenue": ["is_doanh_thu_hoat_dong"], "net_income": ["is_loi_nhuan_ke_toan_sau_thue"],
               "net_income_parent": ["is_loi_nhuan_sau_thue_phan_bo_cho_chu_so_huu"]},
    "insurance": {"revenue": ["is_doanh_thu_thuan_tu_hoat_dong_kinh_doanh_bao_hiem"],
                  "net_income_parent": ["is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan"]},
}


@lru_cache(maxsize=2)
def _companies(payload: bytes) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(payload), dtype=str).fillna("")
    if "Mã CK" not in frame:
        raise ValueError("Danh mục doanh nghiệp thiếu Mã CK")
    frame["ticker"] = frame["Mã CK"].str.strip().str.upper()
    if frame.ticker.eq("").any() or frame.ticker.duplicated().any():
        raise ValueError("Danh mục doanh nghiệp có mã trống hoặc trùng")
    return frame.set_index("ticker", drop=False)


def company_universe(catalog_path: Path | None = None) -> pd.DataFrame:
    return _companies(Path(catalog_path or ASSETS / "companies.csv").read_bytes()).copy(deep=True)


company_universe.cache_clear = _companies.cache_clear


def company(ticker: str, *, dataset_dir: Path | None = None, catalog_path: Path | None = None,
            filing_dir: Path | None = None) -> dict:
    ticker = str(ticker).strip().upper()
    if catalog_path is None and dataset_dir and (Path(dataset_dir) / "companies.csv").exists():
        catalog_path = Path(dataset_dir) / "companies.csv"
    universe = company_universe(catalog_path)
    if ticker not in universe.index:
        raw, _ = load_raw([ticker], 2000, 2100, dataset_dir=dataset_dir, filing_dir=filing_dir)
        if raw.empty:
            raise ValueError(f"Không có mã {ticker} trong danh mục hoặc dữ liệu; cần ánh xạ doanh nghiệp")
        return {"ticker": ticker, "name": f"{ticker} - chưa xác minh danh tính doanh nghiệp",
                "sector": "Chưa phân loại", "industry": "Chưa phân loại", "exchange": "unknown", "website": "",
                "instrument_id": None, "identity_status": "unknown", "instrument_history": [],
                "quality_issues": [_issue("MISSING_COMPANY_IDENTITY", f"{ticker} có BCTC nhưng thiếu profile; không tự suy tên/sàn/ngành", "error")]}
    row = universe.loc[ticker]
    return {"ticker": ticker, "name": row.get("Tên Doanh Nghiệp", ticker),
            "sector": row.get("Ngành ICB Cấp 2 (Supersector)", "Chưa phân loại"),
            "industry": row.get("Ngành ICB Cấp 1 (Industry)", "Chưa phân loại"),
            "exchange": row.get("Sàn giao dịch", ""), "website": row.get("Trang chủ (Website)", ""),
            "instrument_id": None, "identity_status": "catalog_unverified", "instrument_history": [],
            "quality_issues": [_issue("INSTRUMENT_HISTORY_UNKNOWN", "Danh mục hiện tại chưa có lịch sử mã/sàn và ngày hiệu lực") ]}


def file_source(path: Path, *, payload: bytes | None = None, digest: str | None = None,
                dataset_version: str | None = None, base: Path | None = None) -> Source:
    payload = path.read_bytes() if payload is None else payload
    actual = hashlib.sha256(payload).hexdigest()
    if digest is not None and digest != actual:
        raise ValueError("Provenance checksum does not describe parsed bytes")
    relative = path.relative_to(base or ASSETS / "bctc").as_posix()
    return Source(id="bctc-" + relative.replace("/", "-").replace(".parquet", "") + "-" + actual[:16],
                  title=f"BCTC đóng gói: {relative}", kind="snapshot",
                  url=UPSTREAM + "src/arminer/data/bctc_data/" + relative,
                  retrieved_at=utcnow(), sha256=actual,
                  note=f"Legacy upstream chưa xác minh số/đơn vị/ngày công bố; không dùng point-in-time. Dataset={dataset_version or actual}; mapping={MAPPING_VERSION}",
                  **source_optional(dataset_version=dataset_version or actual, mapping_version=MAPPING_VERSION,
                                    verification_status="unverified", report_basis="unknown", currency="VND"))


def _load(path: str) -> pd.DataFrame:
    return read_parquet(Path(path))[0].copy(deep=True)


_load.cache_clear = clear_cache


def snapshot_release(dataset_dir: Path | None = None):
    directory = Path(dataset_dir or os.environ.get("VNRESEARCH_DATASET_DIR") or ASSETS / "bctc")
    entries, version = read_release(directory)
    if not entries and not (directory / "release.json").exists() and directory.resolve() != (ASSETS / "bctc").resolve():
        directory = ASSETS / "bctc"
        entries, version = read_release(directory)
    return directory, entries, version


def load_raw(tickers: list[str], start: int, end: int, *, as_of: date | None = None,
             filing_dir: Path | None = None, dataset_dir: Path | None = None,
             period_type: str = "annual") -> tuple[pd.DataFrame, list[Source]]:
    frames, sources = [], []
    if period_type not in {"annual", "half_year", "quarterly"}:
        raise ValueError("period_type phải chọn annual, half_year hoặc quarterly; không trộn kỳ")
    directory, entries, version = snapshot_release(dataset_dir) if period_type == "annual" else (Path(dataset_dir or ASSETS / "bctc"), [], "")
    for path, payload, digest in entries:
        frame = _parquet(digest, payload)
        selected = frame.loc[frame.ticker.isin(tickers) & frame.year.between(start, end)]
        if not selected.empty:
            selected = selected.copy()
            source = file_source(path, payload=payload, digest=digest, dataset_version=version, base=directory)
            selected["source_id"] = source.id
            selected["file_sha256"] = digest
            selected["dataset_version"] = version
            selected["verification_status"] = "unverified"
            selected["period_type"] = "annual"
            selected["report_basis"] = "unknown"
            frames.append(selected)
            sources.append(source)
    filing_dir = filing_dir or os.environ.get("VNRESEARCH_FILINGS_DIR")
    if filing_dir:
        filing_frames, filing_sources = load_filings(Path(filing_dir), tickers, start, end, as_of=as_of, period_type=period_type)
        frames.extend(filing_frames)
        sources.extend(filing_sources)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), sources)


def _issue(code, message, severity="warning"):
    return {"code": code, "message": message, "severity": severity, "component": "financial"}


def _clean(value):
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value.isoformat() if hasattr(value, "isoformat") else value


def _metadata(row, key, value):
    fields = ["item_code", "item_name", "source_id", "source_file", "source_sheet", "source_page", "file_sha256",
              "original_sha256", "dataset_version", "period_start", "period_end", "period_type", "published_at",
              "published_on", "publication_precision", "report_basis", "verification_status", "scale", "sign_convention"]
    result = {field: _clean(row.get(field)) for field in fields}
    result.update(raw_value=_clean(row.get("raw_value", value)), selected_value=value, mapping_version=MAPPING_VERSION,
                  unit=_clean(row.get("unit")) or ("VND/share" if key in {"eps", "diluted_eps"} else "shares" if key == "weighted_average_shares" else "VND"),
                  unit_status="declared" if _clean(row.get("unit")) else "legacy_unverified", status="usable")
    if result["raw_value"] is None:
        result["raw_value"] = value
    return result


def _template(group):
    codes = set(group.item_code)
    if "is_tong_thu_nhap_hoat_dong" in codes:
        return "bank"
    if "is_doanh_thu_thuan_tu_hoat_dong_kinh_doanh_bao_hiem" in codes:
        return "insurance"
    if "is_doanh_thu_hoat_dong" in codes:
        return "broker"
    return "company"


def _derived_metadata(metadata, inputs, formula, unit="VND"):
    sources = set()
    for key in inputs:
        item = metadata.get(key, {})
        sources.update(item.get("source_ids", []))
        if item.get("source_id"):
            sources.add(item["source_id"])
    return {"status": "usable", "derived_from": inputs, "formula": formula, "unit": unit,
            "source_ids": sorted(sources), "mapping_version": MAPPING_VERSION,
            "verification_status": "verified" if all(metadata.get(key, {}).get("verification_status") == "verified" for key in inputs) else "unverified"}


def _choose_group(group, issues):
    if "filing_id" not in group or group.filing_id.isna().all():
        issues.append(_issue("LEGACY_PROVENANCE_UNVERIFIED", "Số, đơn vị, kỳ gốc và ngày công bố của legacy snapshot chưa được đối chiếu"))
        return group
    imported = group.loc[group.filing_id.notna()]
    verified = imported.loc[imported.verification_status.eq("verified")]
    if verified.empty:
        legacy = group.loc[group.filing_id.isna()]
        if not legacy.empty:
            issues.append(_issue("UNVERIFIED_FILING_NOT_APPLIED", "Filing mới chưa xác minh; không tự ghi đè legacy"))
            return legacy
        verified = imported
        issues.append(_issue("FILING_UNVERIFIED", "Filing chưa xác minh; các số chỉ là quan sát chưa nghiệm thu"))
    consolidated = verified.loc[verified.report_basis.eq("consolidated")]
    selected = consolidated if not consolidated.empty else verified
    if consolidated.empty:
        issues.append(_issue("SEPARATE_REPORT_BASIS", "Đang dùng BCTC riêng lẻ; không so trực tiếp với hợp nhất"))
    periods = selected[["period_start", "period_end"]].drop_duplicates()
    if len(periods) > 1:
        raise ValueError("Annual filings have conflicting fiscal periods; select a release explicitly")
    latest = selected.published_on.max()
    selected = selected.loc[selected.published_on.eq(latest)]
    if selected.filing_id.nunique() > 1:
        raise ValueError("Multiple filing revisions on the same publication day; select a release explicitly")
    return selected


def extract_facts(raw: pd.DataFrame, ticker: str) -> list[dict]:
    if raw.empty:
        return []
    selected = raw.loc[raw.ticker == ticker]
    rows = []
    if "period_type" in selected:
        selected = selected.loc[selected.period_type.fillna("annual").eq("annual")]
    for year, original_group in selected.groupby("year"):
        issues, metadata, facts = [], {}, {}
        group = _choose_group(original_group, issues)
        template = _template(group)
        for key, codes in FACT_CODES.items():
            facts[key] = None
            if "metric_key" in group and group.metric_key.eq(key).any():
                candidates_frame = group.loc[group.metric_key.eq(key)]
                codes = candidates_frame.item_code.unique().tolist()
            else:
                codes = TEMPLATE_CODES.get(template, {}).get(key, codes)
                candidates_frame = group.loc[group.item_code.isin(codes)]
            candidates = []
            for code in codes:
                rows_for_code = candidates_frame.loc[candidates_frame.item_code.eq(code) & candidates_frame.value.notna()]
                if rows_for_code.empty:
                    continue
                unique = rows_for_code.value.unique()
                if len(unique) > 1:
                    raise ValueError(f"Giá trị BCTC xung đột: {ticker}/{year}/{code}; phải chọn nguồn rõ ràng")
                value = float(unique[0])
                if not math.isfinite(value):
                    issues.append(_issue("NONFINITE_FINANCIAL_VALUE", f"{key}/{code} không hữu hạn", "error"))
                    continue
                row = rows_for_code.iloc[0]
                meta = _metadata(row, key, value)
                expected = "VND/share" if key in {"eps", "diluted_eps"} else "shares" if key == "weighted_average_shares" else "VND"
                if meta["unit"] != expected:
                    issues.append(_issue("FINANCIAL_UNIT_MISMATCH", f"{key}: cần {expected}, nhận {meta['unit']}", "error"))
                    continue
                candidates.append((value, meta))
            if not candidates:
                metadata[key] = {"status": "missing", "reason": "Không có quan sát đúng code/đơn vị", "mapping_version": MAPPING_VERSION}
                continue
            values = {value for value, _ in candidates}
            chosen = candidates[0]
            if len(values) > 1:
                nonzero = [candidate for candidate in candidates if candidate[0] != 0]
                if key == "noncontrolling_interest" and len({v for v, _ in nonzero}) == 1:
                    chosen = nonzero[0]
                    issues.append(_issue("NCI_TEMPLATE_ALIAS_RESOLVED", "Chọn NCI khác zero; cơ sở vốn sẽ được kiểm tra bằng đẳng thức kế toán", "info"))
                elif key == "equity" and chosen[1]["item_code"] in {"bs_von_chu_so_huu_4d280b22", "bs_von_chu_so_huu_6cda78ae"}:
                    chosen[1]["template_selection"] = "top_level_equity"
                else:
                    metadata[key] = {"status": "quarantined", "reason": "Alias cùng fact có giá trị khác nhau",
                                     "candidates": [m for _, m in candidates], "mapping_version": MAPPING_VERSION}
                    issues.append(_issue("AMBIGUOUS_FACT_ALIAS", f"{key}: alias có giá trị khác nhau", "error"))
                    continue
            value, meta = chosen
            meta["candidates"] = [{k: v for k, v in m.items() if k != "candidates"} for _, m in candidates]
            sign = meta.get("sign_convention")
            imported = _clean(group.iloc[0].get("filing_id")) is not None
            if key == "interest_expense":
                value = -value if sign == "expense_negative" else abs(value) if not imported else value
                meta["normalization"] = "expense_magnitude" if not imported else sign
                if value < 0:
                    meta["status"], meta["reason"] = "quarantined", "Chi phí lãi vay trái quy ước dấu đã khai báo"
                    issues.append(_issue("INTEREST_SIGN_MISMATCH", f"{ticker}/{year}: chi phí lãi vay cần độ lớn không âm", "error"))
                    metadata[key] = meta
                    continue
            elif key == "capex":
                if sign == "outflow_negative" or not imported and value <= 0:
                    value = -value
                    meta["normalization"] = "negative_cash_outflow_to_positive_capex"
                elif not imported and value > 0:
                    meta["status"], meta["reason"] = "quarantined", "Legacy CAPEX có dấu dương chưa xác minh quy ước"
                    issues.append(_issue("CAPEX_SIGN_UNVERIFIED", f"{ticker}/{year}: CAPEX dương cần đối chiếu nguồn", "error"))
                    metadata[key] = meta
                    continue
                if value < 0:
                    meta["status"], meta["reason"] = "quarantined", "CAPEX trái quy ước dấu đã khai báo"
                    issues.append(_issue("CAPEX_SIGN_MISMATCH", f"{ticker}/{year}: CAPEX cần độ lớn chi tiêu không âm", "error"))
                    metadata[key] = meta
                    continue
            elif key == "depreciation" and value < 0 and sign != "signed_adjustment":
                meta["status"], meta["reason"] = "quarantined", "Khấu hao âm chưa có quy ước điều chỉnh có bằng chứng"
                issues.append(_issue("DEPRECIATION_SIGN_UNVERIFIED", f"{ticker}/{year}: khấu hao âm không tự abs", "error"))
                metadata[key] = meta
                continue
            meta["selected_value"] = value
            facts[key], metadata[key] = value, meta
        equity, nci = facts["equity"], facts["noncontrolling_interest"]
        if facts["equity_parent"] is None and equity is not None and nci is not None:
            assets, liabilities = facts["total_assets"], facts["total_liabilities"]
            residual = assets - liabilities - equity if assets is not None and liabilities is not None else None
            tolerance = max(1.0, abs(assets or 0) * 1e-8)
            if residual is not None and abs(residual - nci) <= tolerance and abs(nci) > tolerance:
                facts["equity_parent"], facts["equity"] = equity, equity + nci
                metadata["equity"]["normalization"] = "legacy_equity_excluded_nci; add_nci_for_total_equity"
                metadata["equity"]["selected_value"] = equity + nci
                issues.append(_issue("EQUITY_BASIS_NORMALIZED", "Vốn legacy chưa gồm minority; tổng vốn được cộng NCI, vốn mẹ giữ nguyên", "info"))
                parent_formula = "reported_equity_excludes_nci"
            elif nci == 0 or residual is not None and abs(residual) <= tolerance:
                facts["equity_parent"] = equity - nci
                parent_formula = "total_equity - nci"
            else:
                parent_formula = None
                issues.append(_issue("EQUITY_BASIS_AMBIGUOUS", "Không xác định được vốn báo cáo có gồm NCI; không suy BVPS", "error"))
            if parent_formula:
                metadata["equity_parent"] = _derived_metadata(metadata, ["equity", "noncontrolling_interest"], parent_formula)
        if facts["ebit"] is None and facts["ebt"] is not None and facts["interest_expense"] is not None:
            facts["ebit"] = facts["ebt"] + facts["interest_expense"]
            metadata["ebit"] = _derived_metadata(metadata, ["ebt", "interest_expense"], "ebt + interest_expense")
        if facts["ebitda"] is None and facts["ebit"] is not None and facts["depreciation"] is not None:
            facts["ebitda"] = facts["ebit"] + facts["depreciation"]
            metadata["ebitda"] = _derived_metadata(metadata, ["ebit", "depreciation"], "ebit + depreciation")
        eps, diluted, owner, shares = facts["eps"], facts["diluted_eps"], facts["net_income_parent"], facts["weighted_average_shares"]
        reasons = []
        if eps is not None:
            if owner is not None and owner != 0 and math.isclose(eps, owner, rel_tol=1e-10):
                reasons.append("EPS bằng đúng tổng lợi nhuận thuộc chủ sở hữu; sai khác định nghĩa/đơn vị")
            if diluted is not None and diluted > 0 and eps > 0 and max(eps / diluted, diluted / eps) > 100:
                reasons.append("EPS cơ bản/pha loãng chênh hơn 100 lần; cần kiểm tra cột/đơn vị")
            if shares is not None and shares > 0 and owner is not None and not math.isclose(eps, owner / shares, rel_tol=0.03, abs_tol=2):
                reasons.append("EPS không khớp LNST mẹ / cổ phiếu bình quân cùng kỳ")
            if metadata["eps"].get("verification_status") != "verified" and abs(eps) > 1_000_000:
                reasons.append("EPS legacy ngoài miền kiểm tra; chưa xác minh đơn vị và cột báo cáo")
            if reasons:
                facts["eps"] = None
                metadata["eps"]["status"], metadata["eps"]["reason"] = "quarantined", "; ".join(reasons)
                issues.append(_issue("EPS_INCONSISTENT", "; ".join(reasons), "error"))
        rows.append({"year": int(year), "facts": facts, "source_ids": sorted(group.source_id.unique()),
                     "fact_metadata": metadata, "quality_issues": issues})
    return sorted(rows, key=lambda item: item["year"])

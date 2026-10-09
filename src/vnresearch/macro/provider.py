"""Macro data adapter for the TV3 macro/sector contract; missing data is never fabricated."""
from __future__ import annotations
from datetime import date
import hashlib
from pathlib import Path
import pandas as pd
import requests
from vnresearch.domain.models import Mode, Section, Source, utcnow
from vnresearch.platform.settings import ASSETS

WORLD_BANK_INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": ("Tăng trưởng GDP thực", "%/năm", "annual"),
    "FP.CPI.TOTL.ZG": ("Lạm phát CPI", "%/năm", "annual"),
    "NE.EXP.GNFS.ZS": ("Xuất khẩu hàng hóa và dịch vụ / GDP", "% GDP", "annual"),
    "PA.NUS.FCRF": ("Tỷ giá chính thức (LCU/USD, bình quân kỳ)", "VND/USD", "annual"),
    "FR.INR.LEND": ("Lãi suất cho vay", "%/năm", "annual"),
    "FS.AST.PRVT.GD.ZS": ("Tín dụng khu vực tư nhân / GDP", "% GDP", "annual"),
}
REQUIRED_COLUMNS = {"indicator", "period", "value", "unit", "source_url", "retrieved_at"}


def fetch_world_bank(start_year: int, end_year: int) -> pd.DataFrame:
    if start_year > end_year:
        raise ValueError("start_year phải nhỏ hơn hoặc bằng end_year")
    rows, retrieved = [], utcnow().isoformat()
    for code, (label, unit, frequency) in WORLD_BANK_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/VNM/indicator/{code}"
        response = requests.get(url, params={"format": "json", "date": f"{start_year}:{end_year}", "per_page": 100}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[0], dict):
            raise ValueError(f"World Bank trả cấu trúc dữ liệu không hợp lệ cho {code}")
        for item in payload[1] or []:
            if item.get("value") is not None:
                rows.append({"indicator": code, "label": label, "period": str(item["date"]), "frequency": frequency,
                             "value": float(item["value"]), "unit": unit, "source_url": response.url,
                             "retrieved_at": retrieved, "published_at": None})
    return pd.DataFrame(rows)


def _normalize_frame(frame: pd.DataFrame, as_of: date) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"CSV vĩ mô thiếu cột bắt buộc: {', '.join(sorted(missing))}")
    
    frame = frame.copy()
    for col in ("indicator", "period", "unit", "source_url"):
        frame[col] = frame[col].astype(str).str.strip()
    
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    
    # 1. Tự động xác định tần suất dựa trên định dạng của chuỗi period
    def infer_frequency(p: str) -> str:
        p_str = str(p).strip()
        if len(p_str) == 4 and p_str.isdigit():
            return "annual"
        if "Q" in p_str:
            return "quarterly"
        if "-" in p_str:
            return "monthly"
        return "annual"

    expected = frame["period"].map(infer_frequency)
    
    # Nếu trong CSV chưa có cột frequency, tự động gán theo expected
    if "frequency" not in frame or frame["frequency"].isna().all():
        frame["frequency"] = expected
    else:
        # Chuẩn hóa giá trị cột frequency nhập vào
        freq_map = {
            "yearly": "annual", "year": "annual", "annual": "annual",
            "quarter": "quarterly", "quarterly": "quarterly",
            "month": "monthly", "monthly": "monthly"
        }
        normalized = frame["frequency"].astype(str).str.strip().str.lower().map(lambda x: freq_map.get(x, ""))
        normalized = normalized.where(normalized.ne(""), expected)
        
        # Kiểm tra nếu tần suất khai báo bị mâu thuẫn với định dạng period (VD: period='2024' nhưng ghi frequency='monthly')
        mismatch = normalized.ne(expected)
        if mismatch.any():
            raise ValueError(f"Tần suất không khớp định dạng kỳ: {frame.loc[mismatch, ['indicator','period','frequency']].to_dict('records')[:5]}")
        frame["frequency"] = normalized

    if "label" not in frame: 
        frame["label"] = frame["indicator"]
    if "published_at" not in frame: 
        frame["published_at"] = None

    if frame["retrieved_at"].isna().any() or frame["source_url"].eq("").any() or frame["unit"].eq("").any():
        raise ValueError("Mỗi quan sát vĩ mô cần retrieved_at, source_url và unit")
    
    frame["retrieved_at"] = pd.to_datetime(frame["retrieved_at"], errors="coerce", utc=True)
    if frame["retrieved_at"].isna().any(): 
        raise ValueError("retrieved_at có giá trị ngày giờ không hợp lệ")
    
    if frame["published_at"].notna().any(): 
        frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce", utc=True)

    # 2. Quy đổi kỳ (period) thành ngày cuối kỳ (period_end)
    def period_key(value):
        text = str(value).strip()
        if len(text) == 4 and text.isdigit(): 
            return pd.Period(text, freq="Y").end_time.date()
        if len(text) == 6 and text[4] == "Q" and text[5] in "1234": 
            return pd.Period(f"{text[:4]}Q{text[5]}", freq="Q").end_time.date()
        if len(text) == 7 and text[4] == "-": 
            return pd.Period(text, freq="M").end_time.date()
        raise ValueError(f"Kỳ không hợp lệ: {text!r}; dùng YYYY, YYYYQn hoặc YYYY-MM")

    frame["period_end"] = frame["period"].map(period_key)
    
    # Lọc các quan sát diễn ra trước hoặc tại ngày chốt (as_of)
    frame = frame.loc[frame["period_end"] <= as_of].copy()
    
    # Kiểm tra trùng lặp chỉ tiêu và kỳ
    if frame.duplicated(["indicator", "period"]).any():
        duplicates = frame.loc[frame.duplicated(["indicator", "period"], keep=False), ["indicator", "period"]]
        raise ValueError(f"Trùng chỉ tiêu/kỳ vĩ mô; phải chọn nguồn trước: {duplicates.to_dict('records')[:5]}")
        
    return frame.loc[frame["value"].notna()].sort_values(["indicator", "period_end"])

def _macro_sources(frame: pd.DataFrame, kind: str, file_hash: str | None = None) -> list[Source]:
    sources = []
    for indicator, group in frame.groupby("indicator", sort=True):
        latest = group.sort_values("period_end").iloc[-1]
        sid = "macro-" + hashlib.sha1(str(indicator).encode()).hexdigest()[:12]
        sources.append(Source(id=sid, title=str(latest.get("label", indicator)), kind=kind, url=str(latest["source_url"]),
            retrieved_at=latest["retrieved_at"].to_pydatetime(), period=str(latest["period"]), sha256=file_hash,
            note=f"Đơn vị: {latest['unit']}; tần suất: {latest['frequency']}; ngày công bố gốc chưa được xác minh nếu thiếu published_at."))
    return sources


def load_macro(as_of: date, mode: Mode, input_path: Path | None = None):
    path = input_path or ASSETS / "macro" / "vietnam_macro.csv"
    file_hash = None
    
    # Ưu tiên 1: Người dùng truyền đường dẫn file CSV tùy chỉnh
    if input_path is not None:
        if not path.exists(): 
            raise ValueError(f"Không tìm thấy file CSV vĩ mô: {path}")
        frame, kind = pd.read_csv(path, dtype={"indicator": str, "period": str}), "user_supplied"
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        
    # Ưu tiên 2: Chế độ SNAPSHOT đọc file CSV sẵn có chứa dữ liệu tháng/quý/năm
    elif mode == Mode.SNAPSHOT and path.exists() and path.stat().st_size:
        frame, kind = pd.read_csv(path, dtype={"indicator": str, "period": str}), "snapshot"
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        
    # Ưu tiên 3: Chế độ LIVE hoặc DEMO
    elif mode in {Mode.LIVE, Mode.DEMO}:
        if mode == Mode.DEMO:
            frame = pd.DataFrame([
                {"indicator": code, "label": label, "period": str(as_of.year - 1), "frequency": freq,
                 "value": value, "unit": unit, "source_url": "urn:demo:synthetic-macro", 
                 "retrieved_at": utcnow().isoformat(), "published_at": None} 
                for (code, (label, unit, freq)), value in zip(
                    WORLD_BANK_INDICATORS.items(), [6.2, 3.5, 88.0, 24500.0, 9.0, 120.0]
                )
            ])
            kind = "synthetic"
        else: 
            # Live từ World Bank (mặc định chỉ lấy số liệu năm)
            frame, kind = fetch_world_bank(max(2000, as_of.year - 8), as_of.year - 1), "live"
    else:
        return [], Section(title="Tổng quan vĩ mô", status="unavailable", summary="Chưa có snapshot vĩ mô. Cung cấp CSV đã xác minh hoặc bật World Bank live.")

    # Chuẩn hóa dữ liệu (xử lý tần suất tháng/quý/năm, tính ngày cuối kỳ)
    frame = _normalize_frame(frame, as_of)
    if frame.empty: 
        return [], Section(title="Tổng quan vĩ mô", status="unavailable", summary="Không có quan sát vĩ mô hợp lệ trước hoặc tại ngày chốt.")
    
    # ... (Giữ nguyên các đoạn code xử lý Source, Section và Policy Events phía sau)

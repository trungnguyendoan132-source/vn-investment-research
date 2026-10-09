from datetime import date
import hashlib
from pathlib import Path

import pandas as pd
import requests

from vnresearch.domain.models import Mode, Section, Source, utcnow
from vnresearch.platform.settings import ASSETS


INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": ("Tăng trưởng GDP thực", "%/năm"),
    "FP.CPI.TOTL.ZG": ("Lạm phát CPI", "%/năm"),
    "NE.EXP.GNFS.ZS": ("Xuất khẩu hàng hóa và dịch vụ / GDP", "% GDP"),
}


def fetch_world_bank(start_year: int, end_year: int) -> pd.DataFrame:
    rows = []
    retrieved = utcnow().isoformat()
    for code, (label, unit) in INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/VNM/indicator/{code}"
        response = requests.get(url, params={"format": "json", "date": f"{start_year}:{end_year}", "per_page": 100}, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            raise ValueError("World Bank trả cấu trúc dữ liệu không hợp lệ")
        for item in payload[1] or []:
            if item.get("value") is not None:
                rows.append({"indicator": code, "label": label, "year": int(item["date"]),
                             "value": float(item["value"]), "unit": unit, "source_url": response.url,
                             "retrieved_at": retrieved})
    return pd.DataFrame(rows)


def load_macro(as_of: date, mode: Mode, input_path: Path | None = None):
    path = input_path or ASSETS / "macro/world_bank.csv"
    if input_path or (mode == Mode.SNAPSHOT and path.exists()):
        frame = pd.read_csv(path)
        kind = "user_supplied" if input_path else "snapshot"
    elif mode == Mode.LIVE:
        frame, kind = fetch_world_bank(as_of.year - 6, as_of.year - 1), "live"
    elif mode == Mode.DEMO:
        frame = pd.DataFrame([{"indicator": code, "label": label, "year": as_of.year - 1,
                               "value": value, "unit": unit, "source_url": "urn:demo:macro", "retrieved_at": utcnow().isoformat()}
                              for (code, (label, unit)), value in zip(INDICATORS.items(), [6.2, 3.5, 88.0])])
        kind = "synthetic"
    else:
        return [], Section(title="Tổng quan vĩ mô", status="unavailable", summary="Chưa có dữ liệu vĩ mô; nhập CSV hoặc bật World Bank live.")
    required = {"indicator", "year", "value", "unit", "source_url", "retrieved_at"}
    if not required.issubset(frame.columns):
        raise ValueError("CSV vĩ mô thiếu cột bắt buộc")
    frame["year"] = pd.to_numeric(frame.year, errors="raise").astype(int)
    frame["value"] = pd.to_numeric(frame.value, errors="raise")
    frame = frame.loc[(frame.year < as_of.year) & frame.value.notna()].sort_values("year")
    if frame.duplicated(["indicator", "year"]).any():
        raise ValueError("Chỉ tiêu vĩ mô trùng năm; phải chọn nguồn trước")
    if frame.empty:
        return [], Section(title="Tổng quan vĩ mô", status="unavailable", summary="Không có kỳ vĩ mô hoàn tất trước ngày chốt.")
    sources, rows = [], []
    for code, group in frame.groupby("indicator"):
        latest = group.iloc[-1]
        sid = "macro-" + str(code).replace(".", "-")
        sources.append(Source(id=sid, title=str(latest.get("label", code)), kind=kind,
                              url=str(latest.source_url), retrieved_at=pd.Timestamp(latest.retrieved_at).to_pydatetime(),
                              period=str(latest.year), note="Chuỗi năm; không thay thế dữ liệu tháng/quý hay lãi suất điều hành. Vintage công bố lịch sử chưa xác minh."))
        rows.append({"Chỉ tiêu": str(latest.get("label", code)), "Năm": int(latest.year),
                     "Giá trị": float(latest.value), "Đơn vị": str(latest.unit)})
    if input_path:
        sources[0].sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return sources, Section(title="Tổng quan vĩ mô", status="ok", rows=rows,
                             source_ids=[s.id for s in sources],
                             summary="Theo dõi tăng trưởng, lạm phát và độ mở thương mại theo năm. Đọc cùng kỳ dữ liệu; các quan hệ với doanh nghiệp là nhận định cần kiểm chứng.")

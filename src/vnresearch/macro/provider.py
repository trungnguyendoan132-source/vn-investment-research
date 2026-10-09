"""Macro data adapter for the TV3 macro/sector contract; missing data is never fabricated."""
from __future__ import annotations

from datetime import date
import hashlib
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

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
WORLD_BANK_CSV = ASSETS / "macro" / "world_bank.csv"
FETCH_COLUMNS = ["indicator", "label", "year", "value", "unit", "source_url", "retrieved_at"]
REQUIRED_COLUMNS = {"indicator", "value", "unit", "source_url", "retrieved_at"}
MAX_QUALITY_ROWS = 40


def fetch_world_bank(start_year: int, end_year: int) -> pd.DataFrame:
    """Fetch latest annual World Bank observations, retaining the shared CSV schema.

    The API serves its current revised series; it does not provide an historical
    vintage suitable for point-in-time backtests.
    """
    if not isinstance(start_year, int) or not isinstance(end_year, int):
        raise ValueError("Năm bắt đầu và kết thúc phải là số nguyên")
    if start_year < 1900 or end_year > 2100 or start_year > end_year:
        raise ValueError("Khoảng năm World Bank không hợp lệ")

    rows = []
    retrieved = utcnow().isoformat()
    for code, (label, unit, _) in WORLD_BANK_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/VNM/indicator/{code}"
        response = requests.get(
            url,
            params={"format": "json", "date": f"{start_year}:{end_year}", "per_page": 100},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if (
            not isinstance(payload, list)
            or len(payload) < 2
            or not isinstance(payload[0], dict)
            or (payload[1] is not None and not isinstance(payload[1], list))
        ):
            raise ValueError(f"World Bank trả cấu trúc dữ liệu không hợp lệ cho {code}")
        for item in payload[1] or []:
            if not isinstance(item, dict):
                continue
            year_text = str(item.get("date", ""))
            if not re.fullmatch(r"\d{4}", year_text):
                continue
            year = int(year_text)
            if not start_year <= year <= end_year or item.get("value") is None:
                continue
            rows.append(
                {
                    "indicator": code,
                    "label": label,
                    "year": year,
                    "value": item["value"],
                    "unit": unit,
                    "source_url": response.url,
                    "retrieved_at": retrieved,
                }
            )
    return pd.DataFrame(rows, columns=FETCH_COLUMNS)


def _period_details(value: object) -> tuple[str, date, str] | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}(?:\.0+)?", text):
        year = int(float(text))
        if 1900 <= year <= 2100:
            period = f"{year:04d}"
            return period, pd.Period(period, freq="Y").end_time.date(), "annual"
    if re.fullmatch(r"\d{4}Q[1-4]", text, flags=re.IGNORECASE):
        period = text.upper()
        return period, pd.Period(period, freq="Q").end_time.date(), "quarterly"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        try:
            return text, pd.Period(text, freq="M").end_time.date(), "monthly"
        except ValueError:
            return None
    return None


def _quality_row(
    indicator: str | None,
    label: str | None,
    period: str | None,
    issue: str,
    unit: str | None = None,
) -> dict:
    return {
        "Loại dòng": "Chất lượng dữ liệu",
        "Chỉ tiêu": label or indicator or "Không xác định",
        "Mã chỉ tiêu": indicator,
        "Kỳ gần nhất": period,
        "Tần suất": None,
        "Giá trị": None,
        "Đơn vị": unit,
        "Số ngày từ cuối kỳ": None,
        "Độ mới": "không áp dụng",
        "published_at": None,
        "Loại bằng chứng": "không có quan sát hợp lệ",
        "source_id": None,
        "Ghi chú": issue,
    }


def _normalize_frame(frame: pd.DataFrame, as_of: date) -> tuple[pd.DataFrame, list[dict]]:
    """Normalize supported CSV shapes and return excluded-row diagnostics."""
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if "period" not in frame.columns and "year" not in frame.columns:
        missing.add("year")
    if missing:
        raise ValueError(f"CSV vĩ mô thiếu cột bắt buộc: {', '.join(sorted(missing))}")

    source = frame.copy()
    if "label" not in source:
        source["label"] = source["indicator"]
    if "frequency" not in source:
        source["frequency"] = ""
    if "published_at" not in source:
        source["published_at"] = None
    if "period" not in source:
        source["period"] = source["year"]

    for column in ("indicator", "label", "unit", "source_url"):
        source[column] = source[column].map(lambda value: "" if pd.isna(value) else str(value).strip())

    source["value"] = pd.to_numeric(source["value"], errors="coerce")
    source["retrieved_at"] = pd.to_datetime(source["retrieved_at"], errors="coerce", utc=True)
    source["published_at"] = pd.to_datetime(source["published_at"], errors="coerce", utc=True)

    normalized_rows = []
    quality_rows = []
    for _, row in source.iterrows():
        indicator = str(row["indicator"])
        label = str(row["label"]) or indicator or None
        unit = str(row["unit"]) or None
        period_text = str(row["period"]).strip() if pd.notna(row["period"]) else None
        reasons = []
        if not indicator:
            reasons.append("Thiếu mã chỉ tiêu.")
        if not unit:
            reasons.append("Thiếu đơn vị đo.")
        if not row["source_url"]:
            reasons.append("Thiếu URL nguồn.")
        else:
            parsed_url = urlsplit(str(row["source_url"]))
            valid_http = parsed_url.scheme in {"http", "https"} and bool(parsed_url.hostname)
            valid_urn = parsed_url.scheme == "urn" and len(str(row["source_url"]).split(":")) >= 3
            if not valid_http and not valid_urn:
                reasons.append("URL nguồn không hợp lệ.")
        if pd.isna(row["retrieved_at"]):
            reasons.append("Thời điểm truy xuất thiếu hoặc không hợp lệ.")

        period_details = _period_details(row["period"])
        if period_details is None:
            reasons.append("Kỳ không hợp lệ; dùng YYYY, YYYYQn hoặc YYYY-MM.")
        value = row["value"]
        if pd.isna(value) or not math.isfinite(float(value)):
            reasons.append("Giá trị thiếu, không phải số hoặc không hữu hạn.")

        if period_details is not None:
            period, period_end, inferred_frequency = period_details
            frequency = str(row["frequency"]).strip().lower()
            frequency = {"yearly": "annual", "quarter": "quarterly", "month": "monthly"}.get(frequency, frequency)
            if frequency and frequency != inferred_frequency:
                reasons.append("Tần suất không khớp định dạng kỳ.")
            if period_end > as_of:
                reasons.append("Kỳ chưa kết thúc tại ngày chốt; quan sát đã bị loại.")
        else:
            period, period_end, inferred_frequency = period_text or "", None, ""

        if reasons:
            quality_rows.append(_quality_row(indicator or None, label, period_text, " ".join(reasons), unit))
            continue

        published_at = row["published_at"]
        if pd.notna(published_at):
            published_on = published_at.date()
        else:
            published_on = None
        normalized_rows.append(
            {
                "indicator": indicator,
                "label": label or indicator,
                "period": period,
                "period_end": period_end,
                "frequency": inferred_frequency,
                "value": float(value),
                "unit": unit,
                "source_url": str(row["source_url"]),
                "retrieved_at": row["retrieved_at"],
                "published_at": published_at if published_on is not None else None,
            }
        )

    normalized = pd.DataFrame(normalized_rows)
    if normalized.empty:
        normalized = pd.DataFrame(
            columns=[
                "indicator", "label", "period", "period_end", "frequency", "value",
                "unit", "source_url", "retrieved_at", "published_at",
            ]
        )

    duplicate_mask = normalized.duplicated(["indicator", "period"], keep=False)
    if duplicate_mask.any():
        duplicates = normalized.loc[duplicate_mask, ["indicator", "label", "period", "unit"]]
        for _, duplicate in duplicates.drop_duplicates(["indicator", "period"]).iterrows():
            quality_rows.append(
                _quality_row(
                    str(duplicate["indicator"]),
                    str(duplicate["label"]),
                    str(duplicate["period"]),
                    "Có nhiều quan sát cho cùng chỉ tiêu/kỳ; tất cả bản trùng đã bị loại.",
                    str(duplicate["unit"]),
                )
            )
        normalized = normalized.loc[~duplicate_mask].copy()

    known = set(WORLD_BANK_INDICATORS)
    for indicator in sorted(set(normalized["indicator"]) - known):
        label = str(normalized.loc[normalized["indicator"] == indicator, "label"].iloc[0])
        quality_rows.append(
            _quality_row(
                indicator,
                label,
                None,
                "Chỉ tiêu ngoài danh mục World Bank cấu hình sẵn; giữ dữ liệu có nguồn nhưng cần TV3 xác nhận định nghĩa và đơn vị.",
            )
        )

    found = set(normalized["indicator"])
    for indicator, (label, unit, _) in WORLD_BANK_INDICATORS.items():
        if indicator not in found:
            quality_rows.append(
                _quality_row(
                    indicator,
                    label,
                    None,
                    "Không có quan sát hợp lệ cho chỉ tiêu này trong dữ liệu đã nạp.",
                    unit,
                )
            )
    normalized = normalized.sort_values(["indicator", "period_end"]).reset_index(drop=True)
    return normalized, quality_rows[:MAX_QUALITY_ROWS]


def _is_world_bank_source(url: str) -> bool:
    try:
        host = urlsplit(url).hostname or ""
        return host == "worldbank.org" or host.endswith(".worldbank.org")
    except ValueError:
        return False


def _macro_sources(frame: pd.DataFrame, kind: str, file_hash: str | None = None) -> list[Source]:
    sources = []
    for indicator, group in frame.groupby("indicator", sort=True):
        latest = group.sort_values("period_end").iloc[-1]
        sid = "macro-" + hashlib.sha256(str(indicator).encode()).hexdigest()[:16]
        world_bank = _is_world_bank_source(str(latest["source_url"]))
        vintage_note = (
            " World Bank API trả chuỗi sửa đổi mới nhất; vintage công bố tại ngày chốt lịch sử chưa được xác minh."
            if world_bank
            else " Vintage/khả năng biết tại ngày chốt chưa được xác minh từ dữ liệu đầu vào."
        )
        sources.append(
            Source(
                id=sid,
                title=str(latest["label"]),
                kind=kind,
                url=str(latest["source_url"]),
                retrieved_at=latest["retrieved_at"].to_pydatetime(),
                period=str(latest["period"]),
                sha256=file_hash,
                unit=str(latest["unit"]),
                verification_status="synthetic" if kind == "synthetic" else "unverified",
                note=f"Đơn vị: {latest['unit']}; tần suất: {latest['frequency']};{vintage_note}",
            )
        )
    return sources


def load_macro(as_of: date, mode: Mode, input_path: Path | None = None):
    path = input_path or WORLD_BANK_CSV
    file_hash = None
    if input_path is not None:
        if not path.exists():
            raise ValueError(f"Không tìm thấy file CSV vĩ mô: {path}")
        frame, kind = pd.read_csv(path, dtype={"indicator": str, "year": str, "period": str}), "user_supplied"
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mode == Mode.SNAPSHOT and path.exists() and path.stat().st_size:
        frame, kind = pd.read_csv(path, dtype={"indicator": str, "year": str, "period": str}), "snapshot"
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mode in {Mode.LIVE, Mode.DEMO}:
        if mode == Mode.DEMO:
            frame = pd.DataFrame(
                [
                    {
                        "indicator": code,
                        "label": label,
                        "year": as_of.year - 1,
                        "value": value,
                        "unit": unit,
                        "source_url": "urn:demo:synthetic-macro",
                        "retrieved_at": utcnow().isoformat(),
                    }
                    for (code, (label, unit, _)), value in zip(
                        WORLD_BANK_INDICATORS.items(), [6.2, 3.5, 88.0, 24500.0, 9.0, 120.0]
                    )
                ]
            )
            kind = "synthetic"
        else:
            frame, kind = fetch_world_bank(max(2000, as_of.year - 8), as_of.year - 1), "live"
    else:
        return [], Section(
            title="Tổng quan vĩ mô",
            status="unavailable",
            summary="Chưa có snapshot vĩ mô. Cung cấp CSV đã xác minh hoặc bật World Bank live.",
        )

    frame, quality_rows = _normalize_frame(frame, as_of)
    if frame.empty:
        missing_count = sum(row["Ghi chú"].startswith("Không có quan sát hợp lệ") for row in quality_rows)
        return [], Section(
            title="Tổng quan vĩ mô",
            status="unavailable",
            rows=quality_rows,
            summary=(
                f"Không có quan sát vĩ mô hợp lệ tại ngày chốt; {missing_count} chỉ tiêu cấu hình sẵn thiếu dữ liệu. "
                "Các lỗi/thiếu được liệt kê trong bảng chất lượng."
            ),
        )

    sources = _macro_sources(frame, kind, file_hash)
    source_by_indicator = {
        str(indicator): "macro-" + hashlib.sha256(str(indicator).encode()).hexdigest()[:16]
        for indicator in frame["indicator"].unique()
    }
    rows = []
    unverified_world_bank = False
    for indicator, group in frame.groupby("indicator", sort=True):
        group = group.sort_values("period_end")
        latest = group.iloc[-1]
        world_bank = _is_world_bank_source(str(latest["source_url"]))
        unverified_world_bank = unverified_world_bank or world_bank
        age = (as_of - latest["period_end"]).days
        for _, observation in group.tail(8).iterrows():
            latest_row = observation["period"] == latest["period"]
            observation_age = (as_of - observation["period_end"]).days
            freshness = (
                "cũ — kiểm tra cập nhật"
                if latest_row and age > 550
                else "kỳ lịch sử; vintage không xác minh"
                if world_bank
                else "kỳ lịch sử"
                if not latest_row
                else "chưa cảnh báo theo ngưỡng 550 ngày"
            )
            rows.append(
                {
                    "Loại dòng": "Quan sát vĩ mô",
                    "Chỉ tiêu": str(observation["label"]),
                    "Mã chỉ tiêu": str(indicator),
                    "Kỳ gần nhất": str(observation["period"]),
                    "Tần suất": str(observation["frequency"]),
                    "Giá trị": float(observation["value"]),
                    "Đơn vị": str(observation["unit"]),
                    "Số ngày từ cuối kỳ": int(observation_age),
                    "Độ mới": freshness,
                    "Vintage point-in-time": "chưa xác minh" if world_bank else "chưa được xác minh",
                    "published_at": (
                        observation["published_at"].isoformat()
                        if pd.notna(observation["published_at"])
                        else None
                    ),
                    "Loại bằng chứng": "giả lập" if kind == "synthetic" else "quan sát nguồn",
                    "source_id": source_by_indicator[str(indicator)],
                }
            )

    rows.extend(quality_rows)
    policy_path = ASSETS / "macro" / "policy_events.csv"
    if policy_path.exists() and policy_path.stat().st_size:
        policy = pd.read_csv(policy_path, dtype=str).fillna("")
        required = {"event_date", "title", "authority", "summary", "affected_sectors", "source_url", "retrieved_at"}
        if not required.issubset(policy.columns):
            raise ValueError(f"CSV chính sách thiếu cột: {', '.join(sorted(required - set(policy.columns)))}")
        policy["event_date"] = pd.to_datetime(policy["event_date"], errors="coerce").dt.date
        policy["retrieved_at"] = pd.to_datetime(policy["retrieved_at"], errors="coerce", utc=True)
        if policy["event_date"].isna().any() or policy["retrieved_at"].isna().any() or policy["source_url"].eq("").any():
            raise ValueError("Mỗi sự kiện chính sách cần ngày, thời điểm truy xuất và URL nguồn hợp lệ")
        for _, event in policy.loc[policy["event_date"] <= as_of].sort_values("event_date").iterrows():
            sid = "policy-" + hashlib.sha256((str(event["event_date"]) + str(event["title"])).encode()).hexdigest()[:16]
            sources.append(
                Source(
                    id=sid,
                    title=str(event["title"]),
                    kind="snapshot",
                    url=str(event["source_url"]),
                    retrieved_at=event["retrieved_at"].to_pydatetime(),
                    period=str(event["event_date"]),
                    sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                    verification_status="unverified",
                    note=f"Cơ quan: {event['authority']}; ngành liên quan: {event['affected_sectors']}; độ tin cậy do người nhập gán: {event.get('confidence', '')}",
                )
            )
            rows.append(
                {
                    "Loại dòng": "Sự kiện chính sách",
                    "Chỉ tiêu": str(event["title"]),
                    "Kỳ gần nhất": str(event["event_date"]),
                    "Tần suất": "sự kiện",
                    "Giá trị": str(event["summary"]),
                    "Đơn vị": "mô tả định tính",
                    "Số ngày từ cuối kỳ": (as_of - event["event_date"]).days,
                    "Độ mới": "kiểm tra hiệu lực/văn bản sửa đổi",
                    "Ngành liên quan": str(event["affected_sectors"]),
                    "Loại bằng chứng": "sự kiện nguồn",
                    "source_id": sid,
                }
            )

    stale = any(str(row.get("Độ mới", "")).startswith("cũ") for row in rows)
    status = "partial" if quality_rows or stale or unverified_world_bank else "ok"
    summary = (
        "Dữ liệu demo là GIẢ LẬP, không phải số liệu thực. "
        if kind == "synthetic"
        else "Tóm tắt quan sát vĩ mô theo kỳ/đơn vị và nguồn đã lưu. "
    )
    if unverified_world_bank:
        summary += "World Bank trả chuỗi sửa đổi mới nhất; dữ liệu lịch sử không phải vintage đã xác minh tại ngày chốt. "
    if quality_rows:
        summary += f"Có {len(quality_rows)} cảnh báo thiếu/lỗi chỉ tiêu trong bảng chất lượng. "
    summary += "Các quan hệ với doanh nghiệp là cơ chế/giả thuyết cần kiểm chứng, không suy ra nhân quả từ tương quan."
    return sources, Section(
        title="Tổng quan vĩ mô",
        status=status,
        rows=rows,
        source_ids=[source.id for source in sources],
        summary=summary,
    )

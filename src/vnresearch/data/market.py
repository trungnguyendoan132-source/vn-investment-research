from datetime import date, timedelta
import hashlib
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from vnresearch.data.filings import source_optional, valid_url
from vnresearch.data.providers import fetch_prices
from vnresearch.domain.models import Mode, Section, Source, utcnow


def _issue(code, message, severity="warning"):
    return {"code": code, "message": message, "severity": severity, "component": "market"}


def normalize_prices(frame: pd.DataFrame, ticker: str, as_of: date) -> pd.DataFrame:
    required = {"ticker", "date", "open", "high", "low", "close", "volume", "price_unit", "source_url"}
    if not required.issubset(frame.columns):
        raise ValueError("CSV giá thiếu cột: " + ", ".join(sorted(required - set(frame.columns))))
    attrs = dict(frame.attrs)
    frame = frame.copy()
    frame["ticker"] = frame.ticker.astype(str).str.strip().str.upper()
    frame = frame.loc[frame.ticker == str(ticker).strip().upper()].copy()
    dates = frame.date.astype(str)
    if frame.date.isna().any() or not dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError("Ngày giá phải là YYYY-MM-DD đầy đủ, không được thiếu")
    try:
        frame["date"] = pd.to_datetime(dates, format="%Y-%m-%d", errors="raise").dt.date
    except (ValueError, TypeError) as exc:
        raise ValueError("Ngày giá không hợp lệ") from exc
    frame = frame.loc[frame.date <= as_of].sort_values("date").reset_index(drop=True)
    if frame.date.duplicated().any():
        raise ValueError("Trùng ngày giao dịch; cần chọn nguồn trước khi nhập")
    if not set(frame.price_unit.unique()).issubset({"VND", "thousand_VND"}):
        raise ValueError("price_unit chỉ nhận VND hoặc thousand_VND; không tự đoán đơn vị")
    for column in ["open", "high", "low", "close", "volume"]:
        if frame[column].map(lambda value: isinstance(value, (bool, np.bool_))).any():
            raise ValueError("Boolean không phải giá/khối lượng")
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column]).all():
            raise ValueError("Giá/khối lượng có số không hữu hạn")
    factor = frame.price_unit.map({"VND": 1, "thousand_VND": 1000})
    for column in ["open", "high", "low", "close"]:
        with np.errstate(over="ignore", invalid="ignore"):
            frame[column] = frame[column].astype(float) * factor
        if not np.isfinite(frame[column]).all():
            raise ValueError("Tràn số sau quy đổi giá sang VND")
    if ((frame[["open", "high", "low", "close"]] <= 0).any(axis=1) | (frame.volume < 0)).any():
        raise ValueError("Giá phải dương, khối lượng không âm")
    if (frame.volume % 1 != 0).any() or frame.volume.map(lambda value: int(value) > np.iinfo(np.int64).max).any():
        raise ValueError("Khối lượng phải là số cổ phiếu nguyên; không tự cắt phần thập phân")
    if "volume_unit" in frame and not frame.volume_unit.eq("shares").all():
        raise ValueError("volume_unit phải là shares; không tự đoán lô giao dịch")
    frame["volume"] = frame.volume.astype("int64")
    frame["volume_unit"] = "shares"
    if ((frame.high < frame[["open", "close", "low"]].max(axis=1)) |
            (frame.low > frame[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Quan hệ OHLC không hợp lệ")
    if not frame.source_url.map(lambda value: str(value).startswith("urn:demo:") or valid_url(str(value))).all():
        raise ValueError("Giá phải đi kèm HTTP(S) có host hoặc nhãn demo")
    demo = frame.source_url.astype(str).str.startswith("urn:demo:")
    if demo.any() and not demo.all():
        raise ValueError("Không trộn giá demo và nguồn thật trong một chuỗi")
    if "price_basis" not in frame:
        frame["price_basis"] = "unknown"
    allowed = {"raw", "split_adjusted", "total_return_adjusted", "unknown", "synthetic"}
    if not set(frame.price_basis.unique()).issubset(allowed) or frame.price_basis.nunique() > 1:
        raise ValueError("price_basis phải đồng nhất và được khai báo rõ")
    if demo.any():
        frame["price_basis"] = "synthetic"
    issues = []
    basis = str(frame.price_basis.iloc[0]) if len(frame) else "unknown"
    if basis == "unknown":
        issues.append(_issue("PRICE_ADJUSTMENT_UNKNOWN", "Chưa xác minh giá raw/điều chỉnh; không tính lợi suất hay drawdown"))
    elif basis == "raw":
        issues.append(_issue("RAW_PRICE_RETURN", "Chỉ báo dùng biến động giá raw; chưa loại ảnh hưởng chia tách/cổ tức"))
    synthetic = bool(demo.any() or basis == "synthetic")
    if synthetic:
        issues.append(_issue("SYNTHETIC_MARKET_INPUT", "Chuỗi giá giả lập; không dùng để quyết định đầu tư", "info"))
    frame["price_unit"] = "VND"
    frame["analysis_close"] = frame.close
    frame.attrs.update(attrs)
    frame.attrs.update(quality_issues=issues, price_basis=basis, analysis_basis=basis, synthetic=synthetic,
                       volume_unit="shares", dividend_policy="price_return_excludes_cash_dividends")
    return frame


def apply_corporate_actions(frame: pd.DataFrame, actions: pd.DataFrame, as_of: date) -> pd.DataFrame:
    required = {"ticker", "ex_date", "action_type", "source_url"}
    if not required.issubset(actions):
        raise ValueError("Corporate actions thiếu ticker/ex_date/action_type/source_url")
    frame = frame.copy()
    if frame.empty:
        return frame
    if frame.attrs.get("price_basis") not in {"raw", "unknown"}:
        raise ValueError("Không điều chỉnh lần hai chuỗi đã adjusted")
    actions = actions.loc[actions.ticker.astype(str).str.upper().eq(frame.ticker.iloc[0])].copy()
    if not actions.source_url.map(valid_url).all():
        raise ValueError("Corporate actions cần URL nguồn có host")
    if not actions.ex_date.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError("Ngày corporate action phải là YYYY-MM-DD đầy đủ")
    try:
        actions["ex_date"] = pd.to_datetime(actions.ex_date, format="%Y-%m-%d", errors="raise").dt.date
    except (ValueError, TypeError) as exc:
        raise ValueError("Ngày corporate action không hợp lệ") from exc
    if actions.ex_date.isna().any() or actions.duplicated(["ticker", "ex_date", "action_type"]).any():
        raise ValueError("Corporate action thiếu ngày hoặc trùng sự kiện")
    actions = actions.loc[actions.ex_date <= as_of].sort_values("ex_date")
    adjustment = pd.Series(1.0, index=frame.index)
    for row in actions.itertuples():
        if row.action_type == "split":
            raw_ratio = getattr(row, "split_ratio", float("nan"))
            if isinstance(raw_ratio, (bool, np.bool_)):
                raise ValueError("Boolean không phải split ratio")
            ratio = float(raw_ratio)
            if not np.isfinite(ratio) or ratio <= 0:
                raise ValueError("Split ratio phải hữu hạn và dương: cổ phiếu mới / cổ phiếu cũ")
            adjustment.loc[frame.date < row.ex_date] /= ratio
        elif row.action_type == "cash_dividend":
            amount = float(getattr(row, "cash_per_share", float("nan")))
            if not np.isfinite(amount) or amount < 0:
                raise ValueError("Cổ tức tiền mặt phải hữu hạn, không âm, đơn vị VND/share")
        else:
            raise ValueError("Chỉ hỗ trợ split và cash_dividend; không tự suy quyền mua")
    frame["analysis_close"] = frame.close * adjustment
    if not np.isfinite(frame.analysis_close).all() or (frame.analysis_close <= 0).any():
        raise ValueError("Giá sau điều chỉnh không hợp lệ")
    frame["adjustment_factor"] = adjustment
    frame.attrs["analysis_basis"] = "split_adjusted" if frame.attrs.get("price_basis") == "raw" else "unknown"
    frame.attrs["corporate_actions"] = [{**row, "ex_date": str(row["ex_date"])} for row in actions.to_dict("records")]
    frame.attrs["quality_issues"] = [issue for issue in frame.attrs.get("quality_issues", []) if issue["code"] != "RAW_PRICE_RETURN"]
    if frame.attrs.get("price_basis") == "unknown":
        frame.attrs["quality_issues"].append(_issue("ADJUSTMENT_REQUIRES_RAW_BASIS", "Nguồn chưa xác minh raw; không thể xác nhận đã tránh double-adjustment", "error"))
    return frame


def demo_prices(ticker: str, as_of: date) -> pd.DataFrame:
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(as_of - timedelta(days=150), as_of)
    close = 60000 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(days))))
    return pd.DataFrame({"ticker": ticker, "date": days.strftime("%Y-%m-%d"),
                         "open": close * 0.998, "high": close * 1.015, "low": close * 0.985,
                         "close": close, "volume": rng.integers(100000, 900000, len(days)),
                         "price_unit": "VND", "price_basis": "synthetic", "source_url": "urn:demo:synthetic-prices"})


def load_prices(ticker: str, as_of: date, mode: Mode, csv_path: Path | None, *, actions_path: Path | None = None,
                maximum_age_days: int = 7, provider_config=None):
    if maximum_age_days < 0:
        raise ValueError("maximum_age_days không âm")
    if csv_path:
        payload = csv_path.read_bytes()
        frame = normalize_prices(pd.read_csv(BytesIO(payload)), ticker, as_of)
        synthetic = frame.attrs.get("synthetic", False)
        source = Source(id="market", title="Giá giả lập được nhập" if synthetic else "Giá do người dùng nhập",
                        kind="synthetic" if synthetic else "user_supplied",
                        url=str(frame.source_url.iloc[-1]) if len(frame) else "urn:empty:prices",
                        retrieved_at=utcnow(), sha256=hashlib.sha256(payload).hexdigest(),
                        note="Hash thuộc đúng bytes đã parse. URLs từng phiên nằm trong CSV gốc; dữ liệu nhập chưa được xác minh độc lập.",
                        **source_optional(unit="VND", currency="VND", verification_status="synthetic" if synthetic else "unverified"))
    elif mode == Mode.DEMO:
        frame = normalize_prices(demo_prices(ticker, as_of), ticker, as_of)
        source = Source(id="market", title="Giá giả lập có hạt giống cố định", kind="synthetic",
                        url="urn:demo:synthetic-prices", retrieved_at=utcnow(), note="Không dùng để quyết định đầu tư",
                        **source_optional(unit="VND", currency="VND", verification_status="synthetic"))
    elif mode == Mode.LIVE:
        frame, provider = fetch_prices(ticker, as_of - timedelta(days=365), as_of, config=provider_config)
        frame = normalize_prices(frame, ticker, as_of)
        source = Source(id="market", title="KBS daily OHLCV - truy vấn trực tiếp có giới hạn", kind="live",
                        url=provider["request_url"], retrieved_at=utcnow(), sha256=provider["response_sha256"],
                        period=f"{provider['start']}/{provider['end']}",
                        note=f"{provider['contract_version']}; response bytes={provider['response_bytes']}; không retry; adjustment=unknown; contract={provider['contract_source']}",
                        **source_optional(unit="VND", currency="VND", mapping_version=provider["contract_version"],
                                          dataset_version=provider["response_sha256"], verification_status="provider_observed"))
    else:
        frame = pd.DataFrame()
        frame.attrs["quality_issues"] = [_issue("MARKET_UNAVAILABLE", "Chưa có nguồn giá")]
        return frame, [], Section(title="Giá và giao dịch", status="unavailable", summary="Chưa có giá. Nhập CSV có nguồn hoặc chọn adapter live.")
    sources = [source]
    if actions_path:
        action_payload = actions_path.read_bytes()
        actions = pd.read_csv(BytesIO(action_payload))
        frame = apply_corporate_actions(frame, actions, as_of)
        action_urls = actions.source_url.astype(str).drop_duplicates().tolist()
        sources.append(Source(id="market-actions", title="Corporate actions nhập có nguồn", kind="user_supplied",
                              url=action_urls[0] if action_urls else "urn:empty:actions", retrieved_at=utcnow(),
                              sha256=hashlib.sha256(action_payload).hexdigest(), note="Split factor=new/old shares; cổ tức tiền mặt không được cộng vào price return"))
    ids = [item.id for item in sources]
    if frame.empty:
        return frame, sources, Section(title="Giá và giao dịch", status="unavailable", summary="Không có giá tại hoặc trước ngày chốt.", source_ids=ids)
    issues = frame.attrs.get("quality_issues", [])
    last = frame.iloc[-1]
    age = (as_of - last.date).days
    if age > maximum_age_days:
        issues.append(_issue("STALE_MARKET_PRICE", f"Giá cuối cách ngày chốt {age} ngày", "error"))
    if frame.attrs.get("synthetic") and mode != Mode.DEMO:
        issues.append(_issue("SYNTHETIC_OUTSIDE_DEMO", "Nguồn là giả lập dù request không ở demo", "error"))
    basis = frame.attrs.get("analysis_basis", "unknown")
    series = frame.analysis_close
    returns = series.pct_change().dropna() if basis != "unknown" else pd.Series(dtype=float)
    data = {"Ngày giá": str(last.date), "Giá đóng cửa (VND)": float(last.close), "Khối lượng (shares)": int(last.volume),
            "Cơ sở chỉ báo": basis, "SMA20 (VND)": float(series.tail(20).mean()) if len(frame) >= 20 else None,
            "Lợi suất giá 20 phiên": float(series.iloc[-1] / series.iloc[-21] - 1) if len(frame) >= 21 and basis != "unknown" else None,
            "Biến động năm hóa (252 phiên)": float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) >= 20 else None,
            "Sụt giảm tối đa trong cửa sổ": float((series / series.cummax() - 1).min()) if basis != "unknown" else None}
    frame.attrs.update(quality_issues=issues, source_urls=frame.source_url.drop_duplicates().tolist(), freshness_days=age)
    partial = any(issue["severity"] == "error" for issue in issues) or basis == "unknown"
    summary = f"{len(frame)} phiên đến {last.date}; giá VND, volume shares; cơ sở {basis}. Price return không gồm cổ tức tiền mặt; lịch nghỉ/suspension chưa xác minh."
    if issues:
        summary += " " + " ".join(issue["message"] for issue in issues)
    return frame, sources, Section(title="Giá và giao dịch", status="partial" if partial else "ok", rows=[data], source_ids=ids, summary=summary)

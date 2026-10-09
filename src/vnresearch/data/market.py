from datetime import date, timedelta
import hashlib
import os
from pathlib import Path

import numpy as np
import pandas as pd

from vnresearch.domain.models import Mode, Section, Source, utcnow


def normalize_prices(frame: pd.DataFrame, ticker: str, as_of: date) -> pd.DataFrame:
    required = {"ticker", "date", "open", "high", "low", "close", "volume", "price_unit", "source_url"}
    if not required.issubset(frame.columns):
        raise ValueError("CSV giá thiếu cột: " + ", ".join(sorted(required - set(frame.columns))))
    frame = frame.copy()
    frame["ticker"] = frame.ticker.astype(str).str.strip().str.upper()
    frame = frame.loc[frame.ticker == ticker].copy()
    frame["date"] = pd.to_datetime(frame.date, format="%Y-%m-%d", errors="raise").dt.date
    frame = frame.loc[frame.date <= as_of].sort_values("date")
    if frame.date.duplicated().any():
        raise ValueError("Trùng ngày giao dịch; cần chọn nguồn trước khi nhập")
    if not set(frame.price_unit.unique()).issubset({"VND", "thousand_VND"}):
        raise ValueError("price_unit chỉ nhận VND hoặc thousand_VND; không tự đoán đơn vị")
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column]).all():
            raise ValueError("Giá/khối lượng có số không hữu hạn")
    factor = frame.price_unit.map({"VND": 1, "thousand_VND": 1000})
    for column in ["open", "high", "low", "close"]:
        frame[column] *= factor
    if ((frame[["open", "high", "low", "close"]] <= 0).any(axis=1) | (frame.volume < 0)).any():
        raise ValueError("Giá phải dương, khối lượng không âm")
    if ((frame.high < frame[["open", "close", "low"]].max(axis=1)) |
            (frame.low > frame[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Quan hệ OHLC không hợp lệ")
    if not frame.source_url.astype(str).str.startswith(("https://", "http://", "urn:demo:")).all():
        raise ValueError("Giá phải đi kèm URL nguồn hoặc nhãn dữ liệu demo")
    frame["price_unit"] = "VND"
    return frame


def demo_prices(ticker: str, as_of: date) -> pd.DataFrame:
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(as_of - timedelta(days=150), as_of)
    close = 60000 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(days))))
    return pd.DataFrame({"ticker": ticker, "date": days.strftime("%Y-%m-%d"),
                         "open": close * 0.998, "high": close * 1.015, "low": close * 0.985,
                         "close": close, "volume": rng.integers(100000, 900000, len(days)),
                         "price_unit": "VND", "source_url": "urn:demo:synthetic-prices"})


def load_prices(ticker: str, as_of: date, mode: Mode, csv_path: Path | None):
    if csv_path:
        frame = normalize_prices(pd.read_csv(csv_path), ticker, as_of)
        source = Source(id="market", title="Giá do người dùng nhập", kind="user_supplied",
                        url=str(frame.source_url.iloc[-1]) if len(frame) else "urn:empty:prices",
                        retrieved_at=utcnow(), sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                        note="Đơn vị đầu vào khai báo rõ; chưa xác minh độc lập tính đúng của nguồn nhập.")
    elif mode == Mode.DEMO:
        frame = normalize_prices(demo_prices(ticker, as_of), ticker, as_of)
        source = Source(id="market", title="Giá giả lập có hạt giống cố định", kind="synthetic",
                        url="urn:demo:synthetic-prices", retrieved_at=utcnow(), note="Không dùng để quyết định đầu tư")
    elif mode == Mode.LIVE:
        try:
            from vnstock import Market
        except ImportError as exc:
            raise ValueError("Cài vnstock theo tài liệu nhà cung cấp hoặc nhập CSV giá có nguồn") from exc
        unit = os.environ.get("VNRESEARCH_VNSTOCK_PRICE_UNIT")
        if unit not in {"VND", "thousand_VND"}:
            raise ValueError("Phải xác nhận VNRESEARCH_VNSTOCK_PRICE_UNIT từ nguồn trước khi gọi giá live")
        os.environ.setdefault("VNSTOCK_DISABLE_AGENT_SETUP", "1")
        frame = Market().equity.ohlcv(symbol=ticker, start=str(as_of - timedelta(days=365)), end=str(as_of))
        frame = frame.rename(columns={"time": "date"})
        frame["ticker"], frame["price_unit"], frame["source_url"] = ticker, unit, "https://github.com/thinh-vu/vnstock"
        frame["date"] = pd.to_datetime(frame.date).dt.strftime("%Y-%m-%d")
        frame = normalize_prices(frame, ticker, as_of)
        source = Source(id="market", title="OHLCV qua vnstock Market", kind="live",
                        url="https://github.com/thinh-vu/vnstock", retrieved_at=utcnow(),
                        note="Đơn vị được cấu hình tường minh. Adapter chưa được xác nhận với tài khoản nhà cung cấp trong lần dựng repo.")
    else:
        return pd.DataFrame(), [], Section(title="Giá và giao dịch", status="unavailable",
                                          summary="Chưa có giá. Nhập CSV có nguồn hoặc cấu hình adapter live.")
    if frame.empty:
        return frame, [source], Section(title="Giá và giao dịch", status="unavailable", summary="Không có giá tại hoặc trước ngày chốt.", source_ids=[source.id])
    returns = frame.close.pct_change().dropna()
    last = frame.iloc[-1]
    data = {"Ngày giá": str(last.date), "Giá đóng cửa (VND)": float(last.close),
            "Khối lượng": int(last.volume), "SMA20 (VND)": float(frame.close.tail(20).mean()) if len(frame) >= 20 else None,
            "Lợi suất 20 phiên": float(last.close / frame.close.iloc[-21] - 1) if len(frame) >= 21 else None,
            "Biến động năm hóa": float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) >= 20 else None,
            "Sụt giảm tối đa trong cửa sổ": float((frame.close / frame.close.cummax() - 1).min())}
    return frame, [source], Section(title="Giá và giao dịch", status="ok", rows=[data], source_ids=[source.id],
                                    summary=f"{len(frame)} phiên đến {last.date}; giá đã chuẩn hóa VND. Lợi suất chưa điều chỉnh cổ tức/chia tách nếu nguồn không cung cấp giá điều chỉnh.")

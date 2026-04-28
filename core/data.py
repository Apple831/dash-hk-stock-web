# ══════════════════════════════════════════════════════════════════
# data.py -- 數據下載、緩存、TradingView 篩選
# ══════════════════════════════════════════════════════════════════
#
# V18 修復（2026-04-27）-- 來自 V17.0 策略複審報告 🟡-6：
#   • filter_anomalies 改為「標記不刪除」
#   • 原版直接 drop 異常 bar 會在時序中製造空洞，
#     讓 EMA 把「上週四」當「昨天」算，污染指標。
#   • 新版加 "is_anomaly" 欄位，下游可用 .where() 排除而不破壞時序。
# ══════════════════════════════════════════════════════════════════

import os
import time
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import requests

from config import TV_URL, TV_HEADERS
from indicators import calculate_indicators


# ── 股票清單 ───────────────────────────────────────────────────────
def load_stocks_from_file() -> list:
    if os.path.exists("stocks.txt"):
        stocks = [
            line.split("#")[0].strip()
            for line in open("stocks.txt", "r", encoding="utf-8")
            if ".HK" in line
        ]
        if stocks:
            return stocks
    return ["0700.HK", "9988.HK", "3690.HK"]


def load_stocks() -> list:
    if st.session_state.get("stocks"):
        return st.session_state["stocks"]
    stocks = load_stocks_from_file()
    st.session_state["stocks"] = stocks
    return stocks


# ── 時區安全處理 ────────────────────────────────────────────────────
def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    try:
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Hong_Kong").tz_localize(None)
        else:
            df.index = pd.to_datetime(df.index)
    except Exception:
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    return df


# ── MultiIndex 展平 ─────────────────────────────────────────────────
def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ── 異常值標記（🟡-6 V18 修復）────────────────────────────────────
# 舊版直接 drop 異常 bar，會在時序中製造空洞，讓 EMA 把「上週四」當「昨天」。
# 新版改為加 "is_anomaly" 欄位，OHLC 保留原值。下游若需排除，可：
#   df = df[~df["is_anomaly"]]   # 真要 drop
#   df["Close"].where(~df["is_anomaly"])  # 計算指標時排除但保時序
# 預設不影響任何下游使用（is_anomaly 只是個附加欄位）。
def filter_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    vol_ma    = df["Volume"].rolling(20, min_periods=10).median()
    price_chg = df["Close"].pct_change().abs()
    vol_bad   = vol_ma.notna() & (df["Volume"] > vol_ma * 10)
    price_bad = price_chg > 0.50
    df["is_anomaly"] = (vol_bad | price_bad).fillna(False)
    return df


# ── 單股下載（加 10 分鐘快取，避免同一 ticker 重複下載）────────────
# ttl=600：10 分鐘內再次請求同一 (ticker, period) 直接返回快取結果
# 適用場景：分析 Tab、掃描 Tab 在同一 session 多次呼叫同一股票
# 注意：手動「清除緩存」只清 session_state["stock_cache"]，
#       st.cache_data 的快取由 Streamlit 獨立管理，需重啟才清除。
@st.cache_data(ttl=600, show_spinner=False)
def get_stock_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    try:
        if ticker == "^HSTECH":
            for sym in ["800700.HK", "^HSTECH", "3032.HK"]:
                df = yf.download(sym, period=period, progress=False, auto_adjust=True)
                if not df.empty:
                    break
        elif ticker == "^HSI":
            for sym in ["^HSI", "2800.HK"]:
                df = yf.download(sym, period=period, progress=False, auto_adjust=True)
                if not df.empty:
                    break
        else:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=True)

        if df.empty:
            return pd.DataFrame()
        df = flatten_columns(df)
        df = normalize_index(df)
        df = df.dropna(subset=["Close"])
        df = filter_anomalies(df)   # 只加 is_anomaly 欄位，不再 drop
        return df
    except Exception:
        return pd.DataFrame()


# ── 批量下載 ────────────────────────────────────────────────────────
def batch_download(tickers: list, period: str = "1y") -> dict:
    cache = {}
    batch_size = 10  # 每批 10 隻，減少 Yahoo Finance 限速風險

    for batch_start in range(0, len(tickers), batch_size):
        batch = tickers[batch_start : batch_start + batch_size]
        try:
            raw = yf.download(
                batch, period=period,
                progress=False, auto_adjust=True,
                group_by="ticker", threads=True,
            )
        except Exception:
            time.sleep(1.5)
            continue

        if raw.empty:
            time.sleep(1.5)
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = raw.columns.get_level_values(0).unique().tolist()
            ohlcv = {"Open", "High", "Low", "Close", "Volume"}
            ticker_level = 1 if set(lvl0) & ohlcv else 0
        else:
            ticker_level = None

        for ticker in batch:
            try:
                if ticker_level is None:
                    df = raw.copy()
                elif ticker_level == 1:
                    if ticker not in raw.columns.get_level_values(1):
                        continue
                    df = raw.xs(ticker, axis=1, level=1).copy()
                else:
                    if ticker not in raw.columns.get_level_values(0):
                        continue
                    df = raw.xs(ticker, axis=1, level=0).copy()

                df = flatten_columns(df)
                df = normalize_index(df)
                df = df.dropna(subset=["Close"])
                if len(df) < 60:
                    continue
                cache[ticker] = calculate_indicators(df)
            except Exception:
                continue

        # 批次之間稍作等待，避免 Yahoo Finance 限速
        if batch_start + batch_size < len(tickers):
            time.sleep(1.5)

    return cache


# ── TradingView Screener ──────────────────────────────────────────
def fetch_stocks_from_tradingview(
    min_cap_hkd: int = 10_000_000_000,
    min_vol_hkd: int = 50_000_000,
    min_price_hkd: float = 5.0,
    min_roe_pct: float = 8.0,
) -> list:
    payload = {
        "filter": [
            {"left": "market_cap_basic",             "operation": "greater", "right": min_cap_hkd / 7.8},
            {"left": "earnings_per_share_basic_ttm", "operation": "greater", "right": 0},
            {"left": "average_volume_30d_calc",      "operation": "greater", "right": min_vol_hkd / 7.8},
            {"left": "close",                        "operation": "greater", "right": 5.0},
        ],
        "columns": ["name", "description", "close", "market_cap_basic",
                    "earnings_per_share_basic_ttm", "average_volume_30d_calc",
                    "return_on_equity"],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, 1000],
    }
    resp = requests.post(TV_URL, headers=TV_HEADERS, json=payload, timeout=20)
    resp.raise_for_status()
    tickers = []
    for row in resp.json().get("data", []):
        d = row.get("d", [])
        if not d:
            continue
        try:
            tickers.append(f"{int(d[0]):04d}.HK")
        except (ValueError, TypeError):
            continue
    return tickers


# ── Cache 助手 ────────────────────────────────────────────────────
def get_cached(ticker: str) -> pd.DataFrame:
    cache = st.session_state.get("stock_cache", {})
    if ticker in cache:
        return cache[ticker]
    df = get_stock_data(ticker)
    if not df.empty:
        return calculate_indicators(df)
    return pd.DataFrame()


def get_cache_label() -> str:
    ts = st.session_state.get("cache_time")
    n  = len(st.session_state.get("stock_cache", {}))
    if ts and n:
        return f"✅ 已緩存 {n} 隻｜{ts}"
    return "⚠️ 尚未緩存"

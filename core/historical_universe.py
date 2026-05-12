import json
from datetime import datetime
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).parent.parent
_PRICES_DIR = _PROJECT_ROOT / "data" / "eodhd_prices"


def load_eodhd_prices(ticker: str) -> pd.DataFrame:
    """
    讀取 data/eodhd_prices/0700.HK.json
    返回 DataFrame，index 為日期，欄位：open/high/low/close/volume
    找不到文件返回空 DataFrame
    """
    file_path = _PRICES_DIR / f"{ticker}.json"
    try:
        if not file_path.exists():
            return pd.DataFrame()
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        return df[cols]
    except Exception:
        return pd.DataFrame()


def get_historical_universe(
    date: datetime,
    min_price: float = 5.0,
    min_turnover_hkd: float = 50_000_000,
    min_bars: int = 62,
) -> list:
    """
    返回該日期符合條件的股票代碼清單（如 ["0700.HK", "9988.HK", ...]）
    date 之後的數據不使用（防止前視偏差）
    """
    if not _PRICES_DIR.exists():
        return []

    cutoff = pd.Timestamp(date)
    result = []

    for json_file in _PRICES_DIR.glob("*.json"):
        ticker = json_file.stem
        try:
            df = load_eodhd_prices(ticker)
            if df.empty:
                continue

            df = df[df.index <= cutoff]

            if len(df) < min_bars:
                continue

            last_close = df.iloc[-1]["close"]
            if last_close < min_price:
                continue

            last_30 = df.tail(30)
            avg_turnover = (last_30["close"] * last_30["volume"]).mean()
            if avg_turnover < min_turnover_hkd:
                continue

            result.append(ticker)
        except Exception:
            continue

    return sorted(result)


def get_universe_cache(dates: list, **kwargs) -> dict:
    """
    批量計算多個日期的股票池，返回 {date: [tickers]} 字典
    避免 walk_forward 每個 fold 重複計算
    """
    if not _PRICES_DIR.exists():
        return {d: [] for d in dates}

    min_price = kwargs.get("min_price", 5.0)
    min_turnover_hkd = kwargs.get("min_turnover_hkd", 50_000_000)
    min_bars = kwargs.get("min_bars", 62)

    all_dfs = {}
    for json_file in _PRICES_DIR.glob("*.json"):
        ticker = json_file.stem
        try:
            df = load_eodhd_prices(ticker)
            if not df.empty:
                all_dfs[ticker] = df
        except Exception:
            continue

    cache = {}
    for date in dates:
        cutoff = pd.Timestamp(date)
        result = []
        for ticker, df in all_dfs.items():
            try:
                df_cut = df[df.index <= cutoff]
                if len(df_cut) < min_bars:
                    continue
                if df_cut.iloc[-1]["close"] < min_price:
                    continue
                last_30 = df_cut.tail(30)
                avg_turnover = (last_30["close"] * last_30["volume"]).mean()
                if avg_turnover < min_turnover_hkd:
                    continue
                result.append(ticker)
            except Exception:
                continue
        cache[date] = sorted(result)

    return cache


if __name__ == "__main__":
    test_dates = [
        datetime(2020, 1, 1),
        datetime(2021, 6, 1),
        datetime(2023, 1, 1),
    ]

    for d in test_dates:
        universe = get_historical_universe(d)
        print(f"\n{d.strftime('%Y-%m-%d')} 股票池: {len(universe)} 隻")
        print(f"前10隻: {universe[:10]}")

    stocks_txt = _PROJECT_ROOT / "stocks.txt"
    if stocks_txt.exists():
        with open(stocks_txt, encoding="utf-8") as f:
            current = [line.strip() for line in f if line.strip()]
        print(f"\n現有 stocks.txt: {len(current)} 隻")

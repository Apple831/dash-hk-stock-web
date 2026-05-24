import json
from datetime import datetime
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).parent.parent
_PRICES_DIR = _PROJECT_ROOT / "data" / "eodhd_prices"

# 確定性錨定：必活躍大型股，用於新鮮度檢查（避免純隨機抽樣誤報/漏報）
_FRESHNESS_ANCHORS = ["0700.HK", "0005.HK", "9988.HK", "0939.HK", "1299.HK"]


def _check_data_freshness(cutoff: pd.Timestamp) -> None:
    """
    檢查 EODHD 數據是否覆蓋到 cutoff（= WF 實際會用到的最遠日期，通常是最後一個
    Fold 的 OOS 結束日 / ref_df 末日），超出 90 天即警告。

    修正（2026-05-24）：
      1. cutoff 由呼叫端傳入「實際數據需求上界」，不再用 IS 起始日 —— 舊版以 IS 起始日
         判斷，盲區寬度等於整個 OOS 窗口（末 Fold OOS 落在缺口卻不報警，被靜默跳過）。
      2. 先讀固定錨定大型股的 max 日期（確定性），再補隨機抽樣 —— 舊版純隨機抽 20 檔，
         若抽樣全落在退市/停更股，max 日期會被低估而誤報，或漏報。
    """
    _prices_max_date = None

    # 候選檔：先錨定大型股，再補隨機抽樣
    candidate_files = []
    for _a in _FRESHNESS_ANCHORS:
        _f = _PRICES_DIR / f"{_a}.json"
        if _f.exists():
            candidate_files.append(_f)

    all_files = list(_PRICES_DIR.glob("*.json"))
    if all_files:
        import random
        candidate_files += random.sample(all_files, min(20, len(all_files)))

    for _f in candidate_files:
        try:
            import json as _json
            _records = _json.loads(_f.read_text(encoding="utf-8"))
            if _records:
                _last = max(r["date"] for r in _records)
                if _prices_max_date is None or _last > _prices_max_date:
                    _prices_max_date = _last
        except Exception:
            pass

    if _prices_max_date and cutoff > pd.Timestamp(_prices_max_date) + pd.Timedelta(days=90):
        import warnings
        warnings.warn(
            f"[PIT WARN] EODHD 數據截至 {_prices_max_date}，"
            f"但 WF 需用到 {cutoff.date()}（含最後 Fold 的 OOS），"
            f"超出 90 天。落在缺口的 Fold 會被靜默跳過，PIT 結果不可信。"
            f"請執行 scripts/eodhd_incremental_update.py 補充數據。",
            UserWarning,
            stacklevel=3,
        )


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
        df.index = pd.to_datetime(df.index)
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume',
            'adjusted_close': 'Adj Close',
        }, inplace=True)
        # EODHD 的 OHLC 為未復權原始價，只有 adjusted_close 已復權。
        # 直接用原始 OHLC 算 EMA/RSI/布林帶，會在拆股/派息日出現假跳空，指標失真數十天。
        # 用 factor = Adj Close / Close 把 OHLC 全部縮放到復權基準，volume 不調整。
        if "Adj Close" in df.columns:
            factor = df["Adj Close"] / df["Close"]
            for _col in ["Open", "High", "Low", "Close"]:
                if _col in df.columns:
                    df[_col] = df[_col] * factor
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[cols]
        if not df.empty and len(df) >= 62:
            from data import filter_anomalies
            from indicators import calculate_indicators
            df = filter_anomalies(df)
            df = calculate_indicators(df)
        return df
    except Exception:
        return pd.DataFrame()


def get_historical_universe(
    date: datetime,
    min_price: float = 5.0,
    min_turnover_hkd: float = 50_000_000,
    min_bars: int = 62,
    needed_through=None,
) -> list:
    """
    返回該日期符合條件的股票代碼清單（如 ["0700.HK", "9988.HK", ...]）
    date 之後的數據不使用（防止前視偏差）

    needed_through：WF 實際會用到的最遠日期（OOS 結束日）。新鮮度檢查以此為準；
                    未傳則退回用 date（向後相容，但盲區較大）。
    """
    if not _PRICES_DIR.exists():
        return []

    cutoff = pd.Timestamp(date)
    # ── PIT 數據新鮮度檢查（用實際需求上界，而非股票池判定日）──────
    _freshness_cutoff = pd.Timestamp(needed_through) if needed_through is not None else cutoff
    _check_data_freshness(_freshness_cutoff)
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

            last_close = df.iloc[-1]["Close"]
            if last_close < min_price:
                continue

            last_30 = df.tail(30)
            avg_turnover = (last_30["Close"] * last_30["Volume"]).mean()
            if avg_turnover < min_turnover_hkd:
                continue

            result.append(ticker)
        except Exception:
            continue

    return sorted(result)


def get_universe_cache(dates: list, needed_through=None, **kwargs) -> dict:
    """
    批量計算多個日期的股票池，返回 {date: [tickers]} 字典
    避免 walk_forward 每個 fold 重複計算

    needed_through：WF 實際會用到的最遠日期（OOS 結束日 / ref_df 末日）。
                    新鮮度檢查以此為準；未傳則退回用 max(dates)（向後相容，盲區較大）。
    """
    if not _PRICES_DIR.exists():
        return {d: [] for d in dates}

    min_price = kwargs.get("min_price", 5.0)
    min_turnover_hkd = kwargs.get("min_turnover_hkd", 50_000_000)
    min_bars = kwargs.get("min_bars", 62)

    # ── PIT 數據新鮮度檢查（用實際需求上界，而非最後 Fold 的 IS 起始日）──
    if dates:
        _freshness_cutoff = (
            pd.Timestamp(needed_through) if needed_through is not None
            else pd.Timestamp(max(dates))
        )
        _check_data_freshness(_freshness_cutoff)

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
                if df_cut.iloc[-1]["Close"] < min_price:
                    continue
                last_30 = df_cut.tail(30)
                avg_turnover = (last_30["Close"] * last_30["Volume"]).mean()
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
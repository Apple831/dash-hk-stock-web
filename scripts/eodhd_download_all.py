import os
import json
import time
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://eodhd.com/api"
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "eodhd_prices"
STOCKS_FILE = ROOT / "stocks.txt"
FROM_DATE = "2019-01-01"
# 修正（2026-05-24）：TO_DATE 改為動態今日，避免全量重抓時又退回 2024-12 缺口。
TO_DATE = datetime.today().strftime("%Y-%m-%d")


def load_local_tickers() -> set:
    tickers = set()
    for line in STOCKS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tickers.add(line)
    return tickers


def fetch_exchange_tickers(api_key: str) -> set:
    url = f"{BASE_URL}/exchange-symbol-list/HK"
    resp = requests.get(url, params={"api_token": api_key, "fmt": "json"}, timeout=30)
    resp.raise_for_status()
    tickers = set()
    for item in resp.json():
        code = item.get("Code", "")
        if not code:
            continue
        # EODHD returns 5-char codes like "00700" → strip leading zeros → pad to 4 → "0700.HK"
        normalized = code.lstrip("0").zfill(4)
        tickers.add(f"{normalized}.HK")
    return tickers


def download_eod(ticker: str, api_key: str) -> list:
    url = f"{BASE_URL}/eod/{ticker}"
    resp = requests.get(
        url,
        params={"api_token": api_key, "fmt": "json", "from": FROM_DATE, "to": TO_DATE},
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def main():
    api_key = os.environ.get("EODHD_API_KEY")
    if not api_key:
        sys.exit("錯誤：環境變數 EODHD_API_KEY 未設定")

    print(f"下載區間：{FROM_DATE} → {TO_DATE}")
    print("讀取 stocks.txt ...")
    local_tickers = load_local_tickers()
    print(f"  本地清單：{len(local_tickers)} 隻")

    print("查詢 EODHD 港交所完整股票清單 ...")
    exchange_tickers = fetch_exchange_tickers(api_key)
    print(f"  交易所清單：{len(exchange_tickers)} 隻")

    all_tickers = sorted(local_tickers | exchange_tickers)
    print(f"合併去重後：{len(all_tickers)} 隻\n")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    success, failed = [], []
    total_records = 0

    for i, ticker in enumerate(all_tickers, start=1):
        data = download_eod(ticker, api_key)
        time.sleep(0.1)

        if data:
            out_path = DATA_DIR / f"{ticker}.json"
            out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            success.append(ticker)
            total_records += len(data)
        else:
            failed.append(ticker)

        if i % 50 == 0:
            print(f"[{i}/{len(all_tickers)}] 進度更新 — 已成功 {len(success)} 隻，失敗 {len(failed)} 隻")

    print("\n=== 下載完成 ===")
    print(f"成功：{len(success)} 隻")
    print(f"失敗：{len(failed)} 隻" + (f" → {failed}" if failed else ""))
    print(f"總數據筆數：{total_records:,}")


if __name__ == "__main__":
    main()
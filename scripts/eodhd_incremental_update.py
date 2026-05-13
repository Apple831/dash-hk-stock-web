import os
import json
import time
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

BASE_URL = "https://eodhd.com/api"
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "eodhd_prices"
SKIP_THRESHOLD_BDAYS = 3


def business_days_since(last_date_str: str) -> int:
    last = datetime.strptime(last_date_str, "%Y-%m-%d").date()
    today = datetime.today().date()
    return int(np.busday_count(last, today))


def download_eod_range(ticker: str, api_key: str, from_date: str, to_date: str) -> list:
    url = f"{BASE_URL}/eod/{ticker}"
    resp = requests.get(
        url,
        params={"api_token": api_key, "fmt": "json", "from": from_date, "to": to_date},
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

    json_files = sorted(DATA_DIR.glob("*.HK.json"))
    if not json_files:
        sys.exit(f"錯誤：{DATA_DIR} 底下找不到任何 *.HK.json 文件")

    total = len(json_files)
    updated = 0
    new_records = 0
    failed = []
    today_str = datetime.today().strftime("%Y-%m-%d")

    print(f"掃描 {total} 個 JSON 文件（截至今天 {today_str}）...\n")

    for i, file_path in enumerate(json_files, start=1):
        ticker = file_path.stem  # e.g. "0001.HK"

        try:
            existing = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            failed.append(ticker)
            continue

        if not existing:
            continue

        last_date = max(r["date"] for r in existing)
        bdays = business_days_since(last_date)

        if bdays <= SKIP_THRESHOLD_BDAYS:
            if i % 50 == 0:
                print(f"[{i}/{total}] 進度更新 — 已更新 {updated} 隻，失敗 {len(failed)} 隻")
            continue

        new_data = download_eod_range(ticker, api_key, last_date, today_str)
        time.sleep(0.1)

        if new_data:
            combined = {r["date"]: r for r in existing}
            combined.update({r["date"]: r for r in new_data})
            sorted_combined = sorted(combined.values(), key=lambda r: r["date"])
            added = len(sorted_combined) - len(existing)
            new_records += added
            file_path.write_text(json.dumps(sorted_combined, ensure_ascii=False), encoding="utf-8")
            updated += 1

        if i % 50 == 0:
            print(f"[{i}/{total}] 進度更新 — 已更新 {updated} 隻，失敗 {len(failed)} 隻")

    print(f"\n✅ 更新完成 | 檢查 {total} 隻 | 更新 {updated} 隻 | 新增 {new_records} 筆 | 失敗 {len(failed)} 隻")
    if failed:
        print(f"失敗清單：{failed}")


if __name__ == "__main__":
    main()

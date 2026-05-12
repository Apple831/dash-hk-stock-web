import json
import os
import random
import sys
from pathlib import Path

import requests

BASE_URL = "https://eodhd.com/api"
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


def get_api_key() -> str:
    key = os.environ.get("EODHD_API_KEY")
    if not key:
        print("錯誤：未設定環境變數 EODHD_API_KEY，請先執行：")
        print("  $env:EODHD_API_KEY = '你的API金鑰'")
        sys.exit(1)
    return key


def fetch_delisted(api_key: str) -> list:
    url = f"{BASE_URL}/exchange-symbol-list/HK"
    params = {"api_token": api_key, "fmt": "json", "delisted": 1}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(f"\n港交所退市股票總數：{len(data)} 隻")
    return data


def filter_by_year(delisted: list, start: str = "2019-01-01", end: str = "2024-12-31") -> list:
    filtered = [
        s for s in delisted
        if s.get("delisted_at") and start <= s["delisted_at"] <= end
    ]
    print(f"2019–2024 年間退市數量：{len(filtered)} 隻\n")
    print(f"{'代碼':<12} {'名稱':<40} 退市日期")
    print("-" * 66)
    for s in filtered[:20]:
        print(f"{s.get('Code', ''):<12} {s.get('Name', '')[:38]:<40} {s['delisted_at']}")
    return filtered


def fetch_eod(ticker: str, api_key: str) -> list:
    url = f"{BASE_URL}/eod/{ticker}.HK"
    params = {
        "api_token": api_key,
        "fmt": "json",
        "from": "2019-01-01",
        "to": "2024-12-31",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def save_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n退市清單已儲存至：{path}")


def main():
    api_key = get_api_key()

    # 步驟 2：抓取退市清單
    all_delisted = fetch_delisted(api_key)

    # 步驟 3：篩選 2019–2024
    filtered = filter_by_year(all_delisted)

    if not filtered:
        print("篩選結果為空，無法進行後續操作。")
        sys.exit(0)

    # 步驟 4：隨機抽一隻，下載 EOD 歷史
    sample = random.choice(filtered)
    ticker = sample["Code"]
    print(f"\n隨機抽選：{ticker}（{sample.get('Name', '')}），退市日：{sample['delisted_at']}")

    try:
        prices = fetch_eod(ticker, api_key)
        print(f"EOD 數據筆數：{len(prices)} 筆")
        if prices:
            print(f"\n{'日期':<14} {'開盤':>8} {'最高':>8} {'最低':>8} {'收盤':>8} {'成交量':>12}")
            print("-" * 62)
            for row in prices[:5]:
                print(
                    f"{row.get('date', ''):<14}"
                    f"{row.get('open', 0):>8.3f}"
                    f"{row.get('high', 0):>8.3f}"
                    f"{row.get('low', 0):>8.3f}"
                    f"{row.get('close', 0):>8.3f}"
                    f"{row.get('volume', 0):>12,}"
                )
    except requests.HTTPError as e:
        print(f"下載 EOD 失敗：{e}")

    # 步驟 5：儲存完整退市清單
    save_json(all_delisted, DATA_DIR / "delisted_hk.json")


if __name__ == "__main__":
    main()

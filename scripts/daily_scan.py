"""
每日自動掃描 + Telegram 通知

港股收盤後（HKT 16:30 / UTC 08:30）由 Render cron job 觸發。
掃描 stocks.txt 全部股票，對 ACTIVE_PRESETS 5 個策略做 AND 邏輯買入訊號判斷。
有命中 → 發 Telegram；無命中 → 靜默退出。
失敗 → 印 log 並 exit(1)，讓 Render 顯示 cron 失敗。
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import requests

from data import load_stocks, get_stock_data
from indicators import calculate_indicators, precompute_signals
from regime import detect_regime
from config import ACTIVE_PRESETS, MIN_BARS_FOR_INDICATORS


def detect_hsi_regime() -> str:
    raw = get_stock_data("^HSI", "1y")
    if raw.empty:
        return "未知"
    df = calculate_indicators(raw)
    return detect_regime(df).get("label", "未知")


def scan_all() -> list[dict]:
    preset_active = {
        name: [f"b{i+1}" for i, v in enumerate(p["buy"]) if v]
        for name, p in ACTIVE_PRESETS.items()
    }

    hits: list[dict] = []
    tickers = load_stocks()
    print(f"[SCAN] 掃描 {len(tickers)} 隻股票，{len(preset_active)} 個策略", flush=True)

    for ticker in tickers:
        try:
            raw = get_stock_data(ticker, "3mo")
            if raw.empty or len(raw) < MIN_BARS_FOR_INDICATORS:
                continue
            df = calculate_indicators(raw)
            sigs = precompute_signals(df)

            matched = []
            for name, active in preset_active.items():
                if not active:
                    continue
                if all(bool(sigs[b].iloc[-1]) for b in active):
                    matched.append(name)

            if not matched:
                continue

            last = df.iloc[-1]
            hits.append({
                "ticker":  ticker,
                "rsi":     round(float(last["RSI"]), 1),
                "price":   round(float(last["Close"]), 2),
                "presets": matched,
            })
        except Exception as e:
            print(f"[SCAN][{ticker}] {type(e).__name__}: {e}", flush=True)

    preset_order = {name: i for i, name in enumerate(ACTIVE_PRESETS)}
    hits.sort(key=lambda h: (preset_order[h["presets"][0]], h["rsi"]))
    return hits


def build_message(hits: list[dict], regime_label: str, date_str: str) -> str:
    lines = [
        "🏹 港股狙擊手 每日掃描",
        f"📅 {date_str}",
        f"🌍 制度：{regime_label}",
        "",
        "🟢 買入訊號：",
    ]
    for h in hits:
        presets_str = ", ".join(h["presets"])
        lines.append(
            f"• {h['ticker']}｜{presets_str}｜RSI={h['rsi']}｜現價 {h['price']}"
        )
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
    resp.raise_for_status()


def main() -> int:
    hkt_now = datetime.now(timezone(timedelta(hours=8)))
    date_str = hkt_now.strftime("%Y-%m-%d")

    try:
        regime_label = detect_hsi_regime()
        hits = scan_all()

        if not hits:
            print(f"[SCAN] {date_str} 無命中，發送心跳", flush=True)
            heartbeat = (
                f"📡 港股狙擊手 每日掃描\n"
                f"📅 {date_str}\n"
                f"🌍 制度：{regime_label}\n"
                f"\n"
                f"✅ 今日無買入訊號，持倉不變"
            )
            send_telegram(heartbeat)
            return 0

        message = build_message(hits, regime_label, date_str)
        print(f"[SCAN] {date_str} 命中 {len(hits)} 隻，發送 Telegram", flush=True)
        print(message, flush=True)
        send_telegram(message)
        return 0

    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        # 嘗試發失敗警告（若 Telegram 本身沒壞）
        try:
            send_telegram(f"🚨 港股狙擊手 掃描失敗\n📅 {date_str}\n❌ {type(e).__name__}: {e}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())

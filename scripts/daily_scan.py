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
from config import ACTIVE_PRESETS, MIN_BARS_FOR_INDICATORS, BEAR_LABELS_HARD


def detect_hsi_regime() -> dict:
    raw = get_stock_data("^HSI", "1y")
    if raw.empty:
        return {"label": "未知", "bucket": "🟡 震盪市", "ma_gap_pct": 0.0}
    df = calculate_indicators(raw)
    result = detect_regime(df)
    return result if result else {"label": "未知", "bucket": "🟡 震盪市", "ma_gap_pct": 0.0}


def scan_all(presets: dict | None = None) -> list[dict]:
    active = presets if presets is not None else ACTIVE_PRESETS
    preset_active = {
        name: [f"b{i+1}" for i, v in enumerate(p["buy"]) if v]
        for name, p in active.items()
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
            for name, active_sigs in preset_active.items():
                if not active_sigs:
                    continue
                if all(bool(sigs[b].iloc[-1]) for b in active_sigs):
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

    preset_order = {name: i for i, name in enumerate(active)}
    hits.sort(key=lambda h: (preset_order[h["presets"][0]], h["rsi"]))
    return hits


def build_message(hits: list[dict], regime_label: str, date_str: str,
                  ma_gap_pct: float = 0.0, prefix: str = "") -> str:
    sign = "+" if ma_gap_pct >= 0 else ""
    header_regime = f"🌍 恒指制度：{regime_label} | MA缺口 {sign}{ma_gap_pct:.1f}% | 今日掃描 {len(hits)} 隻"
    lines = []
    if prefix:
        lines.append(prefix)
    lines += [
        "🏹 港股狙擊手 每日掃描",
        f"📅 {date_str}",
        header_regime,
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
        regime = detect_hsi_regime()
        label = regime.get("label", "未知")
        bucket = regime.get("bucket", "🟡 震盪市")
        ma_gap_pct = regime.get("ma_gap_pct", 0.0)
        sign = "+" if ma_gap_pct >= 0 else ""

        # ── 熊市閘門：不執行任何掃描 ──
        if label in BEAR_LABELS_HARD:
            print(f"[GATE] 熊市制度（{label}），不執行掃描", flush=True)
            send_telegram(
                f"⛔ [制度閘門] 當前制度：{label}，全策略暫停，今日 0 個買入訊號"
            )
            return 0

        # ── 震盪市：只掃描「均值回歸」策略 ──
        if "震盪" in bucket:
            filtered = {k: v for k, v in ACTIVE_PRESETS.items() if "均值回歸" in k}
            hits = scan_all(presets=filtered)
            prefix = "⚠️ 震盪市：只推送保守策略"
        else:
            # 牛市：全策略正常掃描
            hits = scan_all()
            prefix = ""

        regime_header = f"🌍 恒指制度：{label} | MA缺口 {sign}{ma_gap_pct:.1f}% | 今日掃描 {len(hits)} 隻"

        if not hits:
            print(f"[SCAN] {date_str} 無命中，發送心跳", flush=True)
            heartbeat = (
                f"📡 港股狙擊手 每日掃描\n"
                f"📅 {date_str}\n"
                f"{regime_header}\n"
                f"\n"
                f"✅ 今日無買入訊號，持倉不變"
            )
            if prefix:
                heartbeat = prefix + "\n" + heartbeat
            send_telegram(heartbeat)
            return 0

        message = build_message(hits, label, date_str, ma_gap_pct=ma_gap_pct, prefix=prefix)
        print(f"[SCAN] {date_str} 命中 {len(hits)} 隻，發送 Telegram", flush=True)
        print(message, flush=True)
        send_telegram(message)
        return 0

    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        try:
            send_telegram(f"🚨 港股狙擊手 掃描失敗\n📅 {date_str}\n❌ {type(e).__name__}: {e}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
每日自動掃描 + Telegram 通知

港股收盤後（HKT 16:30 / UTC 08:30）由 Render cron job / GitHub Actions 觸發。
掃描 stocks.txt 全部股票，對「實盤策略」做 AND 邏輯買入訊號判斷。
有命中 → 發 Telegram；無命中 → 發心跳。
失敗 → 印 log 並 exit(1)。

V20 修正：
  1. 牛市策略洩漏：牛市改只掃 LIVE_PRESETS（💎 已驗證），不再洩漏 🔬 測試策略。
  2. 訊息增強：每筆顯示「股票名稱（TradingView，多為中文）」與「共振策略數」，
     並按共振數由多到少排序。名稱查詢失敗時 fallback 顯示代碼。
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import requests

from data import load_stocks, get_stock_data
from indicators import calculate_indicators, precompute_signals
from regime import detect_regime
from config import (
    ACTIVE_PRESETS, MIN_BARS_FOR_INDICATORS, BEAR_LABELS_HARD,
    REGIME_RECOMMENDATIONS, TV_URL, TV_HEADERS, LIGHT_POSITION_PRESETS,
)

# 實盤帳本（附加功能：失敗只印 log，不影響掃描 + Telegram 主流程）
import paper_ledger as pl


# ── 實盤策略白名單：只有 💎 已通過 PIT WF 的策略可推播 ──────────────
LIVE_PRESETS = {name: p for name, p in ACTIVE_PRESETS.items() if name.startswith("💎")}


# ── 股票名稱：用 TradingView screener 一次抓全部（多為中文名）──────
# 只在有命中、需要組訊息時才查一次；查不到 fallback 顯示代碼。
_TV_NAME_MAP: dict | None = None


def _load_tv_name_map() -> dict:
    """一次請求 TradingView，回 {ticker: 名稱}。失敗回空 dict（呼叫端 fallback）。"""
    global _TV_NAME_MAP
    if _TV_NAME_MAP is not None:
        return _TV_NAME_MAP

    name_map: dict = {}
    try:
        payload = {
            "filter": [{"left": "close", "operation": "greater", "right": 0}],
            "columns": ["name", "description"],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, 5000],
        }
        resp = requests.post(TV_URL, headers=TV_HEADERS, json=payload, timeout=20)
        resp.raise_for_status()
        for row in resp.json().get("data", []):
            d = row.get("d", [])
            if len(d) < 2:
                continue
            try:
                ticker = f"{int(d[0]):04d}.HK"
            except (ValueError, TypeError):
                continue
            desc = (d[1] or "").strip()
            if desc:
                name_map[ticker] = desc
        print(f"[NAME] TradingView 名稱表載入 {len(name_map)} 筆", flush=True)
    except Exception as e:
        print(f"[NAME] TradingView 名稱查詢失敗，將顯示代碼：{e}", flush=True)

    _TV_NAME_MAP = name_map
    return name_map


def get_stock_name(ticker: str) -> str:
    """回傳公司名稱；查不到回空字串（呼叫端 fallback 顯示代碼）。"""
    return _load_tv_name_map().get(ticker, "")


def detect_hsi_regime() -> dict:
    raw = get_stock_data("^HSI", "1y")
    if raw.empty:
        return {"label": "未知", "bucket": "🟡 震盪市", "ma_gap_pct": 0.0}
    df = calculate_indicators(raw)
    result = detect_regime(df)
    return result if result else {"label": "未知", "bucket": "🟡 震盪市", "ma_gap_pct": 0.0}


def scan_all(presets: dict | None = None, current_month: int | None = None) -> list[dict]:
    if current_month is None:
        from datetime import datetime, timezone, timedelta
        current_month = datetime.now(timezone(timedelta(hours=8))).month
    active = presets if presets is not None else LIVE_PRESETS
    preset_active = {
        name: [f"b{i+1}" for i, v in enumerate(p["buy"]) if v]
        for name, p in active.items()
    }

    hits: list[dict] = []
    tickers = load_stocks()
    print(f"[SCAN] 掃描 {len(tickers)} 隻股票，{len(preset_active)} 個策略", flush=True)

    for ticker in tickers:
        try:
            raw = get_stock_data(ticker, "6mo")
            if raw.empty or len(raw) < MIN_BARS_FOR_INDICATORS:
                continue
            df = calculate_indicators(raw)
            sigs = precompute_signals(df)

            matched = []
            for name, active_sigs in preset_active.items():
                if not active_sigs:
                    continue
                if active.get(name, {}).get("seasonal_filter") and current_month not in [1, 4, 10]:
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
                "n":       len(matched),   # 共振策略數
            })
        except Exception as e:
            print(f"[SCAN][{ticker}] {type(e).__name__}: {e}", flush=True)

    # 排序：共振數多 → 少；同共振數則 RSI 低（更超賣）在前
    hits.sort(key=lambda h: (-h["n"], h["rsi"]))
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
        name = get_stock_name(h["ticker"])
        name_part = f" {name}" if name else ""
        # 命中的輕倉策略加「⚠️輕倉」標記（提醒實盤勿重倉）
        presets_disp = [
            f"{p}⚠️輕倉" if p in LIGHT_POSITION_PRESETS else p
            for p in h["presets"]
        ]
        presets_str = ", ".join(presets_disp)
        n = h.get("n", len(h["presets"]))
        # 若全部命中策略都是輕倉，行尾再補一個總提示
        all_light = all(p in LIGHT_POSITION_PRESETS for p in h["presets"])
        tail = "｜⚠️ 僅輕倉策略命中" if all_light else ""
        lines.append(
            f"• {h['ticker']}{name_part}｜🎯共振 {n} 個"
            f"｜{presets_str}｜RSI={h['rsi']}｜現價 {h['price']}{tail}"
        )
    return "\n".join(lines)

def send_telegram(text: str) -> None:
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
    resp.raise_for_status()


# ── 帳本：價格 / 訊號注入函式 ────────────────────────────────────────────────
def _make_market_fns() -> tuple:
    """
    建立 price_fn / sig_fn 供 paper_ledger 用，兩者共用記憶化 snapshot，
    避免同一 ticker 在 pending_buy / open / pending_sell 處理時重複抓取。
    用 6mo 數據（確保 BB warmup 充足，與 scan_all 一致；get_stock_data 已有 diskcache）。
      price_fn(ticker) -> {"date": date, "open": float} 或 None
      sig_fn(ticker)   -> {"date": date, "s2": bool, "dates": [date,...]} 或 None
    """
    cache: dict = {}

    def _snapshot(ticker: str):
        if ticker in cache:
            return cache[ticker]
        snap = None
        try:
            raw = get_stock_data(ticker, "6mo")
            if not raw.empty and len(raw) >= MIN_BARS_FOR_INDICATORS:
                df = calculate_indicators(raw)
                sigs = precompute_signals(df)
                last = df.iloc[-1]
                snap = {
                    "date":  df.index[-1].date(),
                    "open":  float(last["Open"]),
                    "s2":    bool(sigs["s2"].iloc[-1]),
                    "dates": [d.date() for d in df.index],
                }
        except Exception as e:
            print(f"[LEDGER][{ticker}] snapshot 失敗：{type(e).__name__}: {e}", flush=True)
        cache[ticker] = snap
        return snap

    def price_fn(ticker: str):
        s = _snapshot(ticker)
        return {"date": s["date"], "open": s["open"]} if s else None

    def sig_fn(ticker: str):
        s = _snapshot(ticker)
        return {"date": s["date"], "s2": s["s2"], "dates": s["dates"]} if s else None

    return price_fn, sig_fn


def _run_ledger(hits: list, date_str: str) -> str:
    """
    更新實盤帳本並回傳 Telegram 摘要尾巴。整段 try/except 包住：
    env 缺失或任何失敗都只印 log 回 ""，絕不拖垮掃描 + Telegram 主流程。
    即使今日 0 hit（心跳 / 熊市閘門）也照跑 pending/open 處理
    （可能有昨天的 pending_buy 要成交、或持倉觸發 s2 要平倉）。
    """
    if not pl.is_enabled():
        print("[LEDGER] 未設定 GH_TOKEN / GH_REPO，跳過帳本更新", flush=True)
        return ""
    try:
        price_fn, sig_fn = _make_market_fns()
        trades, sha = pl.load_ledger()
        pl.process_pending_buys(trades, price_fn)         # 1. 昨日訊號 → 今日開盤成交
        pl.process_open_positions(trades, sig_fn, price_fn)  # 2. s2 出場（T+1）
        pl.record_new_signals(trades, hits, date_str)     # 3. 今日新訊號 → pending_buy
        pl.save_ledger(trades, sha, f"chore(ledger): update {date_str}")
        summary = pl.summarize(trades)
        return pl.format_ledger_summary(summary)
    except Exception as e:
        print(f"[LEDGER] 帳本更新失敗（不影響主流程）：{type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return ""


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
            gate_msg = f"⛔ [制度閘門] 當前制度：{label}，全策略暫停，今日 0 個買入訊號"
            # 熊市閘門只停「新買入訊號」，既有持倉仍要管理（成交 / s2 平倉）
            tail = _run_ledger([], date_str)
            if tail:
                gate_msg += "\n\n" + tail
            send_telegram(gate_msg)
            return 0

        FULL_SCAN_LABELS = {"強牛市", "弱牛市"}
        if label in FULL_SCAN_LABELS:
            # 牛市也只掃 💎 實盤策略（LIVE_PRESETS），不洩漏 🔬 測試策略
            hits = scan_all(presets=LIVE_PRESETS, current_month=hkt_now.month)
            prefix = ""
        else:
            rec_names = REGIME_RECOMMENDATIONS.get(label, [])
            if rec_names:
                filtered = {k: v for k, v in LIVE_PRESETS.items() if k in rec_names}
                hits = scan_all(presets=filtered, current_month=hkt_now.month)
                prefix = f"⚠️ {label}：只推送推薦策略（{len(filtered)} 個）"
            else:
                hits = []
                prefix = f"⚠️ {label}：無推薦策略"

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
            tail = _run_ledger([], date_str)
            if tail:
                heartbeat += "\n\n" + tail
            send_telegram(heartbeat)
            return 0

        message = build_message(hits, label, date_str, ma_gap_pct=ma_gap_pct, prefix=prefix)
        tail = _run_ledger(hits, date_str)
        if tail:
            message += "\n\n" + tail
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
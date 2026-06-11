"""
實盤 Paper-Trading 帳本（向前實盤模擬，對齊 Walk-Forward 口徑）

把 daily_scan 每日推播的買入訊號當作真實買入記錄下來，自動以 s2（布林上軌）+ MIN5 平倉，
累積算實盤 P&L。這是 WF 邏輯的真實向前延伸，數字要能跟 WF OOS 對照。

設計原則：
  - 本模組只負責「帳本邏輯 + GitHub 儲存」，不 import core/（保持解耦）。
  - 價格 / 訊號由呼叫端（daily_scan）以 closure 注入（price_fn / sig_fn）。
  - 帳本是附加功能：任何 GitHub IO 失敗都只印 log、不 raise，絕不拖垮主流程。

對齊鐵律（與 core/backtest.py、core/config.py 核實）：
  - 單邊成本 = SLIPPAGE_PCT(0.001) + COMMISSION_PCT(0.0026)/2 = 0.0023。
  - 買入：entry_px = 次日開盤 * (1 + 0.0023)；賣出：exit_px = 次日開盤 * (1 - 0.0023)。
  - 賣出統一用 s2（Close > BB_upper），進場後未滿 5 個「交易日（bar 數）」不允許策略 sell。
  - T+1 + 港股假期：用「該 ticker 最新一根 bar 的日期 > 觸發日期」判定是否成交，
    不用自然日；假期沒有 bar 就自然停在原地等下一個有 bar 的交易日。
  - 固定倉位、非複利；return_pct 為各筆百分比，彙總直接加總。
"""
import os
import json
import base64
from datetime import date, datetime

import requests

# ── 常數（與 WF / config.py 對齊）─────────────────────────────────────────────
ONE_SIDE_COST = 0.0023    # = SLIPPAGE_PCT(0.001) + COMMISSION_PCT(0.0026)/2
MIN_HOLD_DAYS = 5         # 進場後未滿 5 交易日不允許策略 sell（對齊 backtest min_hold_days）
TRADE_SIZE    = 100000    # 固定名目倉位（非複利，僅供記錄；P&L 以 return_pct 加總）
LEDGER_PATH   = "data/paper_trades.json"

GH_API = "https://api.github.com"


# ══════════════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════════════
def _to_date(s) -> date:
    """把儲存的 'YYYY-MM-DD' 字串轉成 date；已是 date 直接回傳。"""
    if isinstance(s, date):
        return s
    return datetime.strptime(s, "%Y-%m-%d").date()


def _new_trade(tid: str, ticker: str, strategy: str, resonance_n: int,
               signal_date: str, stop_loss_pct=None, max_hold_days=None) -> dict:
    """建立一筆 pending_buy 帳本紀錄（其餘欄位待成交 / 平倉時填）。"""
    return {
        "id": tid,                       # ticker|strategy|signal_date
        "ticker": ticker,
        "strategy": strategy,            # = ACTIVE_PRESETS 的 key
        "resonance_n": resonance_n,      # 進場當天該股共振策略數
        "status": "pending_buy",
        "signal_date": signal_date,      # 買訊偵測日（收盤後 cron）
        "entry_date": None,
        "entry_px": None,
        "sell_signal_date": None,        # 出場訊號觸發日（s2 / 止損 / 超時）
        "exit_date": None,
        "exit_px": None,
        "return_pct": None,
        "hold_bars": None,               # 平倉時填（days_held + 1）
        "exit_reason": None,
        "min_hold_days": MIN_HOLD_DAYS,
        # 風險出場（V22.2 Phase 4 補：對齊 backtest 的 stop_loss_pct / max_hold_days）
        # None = 不啟用（現有策略全部 None，行為不變）；由 daily_scan 從 preset 帶入。
        "stop_loss_pct": stop_loss_pct,  # 跌破 entry_px×(1-pct/100) 砍倉（百分數，如 10）
        "max_hold_days": max_hold_days,  # 抱滿 N 個 bar 砍倉
        "trade_size": TRADE_SIZE,
    }


# ══════════════════════════════════════════════════════════════════════════════
# GitHub Contents API 讀寫
# ══════════════════════════════════════════════════════════════════════════════
def _gh_env() -> tuple:
    """回 (GH_TOKEN, GH_REPO)，缺失為 None。"""
    return os.environ.get("GH_TOKEN"), os.environ.get("GH_REPO")


def is_enabled() -> bool:
    """兩個 env var 都齊備才啟用帳本。"""
    token, repo = _gh_env()
    return bool(token and repo)


def _gh_headers() -> dict:
    """回傳含 GH_TOKEN 的 GitHub API headers。"""
    token, _ = _gh_env()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _ledger_url() -> str:
    _, repo = _gh_env()
    return f"{GH_API}/repos/{repo}/contents/{LEDGER_PATH}"


def load_ledger() -> tuple:
    """
    GET data/paper_trades.json，回 (trades_list, sha)。
    檔案不存在（404）回 ([], None)；其他錯誤印 error 回 ([], None)。
    """
    try:
        resp = requests.get(_ledger_url(), headers=_gh_headers(), timeout=20)
        if resp.status_code == 404:
            print("[LEDGER] 帳本檔不存在，視為空帳本（首次執行會自動建立）", flush=True)
            return [], None
        resp.raise_for_status()
        data = resp.json()
        # GitHub 回傳的 base64 內含換行，b64decode 預設會忽略非字母字元
        raw = base64.b64decode(data.get("content", "")).decode("utf-8")
        trades = json.loads(raw) if raw.strip() else []
        return trades, data.get("sha")
    except Exception as e:
        print(f"[LEDGER] load_ledger 失敗：{type(e).__name__}: {e}", flush=True)
        return [], None


def save_ledger(trades: list, sha, message: str) -> bool:
    """
    PUT 回 GitHub：base64 編碼，帶 sha（更新）或無 sha（新建）。
    失敗印 error 回 False（不 raise）。
    """
    try:
        content = json.dumps(trades, ensure_ascii=False, indent=2)
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha
        resp = requests.put(_ledger_url(), headers=_gh_headers(), json=body, timeout=20)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[LEDGER] save_ledger 失敗：{type(e).__name__}: {e}", flush=True)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 去重輔助
# ══════════════════════════════════════════════════════════════════════════════
def get_open_keys(trades: list) -> set:
    """回所有 open + pending_buy 的 (ticker, strategy) 集合（同策略同股去重用）。"""
    return {
        (t["ticker"], t["strategy"])
        for t in trades
        if t["status"] in ("open", "pending_buy")
    }


# ══════════════════════════════════════════════════════════════════════════════
# 三階段處理（每次 cron 依序：buys → opens → new signals）
# price_fn(ticker) -> {"date": date, "open": float} 或 None
# sig_fn(ticker)   -> {"date": date, "s2": bool, "dates": [date,...]} 或 None
# ══════════════════════════════════════════════════════════════════════════════
def process_pending_buys(trades: list, price_fn) -> list:
    """
    對每筆 pending_buy：取該 ticker 最新一根 bar。
    只有最新 bar 日期「嚴格晚於」signal_date（= 次日開盤、且非假期）才成交，
    entry_px = open * (1 + ONE_SIDE_COST)；否則保持 pending_buy 等下次。
    """
    for t in trades:
        if t["status"] != "pending_buy":
            continue
        info = price_fn(t["ticker"])
        if not info:
            continue
        if info["date"] > _to_date(t["signal_date"]):
            t["entry_px"] = round(info["open"] * (1 + ONE_SIDE_COST), 4)
            t["entry_date"] = info["date"].isoformat()
            t["status"] = "open"
    return trades


def process_open_positions(trades: list, sig_fn, price_fn) -> list:
    """
    第一步：open → pending_sell（偵測出場訊號）。
      bars_held = 進場後到今日（含）實際有 bar 的交易日數（= backtest 的 days_held）。
      出場優先序（對齊 backtest）：止損 → 超時 → 策略 s2。
        • 止損 / 超時：風險出場，不受 min_hold 凍結（凍結期內照觸發）。
        • 策略 s2（Close > BB_upper）：滿 min_hold_days 才允許。
      命中即標記 pending_sell（T+1 才平），並把出場理由存進 pending_exit_reason。
      hold_bars = bars_held + 1（對齊 backtest 的 actual_days_held：T+1 多算一天）。

      ⚠️ 止損偵測用「當日最低價」（對齊 backtest 的 low ≤ ep×(1-stop/100)），
         但實際平倉仍在 T+1 開盤（非盤中止損價），故實現虧損會與回測略有出入；
         此為日線帳本架構限制下最接近的實作。時間出場（超時）無此問題、與回測一致。
    第二步：pending_sell → closed。
      最新 bar 日期嚴格晚於 sell_signal_date（次日開盤、非假期）才平倉，
      exit_px = open * (1 - ONE_SIDE_COST)，return_pct 含雙邊成本。
    """
    # ── 第一步：偵測出場訊號（止損 → 超時 → s2）──
    for t in trades:
        if t["status"] != "open":
            continue
        s = sig_fn(t["ticker"])
        if not s:
            continue
        entry_d = _to_date(t["entry_date"])
        today = s["date"]
        if today <= entry_d:                       # 進場當天不出場（T+1 起算）
            continue
        bars_held = sum(1 for d in s["dates"] if entry_d < d <= today)
        min_hold = t.get("min_hold_days", MIN_HOLD_DAYS)

        exit_reason = None

        # (1) 止損：跌破 entry_px×(1-stop/100)。不受 min_hold 凍結。
        stop = t.get("stop_loss_pct")
        if stop:
            p = price_fn(t["ticker"])
            entry_px = t.get("entry_px")
            low = p.get("low") if p else None       # 缺 low（舊 closure）→ 不觸發，安全
            if entry_px and low is not None and low <= entry_px * (1 - stop / 100.0):
                exit_reason = "止損"

        # (2) 超時：抱滿 max_hold_days 個 bar。不受 min_hold 凍結。
        max_hold = t.get("max_hold_days")
        if exit_reason is None and max_hold and bars_held >= max_hold:
            exit_reason = "超時"

        # (3) 策略 s2（布林上軌）：受 min_hold 凍結。
        if exit_reason is None and bars_held >= min_hold and s["s2"]:
            exit_reason = "策略訊號(s2)"

        if exit_reason is not None:
            t["status"] = "pending_sell"
            t["sell_signal_date"] = today.isoformat()
            t["hold_bars"] = bars_held + 1
            t["pending_exit_reason"] = exit_reason

    # ── 第二步：T+1 開盤平倉 ──
    for t in trades:
        if t["status"] != "pending_sell":
            continue
        info = price_fn(t["ticker"])
        if not info:
            continue
        if info["date"] > _to_date(t["sell_signal_date"]):
            exit_px = round(info["open"] * (1 - ONE_SIDE_COST), 4)
            entry_px = t["entry_px"]
            t["exit_px"] = exit_px
            t["exit_date"] = info["date"].isoformat()
            t["return_pct"] = round((exit_px - entry_px) / entry_px * 100, 4)
            t["exit_reason"] = t.get("pending_exit_reason", "策略訊號(s2)")
            t["status"] = "closed"
    return trades


def record_new_signals(trades: list, hits: list, signal_date: str,
                       strategy_params: dict = None) -> list:
    """
    把今日 scan_all 的命中（每筆含 presets list + n）登記為 pending_buy。
    去重規則：
      1. id（ticker|strategy|signal_date）已存在（任何狀態）→ 跳過（同訊號冪等，防同日重跑）。
      2. (ticker, strategy) 已有 open / pending_buy → 跳過（同策略同股不 pyramiding）。
    不同策略可同股並存。resonance_n = hit["n"]。

    strategy_params（可選）：{strategy_name: {"stop_loss_pct":..., "max_hold_days":...}}
      由 daily_scan 從 preset 帶入；缺省 / 缺 key → None（不啟用風險出場，行為不變）。
    """
    strategy_params = strategy_params or {}
    open_keys = get_open_keys(trades)
    existing_ids = {t["id"] for t in trades}
    for h in hits:
        ticker = h["ticker"]
        n = h.get("n", len(h.get("presets", [])))
        for strategy in h.get("presets", []):
            tid = f"{ticker}|{strategy}|{signal_date}"
            if tid in existing_ids:
                continue
            if (ticker, strategy) in open_keys:
                continue
            sp = strategy_params.get(strategy, {})
            trades.append(_new_trade(
                tid, ticker, strategy, n, signal_date,
                stop_loss_pct=sp.get("stop_loss_pct"),
                max_hold_days=sp.get("max_hold_days"),
            ))
            existing_ids.add(tid)
            open_keys.add((ticker, strategy))
    return trades


# ══════════════════════════════════════════════════════════════════════════════
# P&L 彙總
# ══════════════════════════════════════════════════════════════════════════════
def _group_stats(closed: list, key_fn) -> dict:
    """依 key_fn 分組，回 {key: {n, win_rate, avg_ret}}。"""
    groups: dict = {}
    for t in closed:
        groups.setdefault(key_fn(t), []).append(t)
    out: dict = {}
    for k, items in groups.items():
        rets = [t["return_pct"] for t in items if t.get("return_pct") is not None]
        n = len(rets)
        wins = sum(1 for r in rets if r > 0)
        out[k] = {
            "n": n,
            "win_rate": round(wins / n * 100, 1) if n else 0.0,
            "avg_ret": round(sum(rets) / n, 4) if n else 0.0,
        }
    return out


def summarize(trades: list) -> dict:
    """
    回帳本彙總（供 Telegram 摘要 + 日後「共振數 vs 勝率」分析）。
    所有比例 / 平均在空集合時安全回 0，不除以 0。
    """
    closed = [t for t in trades if t["status"] == "closed"]
    rets = [t["return_pct"] for t in closed if t.get("return_pct") is not None]
    holds = [t["hold_bars"] for t in closed if t.get("hold_bars") is not None]
    n_ret = len(rets)
    wins = sum(1 for r in rets if r > 0)
    return {
        "closed_n": len(closed),
        "open_n": sum(1 for t in trades if t["status"] == "open"),
        "pending_n": sum(1 for t in trades
                         if t["status"] in ("pending_buy", "pending_sell")),
        "total_return_pct": round(sum(rets), 4) if rets else 0.0,
        "avg_return_pct": round(sum(rets) / n_ret, 4) if n_ret else 0.0,
        "win_rate": round(wins / n_ret * 100, 1) if n_ret else 0.0,
        "avg_hold_days": round(sum(holds) / len(holds), 1) if holds else 0.0,
        "by_resonance": _group_stats(closed, lambda t: t.get("resonance_n")),
        "by_strategy": _group_stats(closed, lambda t: t.get("strategy")),
    }


def _format_resonance_line(by_resonance: dict) -> str:
    """
    把 by_resonance（{resonance_n: {n, win_rate, avg_ret}}）壓成共振 1 / 2 / 3+ 三桶，
    回一行繁中摘要；無已平倉資料回空字串（呼叫端判斷是否附加）。
    這正是當初記 resonance_n 的目的：檢驗「共振越多勝率越高？」。
    """
    if not by_resonance:
        return ""
    buckets: dict = {"1": [], "2": [], "3+": []}
    for k, v in by_resonance.items():
        if k is None:
            continue
        key = "1" if k == 1 else ("2" if k == 2 else "3+")
        buckets[key].append(v)

    parts = []
    for key in ("1", "2", "3+"):
        items = buckets[key]
        tot_n = sum(i["n"] for i in items)
        if tot_n == 0:
            continue
        # 加權平均勝率 / 平均回報（各 resonance_n 的樣本數加權）
        wr  = sum(i["win_rate"] * i["n"] for i in items) / tot_n
        ret = sum(i["avg_ret"] * i["n"]  for i in items) / tot_n
        sign = "+" if ret >= 0 else ""
        parts.append(f"共振{key}：勝率{wr:.0f}% 均{sign}{ret:.2f}%（{tot_n}筆）")
    if not parts:
        return ""
    return "🎯 共振分析｜" + " ｜ ".join(parts)


def format_ledger_summary(summary: dict) -> str:
    """
    組一段簡短繁中文字給 Telegram 尾巴。

    V22.2（2026-06-02 AUDIT-G 🟡-1）：除了原本 5 個欄位，補上每天都算但從不外露的
    avg_return_pct、avg_hold_days，以及 by_resonance（共振數→勝率，記 resonance_n 的本意）。
    """
    total = summary["total_return_pct"]
    sign = "+" if total >= 0 else ""
    avg_ret = summary.get("avg_return_pct", 0.0)
    avg_sign = "+" if avg_ret >= 0 else ""

    lines = [
        f"📒 帳本：已平倉 {summary['closed_n']} 筆 ｜ "
        f"總 {sign}{total}% ｜ 勝率 {summary['win_rate']}% ｜ "
        f"持倉中 {summary['open_n']} 筆 ｜ 待成交 {summary['pending_n']} 筆",
        f"　　平均每筆 {avg_sign}{avg_ret}% ｜ 平均持倉 {summary.get('avg_hold_days', 0.0)} 天",
    ]

    res_line = _format_resonance_line(summary.get("by_resonance", {}))
    if res_line:
        lines.append(res_line)

    return "\n".join(lines)
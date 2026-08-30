"""
每日自動掃描 + Telegram 通知

港股收盤後（HKT 16:30 / UTC 08:30）由 GitHub Actions 觸發。
掃描 stocks.txt 全部股票，對「實盤策略」做 AND 邏輯買入訊號判斷。
有命中 → 發 Telegram；無命中 → 發心跳。
失敗 → 印 log 並 exit(1)。

V20 修正：
  1. 牛市策略洩漏：牛市改只掃 LIVE_PRESETS（💎 已驗證），不再洩漏 🔬 測試策略。
  2. 訊息增強：每筆顯示「股票名稱（TradingView，多為中文）」與「共振策略數」，
     並按共振數由多到少排序。名稱查詢失敗時 fallback 顯示代碼。

V22.3 修正（2026-06-12，b19 熊市豁免）：
  熊市閘門由「完全停止」改為 per-strategy 豁免：
    • 強/弱熊市（BEAR_LABELS_HARD）下，一般 LIVE 策略仍全停（實盤禁區）；
    • 但對 LIVE_PRESETS ∩ BEAR_EXEMPT_PRESETS（目前僅 b19）續掃並推播，帶熊市風險標註。
  原因：b19 alpha 核心在恐慌環境（強熊市混合 +8.54% 最肥）；硬熊一律封鎖則線上拿不到
  回測水位（+2.49% → +1.48%）。豁免 ≠ 無風險 → b19 同列 LIGHT_POSITION，推播帶輕倉標。
  既有持倉管理（成交 / s2 / 止損 / 超時平倉）原本就在熊市照跑，本次不變。

V22.5 修正（2026-07-23，出場明細上推播）：
  出場鏈路本來每天都跑，但推播只外露帳本彙總數字（已平倉 N 筆 / 勝率 / 均值），
  「賣了哪一隻、什麼原因、賺賠多少」看不到，只能開 GitHub 讀 paper_trades.json。
  改為在買入訊號之後附出場明細兩塊（與買入側 T+1 同構）：
    🔴 賣出訊號（今日觸發，明早開盤平倉）  ✅ 今日已平倉（已實現報酬）
  資料源只有帳本既有持倉 → 只報「買過的」，不掃全池 s2；掃描 / 出場 / 閘門邏輯零變動。
"""
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import requests

from data import load_stocks, get_stock_data
from indicators import calculate_indicators, precompute_signals
from regime import detect_regime
from config import (
    ACTIVE_PRESETS, MIN_BARS_FOR_INDICATORS, BEAR_LABELS_HARD,
    REGIME_RECOMMENDATIONS, TV_URL, TV_HEADERS, LIGHT_POSITION_PRESETS,
    LIVE_PRESET_KEYS, BEAR_EXEMPT_PRESETS,
)

# 實盤帳本（附加功能：失敗只印 log，不影響掃描 + Telegram 主流程）
import paper_ledger as pl


# ── 實盤策略白名單：只推播 key 在 LIVE_PRESET_KEYS 內的策略 ──────────
# V22.2 Phase 4（路線 A）：改用 config 的 LIVE_PRESET_KEYS（取代舊「💎 前綴」判定）。
# V22.3：白名單含 b19（紙上向前驗證）。要復活/下架某策略：編輯 config.LIVE_PRESET_KEYS。
LIVE_PRESETS = {name: p for name, p in ACTIVE_PRESETS.items() if name in LIVE_PRESET_KEYS}

# ── 熊市豁免子集：硬熊制度下仍可掃描/推播的 LIVE 策略 ────────────────
# = LIVE_PRESETS ∩ BEAR_EXEMPT_PRESETS（目前 b19 + b13+b17）。空集則硬熊維持完全停止（舊行為）。
BEAR_EXEMPT_LIVE = {name: p for name, p in LIVE_PRESETS.items() if name in BEAR_EXEMPT_PRESETS}


# ── 制度建議定倉乘數（V22.3 制度條件式定倉，2026-06-15, test_regime_sizing）────────
# 來源：LIVE 四支合併 blended cohort 按【進場日制度】分桶的 ¼-Kelly，經風險折扣（見下）。
# 性質：純推播「相對定倉建議」標註（如同 ⚠️輕倉）；不改任何掃描 / 出場 / 閘門邏輯。
#   基準 1.0× = 現行齊頭；總風險預算不變的「重分配」。絕對倉位上限另由 MC 破產率/maxDD 管（解耦）。
#   實測：制度加權 vs 齊頭 +4.18%→+5.76%、lift +1.58pp、leave-one-regime-out 全過。
# 折扣理由（★勿照原始 Kelly 全收★）：
#   • 強熊市原始 1.75× = 海市蜃樓：進場時平均並行 ~196 倉 = 高度相關的單一巨型 bet，
#     per-trade std 低估尾險 + episode 集中（N_eff~5）→ 封頂 1.0×、務必輕倉，不加碼。
#   • 弱牛市原始 2.40×：n=37 過擬合、LOO 證非支柱 → 壓回 1.0×。
#   • 真獎品 = 牛市警惕（broad n=488 / Sharpe 0.36 / 低並行 75）→ 1.5×，最可信加碼對象。
#   • 震盪市 = 0：已由下方震盪市閘停進場（此處不會走到），列 0 僅為自洽。
# PIT 乾淨：吃 main() 既有 gating 的『前一收盤制度』label，無前視、不另算。
REGIME_SIZE_MULT: dict = {
    "牛市警惕": 1.5,   # ✅ 乾淨的肥：broad / 高 Sharpe / 低並行，最可信加碼
    "弱牛市":   1.0,   # n=37 過擬合，壓中性
    "強牛市":   1.0,   # n=17 樣本薄，中性
    "熊市觀察": 0.6,   # 軟熊、中庸
    "強熊市":   1.0,   # ⚠ episode 集中 + 並行 ~196，封頂·輕倉，不照 Kelly 加
    "弱熊市":   0.4,   # 偏淡
    "轉折期":   0.5,   # 淡但正，小注、不閘
    "震盪市":   0.0,   # 已閘（不會走到推播）
}


def regime_size_note(label: str) -> str:
    """回傳該制度的建議定倉標註字串；未知 / 已閘制度回 ""（不顯示，安全預設）。"""
    m = REGIME_SIZE_MULT.get(label)
    if not m:                       # None（未知制度）或 0（已閘）→ 不標
        return ""
    if label in BEAR_LABELS_HARD:
        return f"📊 制度建議定倉：{m:g}×（熊市封頂·務必輕倉；相對基準，絕對上限另管）"
    return f"📊 制度建議定倉：{m:g}×（相對基準 1.0×；絕對上限另由倉位管理管）"


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


# ── 實驗天數計數（Day XX，交易日版，V22.5, 2026-07-28）────────────────────────
# 起始日 = 2026-05-10（Day 1 = 起始日「當日或之後」的第一個交易日）。
# ★用「^HSI 的 bar 數」數交易日★：恒指只在港股交易日有 K 棒，故「日期 ≥ 起始日的
#   bar 數」= 真實交易日序號 → 自動處理週末 / 港假，無需維護假期表、無狀態、不怕漏跑。
# _DAY_N 由 detect_hsi_regime()（每天第一個動作、早於任何 send_telegram）算好填入；
#   send_telegram 讀取。HSI 取不到 → None → 該則不前置 Day（寧缺勿顯示錯號）。
EXPERIMENT_START = date(2026, 5, 10)
_DAY_N: int | None = None


def _compute_trading_day_n(df) -> int | None:
    """數 ^HSI bar 中日期 ≥ EXPERIMENT_START 的根數 = 交易日序號。取不到 / 出錯回 None。"""
    try:
        return sum(1 for d in df.index if d.date() >= EXPERIMENT_START)
    except Exception:
        return None


def _day_header() -> str:
    """回「Day N」；交易日序號未算出（HSI 不可用）→ 回 ""（send_telegram 不前置）。"""
    return f"Day {_DAY_N}" if _DAY_N is not None else ""


# ── 日期攤平（專案通則）────────────────────────────────────────────────────────
# 陷阱：pandas.Timestamp 與 datetime.datetime 都是 datetime.date 的「子類」，
# isinstance(Timestamp, date) 回 True → 不先攔子類就會把帶時間的物件當純 date 用，
# 之後與純 date 比較會 TypeError。故一律先攔子類再處理。
def _as_date(x) -> date | None:
    """把 Timestamp / datetime / date / 'YYYY-MM-DD' 攤成純 datetime.date；失敗回 None。"""
    if x is None:
        return None
    try:
        if hasattr(x, "to_pydatetime"):        # pandas.Timestamp
            return x.to_pydatetime().date()
        if isinstance(x, datetime):            # datetime（是 date 子類，須先攔）
            return x.date()
        if isinstance(x, date):
            return x
        return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ── 同 bar 去重（備援排程用）──────────────────────────────────────────────────
# 背景：GitHub Actions schedule 高負載時會延遲數小時、甚至整批丟棄（本 repo 2026-08-27/28
#   實測漂移 10h42m / 11h48m）。對策＝一天排多個 cron 拉高「至少跑成一次」的機率；
#   代價＝可能一天跑多次 → 用「資料錨日」做冪等 key，同一根 bar 只推播一次。
# 只有「成功推播」才寫狀態（send_telegram 內單一插入點，覆蓋全部推播路徑）；
#   失敗訊息不寫 → 備援跑批仍會重試。
_SCAN_STATE: dict = {"anchor": None, "sha": None, "armed": False, "done": False}


def _force_scan() -> bool:
    """workflow_dispatch 手動觸發時可帶 FORCE_SCAN=true 忽略去重（重跑同一根 bar）。"""
    return os.environ.get("FORCE_SCAN", "").strip().lower() in ("1", "true", "yes")


def _guard_already_pushed(date_str: str) -> bool:
    """
    True = 這根 bar 今天已經有跑批成功推播過 → 本次是備援排程，應靜默跳過。
    去重不可用（無 GH_TOKEN / API 失敗）→ 回 False（寧可重複推，也不要漏推）。
    """
    if not pl.is_enabled():
        print("[GUARD] 未設定 GH_TOKEN / GH_REPO → 同 bar 去重關閉（備援排程可能重複推播）", flush=True)
        return False
    state, sha = pl.load_state()
    _SCAN_STATE.update(anchor=date_str, sha=sha, armed=True, done=False)
    if _force_scan():
        print(f"[GUARD] FORCE_SCAN=1 → 忽略去重，強制重跑錨日 {date_str}", flush=True)
        return False
    if state.get("last_anchor") == date_str:
        print(
            f"[GUARD] 錨日 {date_str} 已於 {state.get('pushed_at_hkt', '?')} "
            f"由 run {state.get('run_id', '?')} 完成推播 → 本次備援排程靜默跳過",
            flush=True,
        )
        return True
    return False


def _mark_scan_done() -> None:
    """推播成功後寫狀態檔（同 bar 的後續備援跑批據此跳過）。失敗只印 log。"""
    if not _SCAN_STATE["armed"] or _SCAN_STATE["done"] or not _SCAN_STATE["anchor"]:
        return
    now = datetime.now(timezone(timedelta(hours=8)))
    state = {
        "last_anchor": _SCAN_STATE["anchor"],          # 資料錨日 = ^HSI 最新 bar
        "pushed_at_hkt": now.strftime("%Y-%m-%d %H:%M"),  # 實際推播時刻（HKT，看漂移用）
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
    }
    if pl.save_state(state, _SCAN_STATE["sha"], f"chore(scan): mark {_SCAN_STATE['anchor']}"):
        _SCAN_STATE["done"] = True
        print(f"[GUARD] 已標記錨日 {_SCAN_STATE['anchor']} 完成（{state['pushed_at_hkt']} HKT）", flush=True)


def detect_hsi_regime() -> dict:
    raw = get_stock_data("^HSI", "1y")
    if raw.empty:
        return {"label": "未知", "bucket": "🟡 震盪市", "ma_gap_pct": 0.0, "anchor_date": None}
    df = calculate_indicators(raw)
    # 交易日序號：^HSI bar 數 ≥ 起始日（自帶港假處理）；填入模組級 _DAY_N 供 send_telegram 前置。
    global _DAY_N
    _DAY_N = _compute_trading_day_n(df)
    result = detect_regime(df)
    out = dict(result) if result else {"label": "未知", "bucket": "🟡 震盪市", "ma_gap_pct": 0.0}
    # ★資料錨日★：^HSI 最新一根 bar 的日期 = 本批訊號真正來自哪一個交易日。
    # 全流程（帳本 signal_date / 季節性濾網 / 推播日期）一律用它，不用 wall clock。
    out["anchor_date"] = _as_date(df.index[-1])
    return out


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
    size_note = regime_size_note(regime_label)
    lines = []
    if prefix:
        lines.append(prefix)
    lines += [
        "🏹 港股狙擊手 每日掃描",
        f"📅 {date_str}",
        header_regime,
    ]
    if size_note:
        lines.append(size_note)
    lines += [
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

def send_telegram(text: str, mark_done: bool = True) -> None:
    """
    推播 Telegram。mark_done=True（正常路徑）在推播成功後寫「同 bar 已完成」狀態，
    這是單一插入點、覆蓋全部推播路徑（命中/心跳/熊市閘/震盪市閘）——與 Day 計數同構。
    ★失敗訊息必須傳 mark_done=False★：沒跑成就不能擋掉備援排程的重試。
    """
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Day 計數置頂：單一插入點覆蓋所有推播路徑（命中/心跳/熊市閘/震盪市閘/失敗訊息），
    # 免在各訊息字串重複加、也不會漏（module-G 覆蓋一致性）。HSI 不可用 → header="" → 不前置。
    header = _day_header()
    body = f"{header}\n{text}" if header else text
    resp = requests.post(url, json={"chat_id": chat_id, "text": body}, timeout=20)
    resp.raise_for_status()
    if mark_done:
        _mark_scan_done()


# ── 帳本：價格 / 訊號注入函式 ────────────────────────────────────────────────
def _make_market_fns() -> tuple:
    """
    建立 price_fn / sig_fn 供 paper_ledger 用，兩者共用記憶化 snapshot，
    避免同一 ticker 在 pending_buy / open / pending_sell 處理時重複抓取。
    用 6mo 數據（確保 BB warmup 充足，與 scan_all 一致；get_stock_data 已有 diskcache）。
      price_fn(ticker) -> {"date": date, "open": float, "close": float, "low": float} 或 None
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
                    "close": float(last["Close"]),
                    "low":   float(last["Low"]),   # 供帳本止損偵測（low ≤ entry×(1-stop/100)）
                    "s2":    bool(sigs["s2"].iloc[-1]),
                    "dates": [d.date() for d in df.index],
                }
        except Exception as e:
            print(f"[LEDGER][{ticker}] snapshot 失敗：{type(e).__name__}: {e}", flush=True)
        cache[ticker] = snap
        return snap

    def price_fn(ticker: str):
        s = _snapshot(ticker)
        return {"date": s["date"], "open": s["open"],
                "close": s["close"], "low": s["low"]} if s else None

    def sig_fn(ticker: str):
        s = _snapshot(ticker)
        return {"date": s["date"], "s2": s["s2"], "dates": s["dates"]} if s else None

    return price_fn, sig_fn


def _run_ledger(hits: list, date_str: str, size_mult: float = 1.0) -> str:
    """
    更新實盤帳本並回傳 Telegram 尾巴（出場明細 + 帳本摘要）。整段 try/except 包住：
    env 缺失或任何失敗都只印 log 回 ""，絕不拖垮掃描 + Telegram 主流程。
    即使今日 0 hit（心跳 / 熊市閘門 / 震盪市閘門）也照跑 pending/open 處理
    （可能有昨天的 pending_buy 要成交、或持倉觸發 s2 要平倉）
    → 故出場明細在「所有推播路徑」都會出現，不只有命中日（模組 G 覆蓋一致性）。

    strategy_params 從「全 LIVE（含熊市豁免）」帶風險出場參數：
      帳本可能持有任一 LIVE 策略的舊倉（含 b19），平倉判定需要其 stop/max_hold，
      故用 LIVE_PRESETS 全集而非當日掃描子集，避免漏帶 b19 的 max_hold_days=20。
    """
    if not pl.is_enabled():
        print("[LEDGER] 未設定 GH_TOKEN / GH_REPO，跳過帳本更新", flush=True)
        return ""
    try:
        price_fn, sig_fn = _make_market_fns()
        # 從 preset 帶入風險出場參數（stop_loss_pct / max_hold_days）；
        # preset 沒設 → None → 帳本不啟用該出場（行為與現況一致）。
        strategy_params = {
            name: {
                "stop_loss_pct": p.get("stop_loss_pct"),
                "max_hold_days": p.get("max_hold_days"),
            }
            for name, p in LIVE_PRESETS.items()
        }
        trades, sha = pl.load_ledger()
        prev_status = pl.snapshot_status(trades)             # 0. 處理前狀態快照（供出場事件比對）
        pl.process_pending_buys(trades, price_fn)            # 1. 昨日訊號 → 今日開盤成交
        pl.process_open_positions(trades, sig_fn, price_fn)  # 2. 出場（止損→超時→s2，T+1）
        pl.record_new_signals(trades, hits, date_str, strategy_params, size_mult=size_mult)  # 3. 今日新訊號（按制度乘數縮放記倉）
        saved = pl.save_ledger(trades, sha, f"chore(ledger): update {date_str}")
        # 4. 出場事件明細（V22.5）：本次新觸發出場（明早平倉）＋ 本次完成平倉（今日已賣）。
        #    只來自帳本既有持倉 = 天然「只報買過的」，不掃全池 s2。
        #    放在帳本摘要之前 → 訊息序：買入訊號 → 賣出訊號 → 帳本摘要。
        exit_block = pl.format_exit_block(
            pl.collect_exit_events(trades, prev_status),
            name_fn=get_stock_name, price_fn=price_fn,
        )
        summary = pl.summarize(trades)
        # ★寫入失敗必須外顯★（模組 G：落地那一步斷掉不能只留 log）
        # 下方的出場明細/摘要都是「記憶體裡的 trades」算出來的，save_ledger 失敗時它們
        # 看起來一切正常，但 data/paper_trades.json 根本沒更新 → 當日進出場全蒸發、
        # 隔日跑批讀到舊帳本狀態錯開。最典型觸發＝GH_TOKEN PAT 過期（60 天一輪）。
        warn = ("⚠️ 帳本寫入失敗（GH_TOKEN 可能過期）\n"
                "本次進出場未保存，下方數字僅為當下試算") if not saved else ""
        parts = [p for p in (warn, exit_block, pl.format_ledger_summary(summary)) if p]
        return "\n\n".join(parts)
    except Exception as e:
        print(f"[LEDGER] 帳本更新失敗（不影響主流程）：{type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        # 原本回 ""＝帳本尾巴整段消失，0 命中的心跳日幾乎看不出來。改為外顯一行；
        # 只帶例外「類型」不帶訊息（訊息可能含 URL/參數），細節留在 Actions log。
        return (f"⚠️ 帳本更新失敗：{type(e).__name__}\n"
                f"本次進出場未保存，請檢查 Actions log")


def main() -> int:
    hkt_now = datetime.now(timezone(timedelta(hours=8)))
    date_str = hkt_now.strftime("%Y-%m-%d")   # 僅為 fallback；取到錨日後立刻覆寫

    try:
        regime = detect_hsi_regime()
        label = regime.get("label", "未知")
        bucket = regime.get("bucket", "🟡 震盪市")
        ma_gap_pct = regime.get("ma_gap_pct", 0.0)

        # ── ★日期錨定資料，不用 wall clock★ ────────────────────────────────
        # 原本 date_str = datetime.now()。GitHub Actions 排程漂移跨過午夜時（實測 10–12h），
        # 訊號明明來自前一交易日收盤，卻被記成隔天甚至週六 → 帳本 signal_date 偏一天
        # （process_pending_buys 要求 bar 日期「嚴格晚於」signal_date，成交會被推遲一個交易日）、
        # 月底漂移還會翻轉 seasonal_filter 的月份判斷。改用 ^HSI 最新 bar 日期後，
        # runner 幾點醒都不影響結果——同一根 bar 永遠得到同一個 date_str。
        anchor = _as_date(regime.get("anchor_date"))
        if anchor is None:
            print(f"[ANCHOR] ⚠️ 取不到 ^HSI 錨日，退回 wall clock {date_str}（結果可能受排程漂移影響）", flush=True)
        else:
            date_str = anchor.isoformat()
            lag_h = (hkt_now - datetime.combine(anchor, datetime.min.time(),
                                                tzinfo=timezone(timedelta(hours=8)))).total_seconds() / 3600
            print(f"[ANCHOR] 資料錨日 {date_str}｜執行時刻 {hkt_now:%Y-%m-%d %H:%M} HKT"
                  f"（距錨日 00:00 約 {lag_h:.1f} 小時）", flush=True)
            if lag_h > 96:
                print(f"[ANCHOR] ⚠️ 錨日距今超過 4 天，^HSI 資料可能過期，請檢查 yfinance", flush=True)

        # ── 同 bar 去重：備援排程若發現這根 bar 已推播過就靜默結束 ──────────
        if _guard_already_pushed(date_str):
            return 0

        scan_month = anchor.month if anchor else hkt_now.month
        sign = "+" if ma_gap_pct >= 0 else ""
        # 制度建議定倉乘數（PIT：用前收制度 label）；帶入帳本記倉，使紙上帳本前向驗證 lift。
        size_mult = REGIME_SIZE_MULT.get(label, 1.0)

        # ── 熊市閘門：一般策略停，但 BEAR_EXEMPT_LIVE 豁免續掃（V22.3）──
        if label in BEAR_LABELS_HARD:
            if BEAR_EXEMPT_LIVE:
                # 只掃熊市豁免策略（目前 b19）；推薦清單過濾後再掃，帶熊市風險標註。
                rec_names = REGIME_RECOMMENDATIONS.get(label, [])
                exempt_filtered = {
                    k: v for k, v in BEAR_EXEMPT_LIVE.items()
                    if (not rec_names) or (k in rec_names)
                } or BEAR_EXEMPT_LIVE   # 若該制度沒列推薦，退回掃全部豁免策略
                print(f"[GATE] 熊市制度（{label}），一般策略停；豁免掃描 {len(exempt_filtered)} 支", flush=True)
                hits = scan_all(presets=exempt_filtered, current_month=scan_month)
                prefix = (
                    f"⛔ [制度閘門] 當前制度：{label}（實盤禁區）。"
                    f"一般策略全停；僅熊市豁免策略（{len(exempt_filtered)} 支）續掃，"
                    f"⚠️ 熊市接深跌反彈風險高，務必輕倉。"
                )
                if hits:
                    message = build_message(hits, label, date_str,
                                            ma_gap_pct=ma_gap_pct, prefix=prefix)
                else:
                    message = (
                        f"{prefix}\n"
                        f"🏹 港股狙擊手 每日掃描\n📅 {date_str}\n"
                        f"🌍 恒指制度：{label} | MA缺口 {sign}{ma_gap_pct:.1f}%\n\n"
                        f"✅ 熊市豁免策略今日無買入訊號，持倉不變"
                    )
                tail = _run_ledger(hits, date_str, size_mult=size_mult)
                if tail:
                    message += "\n\n" + tail
                print(f"[SCAN] {date_str} 熊市豁免命中 {len(hits)} 隻", flush=True)
                send_telegram(message)
                return 0
            else:
                # 無豁免策略 → 維持舊行為：完全停止掃描，僅管理既有持倉
                print(f"[GATE] 熊市制度（{label}），無豁免策略，不執行掃描", flush=True)
                gate_msg = f"⛔ [制度閘門] 當前制度：{label}，全策略暫停，今日 0 個買入訊號"
                tail = _run_ledger([], date_str, size_mult=size_mult)
                if tail:
                    gate_msg += "\n\n" + tail
                send_telegram(gate_msg)
                return 0

        # ── 震盪市閘門（V22.3 制度曝險疊加，2026-06-15）─────────────────
        # 證據：LIVE 四支在「震盪市」label（高 CoV 橫盤）的 blended cohort 全為負
        #   （b19 −2.80% / b17+b6 −3.59% / b15+b17 −2.44% / b13+b17 −3.61%，
        #    合併 −3.06%、674 筆 broad-sample，非單一事件）。
        #   只停【震盪市 label】→ 整本帳 blended +2.74%→+4.06%（lift +1.32pp、
        #   砍 19% 全是虧損單）。四支通用，無豁免（與熊市閘的 b19 豁免不同）。
        # 只停高 CoV「震盪市」；低 CoV「轉折期」cohort 淨正(+1.78%)→不在此閘、照常走下方流程。
        # 與熊市閘相同：暫停的只是「進場推播」，既有持倉 s2/止損/超時出場照跑（_run_ledger）。
        if label == "震盪市":
            print(f"[GATE] 震盪市制度（高 CoV 橫盤），LIVE 全停進場（疊加閘）；持倉管理照跑", flush=True)
            gate_msg = (
                f"🟡 [震盪市閘門] 制度：震盪市（高波動橫盤）\n"
                f"🏹 港股狙擊手 每日掃描\n📅 {date_str}\n"
                f"🌍 恒指制度：{label} | MA缺口 {sign}{ma_gap_pct:.1f}%\n\n"
                f"⛔ 此制度下 LIVE 策略歷史 cohort 為負（−3.06%），暫停進場推播；"
                f"既有持倉照常管理（出場不受影響）。"
            )
            tail = _run_ledger([], date_str, size_mult=size_mult)
            if tail:
                gate_msg += "\n\n" + tail
            send_telegram(gate_msg)
            return 0

        FULL_SCAN_LABELS = {"強牛市", "弱牛市"}
        if label in FULL_SCAN_LABELS:
            # 牛市也只掃 💎 實盤策略（LIVE_PRESETS），不洩漏 🔬 測試策略
            hits = scan_all(presets=LIVE_PRESETS, current_month=scan_month)
            prefix = ""
        else:
            rec_names = REGIME_RECOMMENDATIONS.get(label, [])
            if rec_names:
                filtered = {k: v for k, v in LIVE_PRESETS.items() if k in rec_names}
                hits = scan_all(presets=filtered, current_month=scan_month)
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
            tail = _run_ledger([], date_str, size_mult=size_mult)
            if tail:
                heartbeat += "\n\n" + tail
            send_telegram(heartbeat)
            return 0

        message = build_message(hits, label, date_str, ma_gap_pct=ma_gap_pct, prefix=prefix)
        tail = _run_ledger(hits, date_str, size_mult=size_mult)
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
            send_telegram(f"🚨 港股狙擊手 掃描失敗\n📅 {date_str}\n❌ {type(e).__name__}: {e}",
                          mark_done=False)   # 失敗不標記 → 備援排程仍會重試
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
"""
test_b17_regime_intensity.py -- b17 救援最終輪：制度閘門 × ROC 強度（Phase 5b）

═══════════════════════════════════════════════════════════════════
背景（接 test_b17_exit_grid.py 結果，2026-06-12）
═══════════════════════════════════════════════════════════════════
  出場格點 7 格全敗，且證明三條新鐵則：
    A. b17 右尾驅動：止盈截右尾必死（TP12 勝率 52.2% 卻混合 -0.04%）。
    B. b17 左尾也會回歸：15%/20% 災難止損照樣把 in-window 砍到 +0.2~0.4
       → 任何價格型截尾出場（止損/止盈，無論多寬）對 b17 都有害。
    C. 時間窗梯度 T10→T15→T20 = +0.33→+0.89→+0.97 急速收斂
       → 出場槓桿開採完畢，T20+s2 即高原頂，出場面天花板 ≈ +1.0%。

  → 缺口 1pp 只能從「交易選擇」（整筆移除負 EV 情境）找，不能從出場改造找。

═══════════════════════════════════════════════════════════════════
本輪假設（預先宣告，機制先行）
═══════════════════════════════════════════════════════════════════
  G1 排除硬熊（強熊市/弱熊市）：崩跌延續期接刀失敗率高；且硬熊本就是
     系統實盤禁區（BEAR_LABELS_HARD），閘門有先驗正當性、非事後撈取。
  G2 僅均值回歸制度（震盪市/轉折期/熊市觀察/牛市警惕）：高波動橫盤是
     均值回歸主場；強/弱牛市裡跌穿 MA20 又 5 日急跌的票多為個股出事，彈不動。
  ROC 強度（-8 基準 / -10 / -12）：同一訊號的深度過濾（非 AND 疊新指標，
     不違反鐵則 4/5）。更深超跌=更強回歸力 vs 撈到更多真刀，方向未知，各一格驗證。

  出場固定為已證高原頂：T20 + s2 + MIN5，無止損、無止盈。

═══════════════════════════════════════════════════════════════════
裁決標準（與上輪相同，跑完不准搬門檻）
═══════════════════════════════════════════════════════════════════
  1. 混合真實回報 ≥ +2.0%（in-window ∪ 已平倉延伸單，逐筆等權）
  2. 有效 Fold 正回報比率 ≥ 60%
  3. 參數高原：過關格的相鄰格（同閘門的鄰近 ROC、同 ROC 的鄰近閘門）同向
  4. 混合樣本 ≥ 500 筆（閘門+深度雙重過濾後謹防樣本薄虛高）

  ⚠️ 這是 b17 的最後一輪：9 格全敗 → 結案，接受「alpha 上限 +1.4%、
     扣成本剩 +1.0%、不足實盤」，b17 留 ACTIVE 作分析用途。

═══════════════════════════════════════════════════════════════════
實作備註
═══════════════════════════════════════════════════════════════════
  • 制度閘門：以恒指 5y 制度序列（regime_history 向量化）建 boolean Series，
    經 run_backtest 的 market_filter_series（hsi_filter 參數）AND 進買入訊號。
    制度由 bar i 收盤前數據算出、閘 bar i 的訊號、i+1 開盤進場 → 無前視。
    序列起點前的日期 fillna(True)（僅影響 Fold1 IS 前段，可接受）。
  • ROC 強度：monkey-patch backtest/walk_forward 模組內已綁定的
    precompute_signals 引用，把 b17 與更深 roc5 門檻 AND。
    只在本測試腳本生效，不碰 core/。
  • 錨點：「ROC-8 × 全制度」應複現上輪 T20 基準（混合 ≈ +0.97%）。
  • BASE 格附「逐制度診斷分解」：每筆混合交易按進場日恒指制度分桶，
    驗證 G1/G2 的機制故事是否成立（純診斷，不得用它事後再造新閘門）。

使用：cd 專案根目錄 → python scripts/test_b17_regime_intensity.py
預估 9 格 × ~2 分鐘 ≈ 20 分鐘（G2/深 ROC 格訊號較少會快一些）。
"""
import os
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import pandas as pd

from data import load_stocks, get_stock_data
from historical_universe import load_eodhd_prices
from indicators import calculate_indicators
from regime import regime_history
import indicators as _ind
import backtest as _bt
import walk_forward as _wf
from walk_forward import run_portfolio_walk_forward
from config import COMMISSION_PCT, SLIPPAGE_PCT


# ══════════════════════════════════════════════════════════════════
# 策略定義（b17 tuple 與 ACTIVE 一字不差；出場固定 T20+s2+MIN5）
# ══════════════════════════════════════════════════════════════════
def make_buy(*active) -> tuple:
    idx = {f"b{i+1}": i for i in range(19)}
    t = [False] * 19
    for a in active:
        t[idx[a]] = True
    return tuple(t)


BUY_B17 = make_buy("b17")
SELL_S2 = (False, True, False, False, False, False, False, False)
MIN_HOLD = 5
MAX_HOLD = 20            # 上輪證實的高原頂，固定不掃
IS_MONTHS = 12
OOS_MONTHS = 6
TRADE_SIZE = 100_000

PASS_BLENDED = 2.0
PASS_POS_RATE = 60.0
MIN_SAMPLE = 500

ALL_REGIMES = {"強牛市", "弱牛市", "牛市警惕", "熊市觀察",
               "弱熊市", "強熊市", "震盪市", "轉折期"}

GATES = {
    "ALL":  None,                                        # 全制度（錨點）
    "G1":   ALL_REGIMES - {"強熊市", "弱熊市"},          # 排除硬熊
    "G2":   {"震盪市", "轉折期", "熊市觀察", "牛市警惕"},  # 僅均值回歸制度
}

# 9 格預宣告：(名稱, roc 門檻, 閘門 key)
GRID = [
    ("ROC-8 × 全制度(錨點)", -8.0,  "ALL"),
    ("ROC-8 × G1排除硬熊",   -8.0,  "G1"),
    ("ROC-8 × G2震盪系",     -8.0,  "G2"),
    ("ROC-10 × 全制度",      -10.0, "ALL"),
    ("ROC-10 × G1排除硬熊",  -10.0, "G1"),
    ("ROC-10 × G2震盪系",    -10.0, "G2"),
    ("ROC-12 × 全制度",      -12.0, "ALL"),
    ("ROC-12 × G1排除硬熊",  -12.0, "G1"),
    ("ROC-12 × G2震盪系",    -12.0, "G2"),
]


# ══════════════════════════════════════════════════════════════════
# ROC 強度：monkey-patch（只在本腳本進程內生效，不碰 core/ 檔案）
# ══════════════════════════════════════════════════════════════════
_ORIG_PRECOMPUTE = _ind.precompute_signals
_ROC_THRESHOLD = [-8.0]   # 可變 cell；-8 = 不加深（b17 原生即 roc5 < -8）


def _patched_precompute(df, hsi_bullish=True):
    sigs = _ORIG_PRECOMPUTE(df, hsi_bullish)
    thr = _ROC_THRESHOLD[0]
    if thr < -8.0:   # 只在要求比原生更深時才額外 AND
        roc5 = (df["Close"] - df["Close"].shift(5)) / df["Close"].shift(5) * 100
        deeper = (roc5 < thr).fillna(False)
        sigs["b17"] = sigs["b17"] & deeper
    return sigs


# backtest / walk_forward 在 import 時已各自綁定 precompute_signals 引用，
# 必須逐一覆寫模組屬性（只 patch indicators 不會生效）。
_bt.precompute_signals = _patched_precompute
_wf.precompute_signals = _patched_precompute


# ══════════════════════════════════════════════════════════════════
# 制度閘門：恒指 5y 制度序列（無前視：bar i 制度由 ≤i 數據算出）
# ══════════════════════════════════════════════════════════════════
def build_regime_label_series():
    """回 pd.Series(label, index=DatetimeIndex)；失敗回 None。"""
    raw = get_stock_data("^HSI", "5y")
    if raw is None or raw.empty:
        return None
    hsi = calculate_indicators(raw)
    hist = regime_history(hsi, n_bars=len(hsi))
    if not hist:
        return None
    return pd.Series(
        [r["label"] for r in hist],
        index=pd.DatetimeIndex([r["date"] for r in hist]),
    ).sort_index()


def gate_series_from(labels: pd.Series, allowed: set):
    """allowed=None → 不設閘（回 None）；否則回 boolean Series 供 hsi_filter 用。"""
    if allowed is None:
        return None
    return labels.isin(allowed)


def regime_at(labels: pd.Series, buy_date) -> str:
    """逐筆診斷用：取進場日（含）之前最近一根的制度標籤。"""
    idx = labels.index.searchsorted(pd.Timestamp(buy_date), side="right") - 1
    if idx < 0:
        return "（序列前）"
    return labels.iloc[idx]


# ══════════════════════════════════════════════════════════════════
# 數據
# ══════════════════════════════════════════════════════════════════
def build_stock_data(tickers: list) -> tuple:
    stock_data, skipped = {}, 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        stock_data[tkr] = df
    return stock_data, skipped


# ══════════════════════════════════════════════════════════════════
# 彙總（沿用上輪：混合真實回報為唯一裁決）
# ══════════════════════════════════════════════════════════════════
def collect_blended_trades(wf_results: list) -> list:
    """回 [(buy_date, 回報%, 來源)]：oos_trades ∪ 已平倉延伸單。"""
    out = []
    for r in wf_results:
        for t in r.get("oos_trades", []):
            out.append((t.get("_buy_date"), float(t["回報%"]), "in"))
        for t in r.get("oos_extended_trades", []):
            if t.get("_still_held_at_end", False):
                continue
            out.append((t.get("_buy_date"), float(t["回報%"]), "ext"))
    return out


def summarize(wf_results: list) -> dict:
    blended = collect_blended_trades(wf_results)
    in_rets = [r for _, r, src in blended if src == "in"]
    ext_rets = [r for _, r, src in blended if src == "ext"]
    all_rets = in_rets + ext_rets

    forced = sum(r.get("forced_exit_count", 0) for r in wf_results)
    still = sum(
        1 for r in wf_results for t in r.get("oos_extended_trades", [])
        if t.get("_still_held_at_end", False)
    )
    valid = [r for r in wf_results if r.get("valid_oos")]
    pos = sum(1 for r in valid
              if (r.get("oos_metrics") or {}).get("平均每筆回報%", 0.0) > 0)

    def _avg(xs):
        return sum(xs) / len(xs) if xs else None

    def _wr(xs):
        return sum(1 for x in xs if x > 0) / len(xs) * 100 if xs else None

    return {
        "blended": _avg(all_rets), "blended_wr": _wr(all_rets), "n_total": len(all_rets),
        "in_avg": _avg(in_rets), "in_n": len(in_rets),
        "ext_avg": _avg(ext_rets), "ext_n": len(ext_rets),
        "forced": forced, "still_held": still,
        "pos_folds": pos, "valid_folds": len(valid),
        "pos_rate": (pos / len(valid) * 100) if valid else 0.0,
        "_blended_trades": blended,   # 供逐制度診斷
    }


def verdict(s: dict) -> str:
    if s["blended"] is None or s["n_total"] < MIN_SAMPLE:
        return f"⚪ 樣本薄({s['n_total']}筆)"
    if s["blended"] >= PASS_BLENDED and s["pos_rate"] >= PASS_POS_RATE:
        return "🟢 候選過關(待高原檢查)"
    if s["blended"] >= 1.0:
        return "🟡 接近但不過"
    if s["blended"] >= 0:
        return "🟠 打平"
    return "🔴 負"


def _fmt(v, fmt="{:+.2f}%"):
    return fmt.format(v) if v is not None else "N/A"


def print_regime_breakdown(s: dict, labels: pd.Series):
    """BASE 格逐制度診斷：驗證 G1/G2 機制故事。純診斷，不得據此再造新閘門。"""
    buckets: dict = {}
    for buy_d, ret, _src in s["_blended_trades"]:
        if buy_d is None:
            continue
        buckets.setdefault(regime_at(labels, buy_d), []).append(ret)
    print("\n  🔬 逐制度診斷分解（BASE 格，混合口徑，純診斷）：")
    print(f"  {'制度':<8} {'筆數':>6} {'均回報%':>9} {'勝率%':>7} {'佔比%':>7}")
    total = sum(len(v) for v in buckets.values()) or 1
    for lab in sorted(buckets, key=lambda k: -len(buckets[k])):
        rets = buckets[lab]
        n = len(rets)
        avg = sum(rets) / n
        wr = sum(1 for r in rets if r > 0) / n * 100
        print(f"  {lab:<8} {n:>6} {avg:>+9.2f} {wr:>7.1f} {n/total*100:>7.1f}")


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run_one(name, roc_thr, gate_key, stock_data, labels):
    print(f"\n────────────────────────────────────────")
    print(f"▶ b17 × {name}  (ROC<{roc_thr:.0f}, 閘門={gate_key}, T{MAX_HOLD}+s2)")
    t0 = time.time()
    _ROC_THRESHOLD[0] = roc_thr
    hsi_filter = gate_series_from(labels, GATES[gate_key])

    last_print = [0.0]
    def cb(fold, total_folds, ticker):
        now = time.time()
        if now - last_print[0] > 1.0:
            print(f"    fold {fold}/{total_folds}  {ticker}", end="\r", flush=True)
            last_print[0] = now

    wf = run_portfolio_walk_forward(
        stock_data,
        buy_sigs=BUY_B17,
        sell_sigs=SELL_S2,
        is_months=IS_MONTHS,
        oos_months=OOS_MONTHS,
        trade_size=TRADE_SIZE,
        slippage=SLIPPAGE_PCT,
        commission_pct=COMMISSION_PCT,
        min_hold_days=MIN_HOLD,
        max_hold_days=MAX_HOLD,
        hsi_filter=hsi_filter,
        track_extended=True,
        use_pit_universe=True,
        progress_cb=cb,
    )
    print(" " * 80, end="\r")

    s = summarize(wf)
    g = verdict(s)
    print(f"  ✓ {time.time()-t0:.1f}s")
    print(f"  混合真實回報 : {_fmt(s['blended'])}（勝率 {_fmt(s['blended_wr'], '{:.1f}%')}，{s['n_total']} 筆）")
    print(f"  in-window    : {_fmt(s['in_avg'])}（{s['in_n']} 筆）｜ 延伸 {_fmt(s['ext_avg'])}（{s['ext_n']} 筆；仍持倉 {s['still_held']}）")
    print(f"  強制平倉 {s['forced']} ｜ 正Fold {s['pos_folds']}/{s['valid_folds']}（{s['pos_rate']:.0f}%）")
    print(f"  判定         : {g}")
    return {"name": name, "summary": s, "verdict": g}


def print_table(rows):
    print("\n" + "═" * 104)
    print(f"  b17 制度閘門 × ROC 強度 — 混合真實回報對比"
          f"（門檻：≥ +{PASS_BLENDED:.1f}%、正Fold ≥ {PASS_POS_RATE:.0f}%、高原、樣本 ≥ {MIN_SAMPLE}）")
    print("═" * 104)
    print(f"{'配置':<24} {'混合%':>8} {'勝率%':>7} {'總筆':>6} {'inW%':>8} "
          f"{'ext%':>8} {'正Fold':>8}  判定")
    print("─" * 104)
    for r in rows:
        if r is None:
            continue
        s = r["summary"]
        print(f"{r['name']:<24} "
              f"{_fmt(s['blended'], '{:+.2f}'):>8} "
              f"{_fmt(s['blended_wr'], '{:.1f}'):>7} "
              f"{s['n_total']:>6} "
              f"{_fmt(s['in_avg'], '{:+.2f}'):>8} "
              f"{_fmt(s['ext_avg'], '{:+.2f}'):>8} "
              f"{s['pos_folds']}/{s['valid_folds']:<5}  {r['verdict']}")
    print("═" * 104)
    print("\n💡 判讀提醒：")
    print("   • 錨點（ROC-8 × 全制度）混合應 ≈ +0.97%；偏差大先查環境，不要直接信本輪。")
    print("   • 高原檢查：過關格的相鄰格（同閘門鄰 ROC / 同 ROC 鄰閘門）須同向。")
    print("   • 逐制度診斷只用來驗證 G1/G2 的機制故事，不得據此事後再造第三個閘門（= data mining）。")
    print("   • 本輪是 b17 最後一輪：9 格全敗 → 結案，b17 留 ACTIVE 作分析，不實盤。")


def main() -> int:
    t_start = time.time()
    print("═" * 104)
    print("  b17 救援最終輪：制度閘門 × ROC 強度（PIT WF 12+6，5y，T20+s2+MIN5 固定，9 格預宣告）")
    print("═" * 104)

    labels = build_regime_label_series()
    if labels is None or len(labels) < 200:
        print("❌ 無法取得恒指 5y 制度序列（yfinance/^HSI），制度閘門無法建立，中止。")
        return 1
    print(f"\n恒指制度序列：{len(labels)} 根（{labels.index[0].date()} → {labels.index[-1].date()}）")
    dist = labels.value_counts()
    print("  制度分佈：" + " ｜ ".join(f"{k} {v}" for k, v in dist.items()))

    tickers = load_stocks()
    print(f"\nstocks.txt 共 {len(tickers)} 隻；載入 EODHD…")
    stock_data, skipped = build_stock_data(tickers)
    print(f"已載入 {len(stock_data)} 隻（跳過 {skipped} 隻數據不足）")
    if len(stock_data) < 10:
        print("❌ 可用股票太少（<10），中止。")
        return 1

    rows = []
    for i, (name, roc_thr, gate_key) in enumerate(GRID):
        r = run_one(name, roc_thr, gate_key, stock_data, labels)
        rows.append(r)
        if i == 0:   # 錨點格附逐制度診斷
            print_regime_breakdown(r["summary"], labels)

    print_table(rows)

    passed = [r for r in rows if r and r["verdict"].startswith("🟢")]
    if passed:
        print(f"\n🟢 通過數字門檻的格 {len(passed)} 個（仍需高原檢查 + 機制故事核對）：")
        for r in passed:
            print(f"   • {r['name']}  混合 {_fmt(r['summary']['blended'])}（{r['summary']['n_total']} 筆）")
        print("\n   下一步：整張表 + 逐制度診斷貼回對話 → 高原/機制雙重核對 → 才走復活程序。")
        print("   注意：制度閘門過關的話，daily_scan 端已天然具備制度過濾（REGIME_RECs +")
        print("   熊市閘門），但需核對「閘門允許集合」與線上推播制度集合一致，避免研究/實盤口徑分裂。")
    else:
        print("\n⚠️ 9 格全數未過 +2.0% 門檻 → 按預宣告紀律結案：")
        print("   b17 進場 alpha 上限 ≈ +1.4%（in-window, T20），扣成本後混合 ≈ +1.0%，不足實盤。")
        print("   處置：b17 留 ACTIVE 作分析/回測用途，LIVE_PRESET_KEYS 維持空集。")

    print(f"\n總耗時：{time.time()-t_start:.1f} 秒 ({(time.time()-t_start)/60:.1f} 分鐘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

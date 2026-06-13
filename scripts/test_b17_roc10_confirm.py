"""
test_b17_roc10_confirm.py -- 勝出格確認：b17 × ROC<-10 × 全制度 × T20+s2+MIN5

═══════════════════════════════════════════════════════════════════
目的（接 test_b17_regime_intensity.py 結果，2026-06-12）
═══════════════════════════════════════════════════════════════════
  9 格中唯一過三道門的格：ROC-10 × 全制度（混合 +2.49% / 正Fold 7/11 / n=1811），
  且 ROC 深度維度為單調梯度（-8→-10→-12 = +0.97→+2.49→+3.29），高原成立。

  但有兩個必須在裁決前攤開的問題：
    1. 事件集中風險：強熊市 5 年僅 34 個交易日卻貢獻最肥的 alpha 桶
       → 有效獨立事件數遠小於交易筆數，必須看 alpha 是否全押在 2022。
    2. 研究/實盤口徑分裂：daily_scan 熊市閘門會擋掉強/弱熊市訊號
       → 現行線上配置的真實預期 ≈ G1 格 +0.93%（不過關）。
       本腳本同時輸出「含熊市」與「剔除硬熊後」兩套逐年/逐 fold 數字，
       供 Ivan 做「是否開熊市例外」的風險決策。

═══════════════════════════════════════════════════════════════════
輸出
═══════════════════════════════════════════════════════════════════
  ① 逐 Fold 表：OOS 期間 / in-window 均回報 / 筆數 / 強制 / fold 混合均回報
     → 看正 fold 分佈、最近 fold（2025-2026）是正是負。
  ② 逐制度分解（混合口徑，ROC-10 深度下重算，非沿用 BASE 格）。
  ③ 逐年分解：alpha 是分散還是全押 2022。
  ④ 對照欄：每張表同時給「全部」與「剔除硬熊（強熊市+弱熊市）」兩列
     → 後者 ≈ 現行線上閘門下的真實預期。
  ⑤ 匯出混合回報序列 data/b17_roc10_blended_returns.json
     （[ [buy_date, 回報%, 制度], ... ]，按進場日排序）供 MC 定倉分析。

使用：cd 專案根目錄 → python scripts/test_b17_roc10_confirm.py
"""
import os
import sys
import json
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT_PATH = os.path.join(ROOT, "data", "b17_roc10_blended_returns.json")


# ── 勝出格參數（鎖定，不掃）─────────────────────────────────────────
def make_buy(*active) -> tuple:
    idx = {f"b{i+1}": i for i in range(19)}
    t = [False] * 19
    for a in active:
        t[idx[a]] = True
    return tuple(t)


BUY_B17 = make_buy("b17")
SELL_S2 = (False, True, False, False, False, False, False, False)
ROC_THRESHOLD = -10.0
MIN_HOLD = 5
MAX_HOLD = 20
HARD_BEAR = {"強熊市", "弱熊市"}


# ── ROC 深度 patch（同上輪實作）──────────────────────────────────────
_ORIG_PRECOMPUTE = _ind.precompute_signals


def _patched_precompute(df, hsi_bullish=True):
    sigs = _ORIG_PRECOMPUTE(df, hsi_bullish)
    roc5 = (df["Close"] - df["Close"].shift(5)) / df["Close"].shift(5) * 100
    sigs["b17"] = sigs["b17"] & (roc5 < ROC_THRESHOLD).fillna(False)
    return sigs


_bt.precompute_signals = _patched_precompute
_wf.precompute_signals = _patched_precompute


# ── 制度標籤序列（診斷用）────────────────────────────────────────────
def build_regime_label_series():
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


def regime_at(labels: pd.Series, buy_date) -> str:
    idx = labels.index.searchsorted(pd.Timestamp(buy_date), side="right") - 1
    if idx < 0:
        return "（序列前）"
    return labels.iloc[idx]


# ── 統計小工具 ───────────────────────────────────────────────────────
def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def _wr(xs):
    return sum(1 for x in xs if x > 0) / len(xs) * 100 if xs else None


def _f(v, fmt="{:+.2f}"):
    return fmt.format(v) if v is not None else "  N/A"


def _stat_line(rets):
    return f"n={len(rets):>5}  均={_f(_avg(rets)):>7}%  勝率={_f(_wr(rets), '{:.1f}'):>6}%"


def main() -> int:
    t0 = time.time()
    print("═" * 96)
    print(f"  勝出格確認：b17 × ROC<{ROC_THRESHOLD:.0f} × 全制度 × T{MAX_HOLD}+s2+MIN{MIN_HOLD}（PIT WF 12+6）")
    print("═" * 96)

    labels = build_regime_label_series()
    if labels is None:
        print("❌ 無法取得恒指制度序列，中止。")
        return 1

    tickers = load_stocks()
    stock_data, skipped = {}, 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        stock_data[tkr] = df
    print(f"\n已載入 {len(stock_data)} 隻（跳過 {skipped}）；恒指制度序列 {len(labels)} 根")

    last_print = [0.0]
    def cb(fold, total_folds, ticker):
        now = time.time()
        if now - last_print[0] > 1.0:
            print(f"    fold {fold}/{total_folds}  {ticker}", end="\r", flush=True)
            last_print[0] = now

    wf = run_portfolio_walk_forward(
        stock_data,
        buy_sigs=BUY_B17, sell_sigs=SELL_S2,
        is_months=12, oos_months=6,
        trade_size=100_000,
        slippage=SLIPPAGE_PCT, commission_pct=COMMISSION_PCT,
        min_hold_days=MIN_HOLD, max_hold_days=MAX_HOLD,
        track_extended=True, use_pit_universe=True,
        progress_cb=cb,
    )
    print(" " * 80, end="\r")
    print(f"  ✓ WF 完成（{time.time()-t0:.1f}s，{len(wf)} folds）")

    # ── 收集混合交易（含 fold 歸屬與制度標籤）────────────────────────
    all_trades = []   # (fold, buy_date, ret, regime)
    for r in wf:
        fold_n = r.get("fold")
        for t in r.get("oos_trades", []):
            bd = t.get("_buy_date")
            all_trades.append((fold_n, bd, float(t["回報%"]), regime_at(labels, bd)))
        for t in r.get("oos_extended_trades", []):
            if t.get("_still_held_at_end", False):
                continue
            bd = t.get("_buy_date")
            all_trades.append((fold_n, bd, float(t["回報%"]), regime_at(labels, bd)))

    rets_all = [x[2] for x in all_trades]
    rets_nobear = [x[2] for x in all_trades if x[3] not in HARD_BEAR]

    print("\n" + "─" * 96)
    print("  總覽（混合真實回報口徑）")
    print("─" * 96)
    print(f"  全部（=回測口徑）      ：{_stat_line(rets_all)}")
    print(f"  剔除硬熊（≈線上閘門口徑）：{_stat_line(rets_nobear)}")
    print("  ⚠️ 兩列的差距 = 熊市閘門吃掉的 alpha；線上不開例外，拿到的是下面那列。")

    # ── ① 逐 Fold 表 ────────────────────────────────────────────────
    print("\n" + "─" * 96)
    print("  ① 逐 Fold（看 alpha 分佈 + 最近 fold 是正是負）")
    print("─" * 96)
    print(f"  {'Fold':<5} {'OOS 期間':<20} {'混合n':>6} {'混合均%':>8} "
          f"{'剔硬熊n':>7} {'剔硬熊均%':>9} {'強制':>5}")
    for r in wf:
        fold_n = r.get("fold")
        ft = [x for x in all_trades if x[0] == fold_n]
        ft_nb = [x for x in ft if x[3] not in HARD_BEAR]
        period = f"{r['oos_start'].strftime('%Y-%m')}→{r['oos_end'].strftime('%Y-%m')}"
        rets_f = [x[2] for x in ft]
        rets_fnb = [x[2] for x in ft_nb]
        print(f"  {fold_n:<5} {period:<20} {len(rets_f):>6} {_f(_avg(rets_f)):>8} "
              f"{len(rets_fnb):>7} {_f(_avg(rets_fnb)):>9} {r.get('forced_exit_count', 0):>5}")

    # ── ② 逐制度分解（ROC-10 深度下重算）────────────────────────────
    print("\n" + "─" * 96)
    print("  ② 逐制度分解（ROC-10 深度，混合口徑）")
    print("─" * 96)
    buckets: dict = {}
    for _, _, ret, lab in all_trades:
        buckets.setdefault(lab, []).append(ret)
    total = len(all_trades) or 1
    print(f"  {'制度':<8} {'筆數':>6} {'均回報%':>9} {'勝率%':>7} {'佔比%':>7}")
    for lab in sorted(buckets, key=lambda k: -len(buckets[k])):
        rs = buckets[lab]
        print(f"  {lab:<8} {len(rs):>6} {_f(_avg(rs)):>9} {_f(_wr(rs), '{:.1f}'):>7} {len(rs)/total*100:>7.1f}")

    # ── ③ 逐年分解（全押 2022？）────────────────────────────────────
    print("\n" + "─" * 96)
    print("  ③ 逐年分解（進場年；alpha 是分散還是押單一崩盤年）")
    print("─" * 96)
    by_year: dict = {}
    for _, bd, ret, lab in all_trades:
        y = pd.Timestamp(bd).year
        by_year.setdefault(y, {"all": [], "nb": []})
        by_year[y]["all"].append(ret)
        if lab not in HARD_BEAR:
            by_year[y]["nb"].append(ret)
    print(f"  {'年份':<6} {'全部n':>6} {'全部均%':>8} {'剔硬熊n':>8} {'剔硬熊均%':>9}")
    for y in sorted(by_year):
        d = by_year[y]
        print(f"  {y:<6} {len(d['all']):>6} {_f(_avg(d['all'])):>8} "
              f"{len(d['nb']):>8} {_f(_avg(d['nb'])):>9}")

    # ── ⑤ 匯出供 MC 定倉 ────────────────────────────────────────────
    export = sorted(
        [[pd.Timestamp(bd).strftime("%Y-%m-%d"), round(ret, 4), lab]
         for _, bd, ret, lab in all_trades],
        key=lambda x: x[0],
    )
    try:
        os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
        with open(EXPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False)
        print(f"\n✅ 已匯出混合回報序列 {len(export)} 筆 → {os.path.relpath(EXPORT_PATH, ROOT)}")
        print("   （[進場日, 回報%, 制度]；供 Block Bootstrap MC 定倉；⚠️ 勿 commit 進 repo 可加 .gitignore）")
    except Exception as e:
        print(f"\n⚠️ 匯出失敗：{type(e).__name__}: {e}")

    print("\n" + "═" * 96)
    print("  裁決清單（人工核對）：")
    print("  □ 最近 2 個 fold（2025-2026）混合均回報是否 ≥ 0？（負 = 近期退化，黃旗）")
    print("  □ 逐年表：剔除 2022 後其餘年份均值是否仍 > 成本（>0.5%）？（否 = 單一事件依賴）")
    print("  □ 「剔除硬熊」列是否遠低於 +2%？（是 = 不開熊市例外就沒有這支策略，決策交 Ivan）")
    print("  □ 強熊市桶的訊號日數（episode 數）：404 筆 ≠ 404 個獨立事件，定倉必須用 MC 保守值。")
    print("═" * 96)
    print(f"\n總耗時：{time.time()-t0:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

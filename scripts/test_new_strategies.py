"""
test_new_strategies.py -- 測試 3 個新「🔬」策略的 Portfolio Walk-Forward

跑：
  • 🔬 b12+b6 資金流向超賣
  • 🔬 b11+b5 KDJ超賣布林雙確認
  • 🔬 b3+b7+b8 底背離趨勢確認
基準：💎M30 純粹均值回歸MIN30（已知 OOS ≈ +3.31%）

設定：is_months=12, oos_months=6, trade_size=100000，前 60 隻 stocks.txt 股票。
資料來源：data/eodhd_prices/{ticker}.json（已含 5 年 OHLCV + indicators）。
"""

import os
import sys
import time
from io import StringIO

# 修正 Windows console 印 emoji（cp950）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 把 core/ 加進 path（沿用 scripts/daily_scan.py pattern）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

from data import load_stocks
from historical_universe import load_eodhd_prices
from walk_forward import run_portfolio_walk_forward
from config import (
    ACTIVE_PRESETS,
    COMMISSION_PCT,
    SLIPPAGE_PCT,
    WF_ROBUST_MAX_DEGRADATION,
    WF_ROBUST_MIN_OOS_POS_RATE,
    WF_WARNING_MAX_DEGRADATION,
    WF_WARNING_MIN_OOS_POS_RATE,
    WF_MIN_IS_RETURN_FOR_CALC,
)


TARGETS = [
    "🔬 b12+b6 資金流向超賣",
    "🔬 b11+b5 KDJ超賣布林雙確認",
    "🔬 b3+b7+b8 底背離趨勢確認",
]
BENCHMARK = "💎M30 純粹均值回歸MIN30"
N_STOCKS = 60


def rate(avg_oos: float, avg_deg, oos_pos_rate: float) -> str:
    """套用 config.py 的 WF 門檻評級。"""
    if avg_oos is None or avg_deg is None:
        return "⚪ N/A"
    if avg_oos > 0 \
       and avg_deg < WF_ROBUST_MAX_DEGRADATION \
       and oos_pos_rate >= WF_ROBUST_MIN_OOS_POS_RATE:
        return "🟢 穩健"
    if avg_oos > 0 \
       and avg_deg < WF_WARNING_MAX_DEGRADATION \
       and oos_pos_rate >= WF_WARNING_MIN_OOS_POS_RATE:
        return "🟡 尚可"
    return "🔴 危險"


def build_stock_data(tickers: list) -> dict:
    """從 EODHD JSON 載入前 N_STOCKS 隻可用股票。"""
    stock_data = {}
    skipped = 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        stock_data[tkr] = df
        if len(stock_data) >= N_STOCKS:
            break
    return stock_data, skipped


def summarize_wf(wf_results: list) -> dict:
    """濃縮 WF fold 列表為 5 個摘要數字。"""
    if not wf_results:
        return {
            "avg_is": None, "avg_oos": None, "avg_deg": None,
            "oos_pos": 0, "valid_folds": 0, "total_folds": 0,
        }
    total_folds = len(wf_results)
    valid = [r for r in wf_results if r.get("valid_oos")]
    valid_folds = len(valid)

    is_rets = [r["is_metrics"].get("平均每筆回報%", 0.0)
               for r in valid if r["is_metrics"]]
    oos_rets = [r["oos_metrics"].get("平均每筆回報%", 0.0)
                for r in valid if r["oos_metrics"]]
    avg_is = sum(is_rets) / len(is_rets) if is_rets else None
    avg_oos = sum(oos_rets) / len(oos_rets) if oos_rets else None

    if avg_is is not None and avg_oos is not None and abs(avg_is) >= WF_MIN_IS_RETURN_FOR_CALC:
        avg_deg = (avg_is - avg_oos) / abs(avg_is) * 100
    else:
        avg_deg = None

    oos_pos = sum(1 for r in valid
                  if r["oos_metrics"].get("平均每筆回報%", 0.0) > 0)
    return {
        "avg_is": avg_is, "avg_oos": avg_oos, "avg_deg": avg_deg,
        "oos_pos": oos_pos, "valid_folds": valid_folds, "total_folds": total_folds,
    }


def run_one(name: str, stock_data: dict) -> dict:
    if name not in ACTIVE_PRESETS:
        print(f"  ⚠️ {name} 不在 ACTIVE_PRESETS，跳過")
        return None
    p = ACTIVE_PRESETS[name]

    print(f"\n────────────────────────────────────────")
    print(f"▶ 跑：{name}")
    print(f"  buy={p['buy']}")
    print(f"  sell={p['sell']}")
    print(f"  min_hold_days={p.get('min_hold_days')}")

    t0 = time.time()

    # 進度回呼：每 ticker 印一行（覆寫）
    last_print = [0.0]
    def cb(fold, total_folds, ticker):
        now = time.time()
        if now - last_print[0] > 1.0:
            print(f"    fold {fold}/{total_folds}  {ticker}", end="\r", flush=True)
            last_print[0] = now

    wf = run_portfolio_walk_forward(
        stock_data,
        buy_sigs=p["buy"],
        sell_sigs=p["sell"],
        is_months=12,
        oos_months=6,
        trade_size=100_000,
        slippage=SLIPPAGE_PCT,
        commission_pct=COMMISSION_PCT,
        min_hold_days=p.get("min_hold_days"),
        cooldown_days=p.get("cooldown_days"),
        seasonal_filter=p.get("seasonal_filter", False),
        track_extended=False,
        progress_cb=cb,
    )
    print(" " * 80, end="\r")  # 清空進度行

    summary = summarize_wf(wf)
    elapsed = time.time() - t0
    print(f"  ✓ {elapsed:.1f}s  folds {summary['valid_folds']}/{summary['total_folds']}")

    is_str = f"{summary['avg_is']:+.2f}%" if summary["avg_is"] is not None else "N/A"
    oos_str = f"{summary['avg_oos']:+.2f}%" if summary["avg_oos"] is not None else "N/A"
    deg_str = f"{summary['avg_deg']:.1f}%" if summary["avg_deg"] is not None else "N/A"
    pos_str = f"{summary['oos_pos']}/{summary['valid_folds']}"
    pos_rate = (summary["oos_pos"] / summary["valid_folds"] * 100) if summary["valid_folds"] else 0.0
    grade = rate(summary["avg_oos"], summary["avg_deg"], pos_rate)

    print(f"  IS avg     : {is_str}")
    print(f"  OOS avg    : {oos_str}")
    print(f"  退化率     : {deg_str}")
    print(f"  OOS正Fold  : {pos_str} ({pos_rate:.0f}%)")
    print(f"  評級       : {grade}")

    return {
        "name": name,
        "summary": summary,
        "pos_rate": pos_rate,
        "grade": grade,
    }


def print_table(rows: list):
    print("\n" + "═" * 96)
    print("  策略對比表  (基準：💎M30 純粹均值回歸MIN30，已知 OOS ≈ +3.31%)")
    print("═" * 96)

    header = f"{'策略':<36} {'IS%':>10} {'OOS%':>10} {'退化%':>10} {'正Fold':>10} {'評級':>10}"
    print(header)
    print("─" * 96)
    for r in rows:
        if r is None:
            continue
        s = r["summary"]
        is_str  = f"{s['avg_is']:+.2f}"  if s["avg_is"]  is not None else "N/A"
        oos_str = f"{s['avg_oos']:+.2f}" if s["avg_oos"] is not None else "N/A"
        deg_str = f"{s['avg_deg']:.1f}"  if s["avg_deg"] is not None else "N/A"
        pos_str = f"{s['oos_pos']}/{s['valid_folds']}"
        name = r["name"]
        if len(name) > 35:
            name = name[:34] + "…"
        print(f"{name:<36} {is_str:>10} {oos_str:>10} {deg_str:>10} {pos_str:>10} {r['grade']:>10}")
    print("═" * 96)


def main() -> int:
    t_start = time.time()
    print("═" * 96)
    print("  測試 3 個新策略 + 1 個基準  (Portfolio Walk-Forward, 12+6, $100k)")
    print("═" * 96)

    tickers = load_stocks()
    print(f"stocks.txt 共 {len(tickers)} 隻；準備載入前 {N_STOCKS} 隻可用 EODHD 數據…")
    stock_data, skipped = build_stock_data(tickers)
    print(f"已載入 {len(stock_data)} 隻（前 {N_STOCKS} 隻命中，跳過 {skipped} 隻數據不足）")

    if len(stock_data) < 10:
        print("❌ 可用股票太少（<10），中止。請檢查 data/eodhd_prices/ 是否存在。")
        return 1

    all_strategies = TARGETS + [BENCHMARK]
    rows = []
    for name in all_strategies:
        rows.append(run_one(name, stock_data))

    print_table(rows)

    elapsed = time.time() - t_start
    print(f"\n總耗時：{elapsed:.1f} 秒 ({elapsed/60:.1f} 分鐘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

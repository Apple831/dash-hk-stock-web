"""
test_b17_blended.py -- b17 真正的「混合真實回報」（降級前最後驗證）

═══════════════════════════════════════════════════════════════════
為什麼要這支
═══════════════════════════════════════════════════════════════════
  Phase 4 的「真實出場%」只統計【邊界強制平倉 → 延伸追蹤】那一群（cohort），
  不是策略整體回報。而這個 cohort 在不同出場規則下被「選出來」的方式不同：
    • 止損版：跌的單先被砍 → 撐到邊界的 cohort = 贏家 → 延伸 +2.64%（選擇性偏誤偏高）
    • 時間版：每單 20 天砍、不分輸贏 → cohort 無篩選 → 延伸 −2.29%
  兩者都不是 b17 的整體真實回報。

  正確的「混合真實回報（blended）」＝把兩群【逐筆】合併平均：
    blended = mean( 所有 in-window 策略單的 回報%  ∪  所有邊界單延伸實現的 回報% )
  其中 in-window 策略單 = oos_metrics 統計的那群（強制平倉被排除），
       邊界單 = 強制平倉，用延伸追蹤（套用同一風險出場規則）跑到真實出場。
  這個數字不受 cohort 選擇偏誤影響，是 b17 的誠實整體回報。

  引擎事實（walk_forward.py 核實）：
    • oos_metrics = calc_bt_metrics(oos_strategy_trades) → 強制平倉「不」計入（survivorship）。
    • oos_extended_trades = 強制平倉用 run_backtest 帶 stop/max_hold 跑到真實出場。
    • 策略單與延伸單皆有 "回報%" 欄位 → 可逐筆合併。

═══════════════════════════════════════════════════════════════════
預期
═══════════════════════════════════════════════════════════════════
  若 b17 的 blended 在止損版與時間版收斂到同一個值（且落在打平帶、< +2%），
  則證明 +2.64% 是 cohort 選擇偏誤、b17 誠實口徑打平 → 支持與其他一起降級（路線 A）。

使用：python scripts/test_b17_blended.py   （約 4 分鐘，b17 × 止損/時間 兩版）
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

from data import load_stocks
from historical_universe import load_eodhd_prices
from walk_forward import run_portfolio_walk_forward
from config import ACTIVE_PRESETS, COMMISSION_PCT, SLIPPAGE_PCT

TARGET = "💎 b17 ROC超跌反彈"
VARIANTS = {
    "s2 + 止損10": {"stop_loss_pct": 10,   "max_hold_days": None},
    "s2 + 時間20": {"stop_loss_pct": None, "max_hold_days": 20},
}


def build_stock_data(tickers):
    sd, skipped = {}, 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        sd[tkr] = df
    return sd, skipped


def _rets(trades):
    """逐筆取 回報%（跳過 None）。"""
    return [t["回報%"] for t in trades
            if t.get("回報%") is not None]


def analyze(wf):
    """把全 fold 的策略單 + 延伸（已真實出場）單逐筆合併，算 blended。"""
    strat_rets = []
    ext_closed_rets = []
    still_held = 0
    for r in wf:
        # in-window 策略單（強制平倉已被引擎排除在 oos_trades 外）
        strat_rets += _rets(r.get("oos_trades", []))
        # 邊界強制單 → 延伸追蹤真實出場
        for t in r.get("oos_extended_trades", []):
            if t.get("_still_held_at_end", False):
                still_held += 1
            elif t.get("回報%") is not None:
                ext_closed_rets.append(t["回報%"])

    n_s, n_e = len(strat_rets), len(ext_closed_rets)
    headline = sum(strat_rets) / n_s if n_s else None          # in-window（=頂部，逐筆加權）
    cohort   = sum(ext_closed_rets) / n_e if n_e else None      # 邊界 cohort（Phase 4 的真實出場%）
    allr     = strat_rets + ext_closed_rets
    blended  = sum(allr) / len(allr) if allr else None          # ★混合真實回報★

    def wr(rs):
        return (sum(1 for x in rs if x > 0) / len(rs) * 100) if rs else None

    return {
        "n_strat": n_s, "n_ext": n_e, "still_held": still_held,
        "headline": headline, "cohort": cohort, "blended": blended,
        "wr_strat": wr(strat_rets), "wr_blended": wr(allr),
        "ext_share": n_e / (n_s + n_e) * 100 if (n_s + n_e) else 0.0,
    }


def run(name, preset, exit_kw, stock_data):
    sl, md = exit_kw["stop_loss_pct"], exit_kw["max_hold_days"]
    print(f"\n▶ {name}  ｜ 出場 s2"
          + (f"+止損{sl}%" if sl else "") + (f"+時間{md}日" if md else ""))
    t0 = time.time()
    last = [0.0]
    def cb(f, tot, tk):
        now = time.time()
        if now - last[0] > 1.0:
            print(f"    fold {f}/{tot}  {tk}", end="\r", flush=True); last[0] = now
    wf = run_portfolio_walk_forward(
        stock_data, buy_sigs=preset["buy"], sell_sigs=preset["sell"],
        is_months=12, oos_months=6, trade_size=100_000,
        slippage=SLIPPAGE_PCT, commission_pct=COMMISSION_PCT,
        stop_loss_pct=sl, max_hold_days=md,
        min_hold_days=preset.get("min_hold_days"),
        track_extended=True, use_pit_universe=True, progress_cb=cb,
    )
    print(" " * 80, end="\r")
    a = analyze(wf)
    print(f"  ✓ {time.time()-t0:.1f}s")
    fmt = lambda x, s="%": f"{x:+.2f}{s}" if x is not None else "N/A"
    print(f"    in-window 策略單 : {fmt(a['headline'])}  ({a['n_strat']} 筆, 勝率 {a['wr_strat']:.1f}%)")
    print(f"    邊界 cohort 延伸 : {fmt(a['cohort'])}  ({a['n_ext']} 筆"
          + (f", 仍持倉 {a['still_held']}" if a['still_held'] else "") + ")")
    print(f"    ★混合真實回報   : {fmt(a['blended'])}  "
          f"(合計 {a['n_strat']+a['n_ext']} 筆, 勝率 {a['wr_blended']:.1f}%, 邊界佔 {a['ext_share']:.0f}%)")
    return {"variant": name, **a}


def main():
    t_start = time.time()
    print("═" * 92)
    print("  b17 ROC超跌反彈：混合真實回報（in-window 策略單 + 邊界延伸單，逐筆加權）")
    print("  目的：剝離 cohort 選擇偏誤，看 b17 誠實口徑的整體回報")
    print("═" * 92)

    preset = ACTIVE_PRESETS.get(TARGET)
    if preset is None:
        print(f"❌ 找不到 {TARGET}")
        return 1

    tickers = load_stocks()
    print(f"\nstocks.txt {len(tickers)} 隻；載入 EODHD…")
    sd, skipped = build_stock_data(tickers)
    print(f"已載入 {len(sd)} 隻（跳過 {skipped}）")
    if len(sd) < 10:
        print("❌ 可用股票太少")
        return 1

    rows = [run(v, preset, kw, sd) for v, kw in VARIANTS.items()]

    print("\n" + "═" * 92)
    print("  b17 混合真實回報 — 止損 vs 時間 收斂對照")
    print("═" * 92)
    print(f"{'出場':<14}{'in-window':>12}{'邊界cohort':>12}{'★混合真實':>12}"
          f"{'合計筆數':>10}{'混合勝率':>10}")
    print("─" * 92)
    for r in rows:
        f = lambda x: f"{x:+.2f}%" if x is not None else "N/A"
        print(f"{r['variant']:<14}{f(r['headline']):>12}{f(r['cohort']):>12}"
              f"{f(r['blended']):>12}{r['n_strat']+r['n_ext']:>10}"
              f"{r['wr_blended']:>9.1f}%")
    print("═" * 92)

    blends = [r["blended"] for r in rows if r["blended"] is not None]
    if len(blends) == 2:
        spread = abs(blends[0] - blends[1])
        avg_b = sum(blends) / 2
        print(f"\n兩版混合真實回報差距 {spread:.2f}pp，平均 {avg_b:+.2f}%。")
        if avg_b < 2.0:
            print("→ 混合真實回報落在打平帶（< +2%）：+2.64% 確為 cohort 選擇偏誤，")
            print("  b17 誠實口徑不過實盤門檻 → 支持路線 A（與其他一起降級）。")
        else:
            print("→ 混合真實回報站上 +2%：b17 可能有可保留的真實 alpha，需再議。")
        if spread > 2.0:
            print(f"⚠️ 兩版差距 {spread:.2f}pp 偏大：b17 對出場規則敏感，實盤出場選擇會顯著影響結果。")

    print(f"\n總耗時 {time.time()-t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

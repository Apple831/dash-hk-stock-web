"""
test_b17_exit_grid.py -- b17 救援：出場規則格點測試（V22.2 Phase 5 候選）

═══════════════════════════════════════════════════════════════════
背景（接 HANDOVER28 §5.3 b17 救援研究）
═══════════════════════════════════════════════════════════════════
  Phase 4 關鍵診斷：
    • b17 時間出場(T20) in-window：+1.40% / 勝率 49.8%（全場最健康）
    • b17 止損出場(stop10) in-window：+0.14%
    → 緊止損(10%)在急跌股上是雜訊區，把會反彈的單掃成實虧（whipsaw）。
    → b17 的問題不是「沒止損」，是「止損太近」+「T20 尾段死錢攤薄」。

  本腳本假設（預先宣告，跑完不准搬門檻）：
    H1 縮短時間窗：超跌反彈多在 5-15 交易日內完成，T10/T15 砍掉死錢尾段。
    H2 寬災難止損：15-20% 只砍真災難左尾，不碰正常回檔（避開 stop10 whipsaw）。
    H3 止盈 12%（對照組）：鎖定沒碰到布林上軌的反彈；風險是截斷右尾。

═══════════════════════════════════════════════════════════════════
裁決標準（唯一指標：混合真實回報，HANDOVER28 §3.1/§3.2）
═══════════════════════════════════════════════════════════════════
  混合真實回報 = mean( 所有 fold 的 oos_trades 回報% ∪ 已平倉延伸單回報% )
  （oos_trades = 策略出場單，強制平倉已被引擎排除；兩群逐筆等權。）

  過關門檻（全部滿足才有資格進復活程序）：
    1. 混合真實回報 ≥ +2.0%
    2. 有效 Fold 正回報比率 ≥ 60%
    3. 參數高原：勝出格的相鄰格同向（尖點 = 運氣，不過關）
    4. 延伸後仍持倉(未解決)比例不可過高（真實結果不可知的單越少越好）

  ⚠️ 防過擬合：本輪只測 b17 一支 × 7 格。不准擴成多策略掃描。

═══════════════════════════════════════════════════════════════════
使用方法
═══════════════════════════════════════════════════════════════════
  cd 專案根目錄
  python scripts/test_b17_exit_grid.py

  設定對齊 Phase 3/4：IS12/OOS6、5年 EODHD、PIT ON、MIN_HOLD 5、
  commission 0.0026 / slippage 0.001、trade_size 100k、非複利。
  G_T20 為 Phase 4 時間版複現錨點（混合應 ≈ +0.97%，偏差大代表環境未對齊）。
"""
import os
import sys
import time

# 修正 Windows console 印 emoji（cp950）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

from data import load_stocks
from historical_universe import load_eodhd_prices
from walk_forward import run_portfolio_walk_forward
from config import COMMISSION_PCT, SLIPPAGE_PCT


# ══════════════════════════════════════════════════════════════════
# 策略定義（不碰 config.py；b17 buy/sell tuple 與 ACTIVE 一字不差）
# ══════════════════════════════════════════════════════════════════
def make_buy(*active) -> tuple:
    idx = {f"b{i+1}": i for i in range(19)}
    t = [False] * 19
    for a in active:
        t[idx[a]] = True
    return tuple(t)


BUY_B17 = make_buy("b17")
SELL_S2 = (False, True, False, False, False, False, False, False)   # s2 布林上軌
MIN_HOLD = 5            # 對齊 preset / Phase 3 baseline 對齊修正
IS_MONTHS = 12
OOS_MONTHS = 6
TRADE_SIZE = 100_000

# ── 格點（7 格，預先宣告，不准中途加格）─────────────────────────────
# 結構：(名稱, dict(stop_loss_pct / take_profit_pct / max_hold_days))
# 所有格都保留 s2（右尾保留器）。
GRID = [
    ("T20 基準(Phase4錨點)",  dict(max_hold_days=20)),
    ("T10",                   dict(max_hold_days=10)),
    ("T15",                   dict(max_hold_days=15)),
    ("T15+災難止損15",        dict(max_hold_days=15, stop_loss_pct=15)),
    ("T20+災難止損15",        dict(max_hold_days=20, stop_loss_pct=15)),
    ("T20+災難止損20",        dict(max_hold_days=20, stop_loss_pct=20)),
    ("T15+止盈12(對照)",      dict(max_hold_days=15, take_profit_pct=12)),
]

PASS_BLENDED = 2.0      # 混合真實回報過關門檻（%）
PASS_POS_RATE = 60.0    # 有效 Fold 正回報比率門檻（%）


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
# 彙總：混合真實回報 + 診斷
# ══════════════════════════════════════════════════════════════════
def summarize(wf_results: list) -> dict:
    """逐筆等權混合：oos_trades ∪ 已平倉延伸單。並回傳兩群分別的診斷。"""
    in_rets, ext_rets = [], []
    forced_total, still_held = 0, 0
    pos_folds, valid_folds = 0, 0
    hold_days = []

    for r in wf_results:
        forced_total += r.get("forced_exit_count", 0)
        for t in r.get("oos_trades", []):
            in_rets.append(float(t["回報%"]))
            hold_days.append(t.get("持倉天數", 0))
        for t in r.get("oos_extended_trades", []):
            if t.get("_still_held_at_end", False):
                still_held += 1
                continue
            ext_rets.append(float(t["回報%"]))
            hold_days.append(t.get("持倉天數", 0))
        if r.get("valid_oos"):
            valid_folds += 1
            om = r.get("oos_metrics") or {}
            if om.get("平均每筆回報%", 0.0) > 0:
                pos_folds += 1

    all_rets = in_rets + ext_rets
    n = len(all_rets)

    def _avg(xs):
        return sum(xs) / len(xs) if xs else None

    def _wr(xs):
        return sum(1 for x in xs if x > 0) / len(xs) * 100 if xs else None

    return {
        "blended":      _avg(all_rets),
        "blended_wr":   _wr(all_rets),
        "n_total":      n,
        "in_avg":       _avg(in_rets),
        "in_n":         len(in_rets),
        "ext_avg":      _avg(ext_rets),
        "ext_n":        len(ext_rets),
        "forced":       forced_total,
        "still_held":   still_held,
        "pos_folds":    pos_folds,
        "valid_folds":  valid_folds,
        "pos_rate":     (pos_folds / valid_folds * 100) if valid_folds else 0.0,
        "avg_hold":     _avg(hold_days),
    }


def verdict(s: dict) -> str:
    if s["blended"] is None or s["n_total"] < 30:
        return "⚪ 樣本不足"
    if s["blended"] >= PASS_BLENDED and s["pos_rate"] >= PASS_POS_RATE:
        return "🟢 候選過關(待高原檢查)"
    if s["blended"] >= 1.0:
        return "🟡 接近但不過"
    if s["blended"] >= 0:
        return "🟠 打平"
    return "🔴 負"


def _fmt(v, fmt="{:+.2f}%"):
    return fmt.format(v) if v is not None else "N/A"


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run_one(name: str, params: dict, stock_data: dict) -> dict:
    print(f"\n────────────────────────────────────────")
    print(f"▶ b17 × {name}  params={params}")
    t0 = time.time()

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
        stop_loss_pct=params.get("stop_loss_pct"),
        take_profit_pct=params.get("take_profit_pct"),
        max_hold_days=params.get("max_hold_days"),
        track_extended=True,        # 混合真實回報必需（延伸追蹤是裁決資料源）
        use_pit_universe=True,      # PIT ON（對齊 Phase 3/4）
        progress_cb=cb,
    )
    print(" " * 80, end="\r")

    s = summarize(wf)
    g = verdict(s)
    elapsed = time.time() - t0

    print(f"  ✓ {elapsed:.1f}s")
    print(f"  混合真實回報 : {_fmt(s['blended'])}  （勝率 {_fmt(s['blended_wr'], '{:.1f}%')}，{s['n_total']} 筆）")
    print(f"  in-window    : {_fmt(s['in_avg'])}（{s['in_n']} 筆）")
    print(f"  延伸 cohort  : {_fmt(s['ext_avg'])}（{s['ext_n']} 筆已平倉；仍持倉 {s['still_held']}）")
    print(f"  強制平倉     : {s['forced']} 筆 ｜ 正Fold {s['pos_folds']}/{s['valid_folds']}"
          f"（{s['pos_rate']:.0f}%）｜ 平均持倉 {_fmt(s['avg_hold'], '{:.1f}')} 天")
    print(f"  判定         : {g}")
    return {"name": name, "summary": s, "verdict": g}


def print_table(rows: list):
    print("\n" + "═" * 100)
    print("  b17 出場規則格點 — 混合真實回報對比（門檻：≥ +2.0% 且 正Fold ≥ 60% 且 參數高原）")
    print("═" * 100)
    print(f"{'配置':<22} {'混合%':>8} {'勝率%':>7} {'總筆':>6} {'inW%':>8} "
          f"{'ext%':>8} {'未解決':>6} {'正Fold':>8} {'持倉天':>7}  判定")
    print("─" * 100)
    for r in rows:
        if r is None:
            continue
        s = r["summary"]
        print(f"{r['name']:<22} "
              f"{_fmt(s['blended'], '{:+.2f}'):>8} "
              f"{_fmt(s['blended_wr'], '{:.1f}'):>7} "
              f"{s['n_total']:>6} "
              f"{_fmt(s['in_avg'], '{:+.2f}'):>8} "
              f"{_fmt(s['ext_avg'], '{:+.2f}'):>8} "
              f"{s['still_held']:>6} "
              f"{s['pos_folds']}/{s['valid_folds']:<5} "
              f"{_fmt(s['avg_hold'], '{:.1f}'):>7}  {r['verdict']}")
    print("═" * 100)
    print("\n💡 判讀提醒：")
    print("   • T20 基準的混合值應 ≈ +0.97%（Phase 4 錨點）；偏差大先查環境對齊，不要直接信本輪數字。")
    print("   • 過關格必須有「參數高原」：相鄰格（如 T15 過 → 看 T10/T20）同向才算數，尖點=運氣。")
    print("   • 含止損的勝出版本要注意帳本實作偏差（low 偵測 + T+1 開盤平倉）；時間出場無此問題。")
    print("   • 全部不過 = 接受「b17 進場 alpha 上限 ~+1.4%，扣成本不足實盤」，結案不硬掃。")


def main() -> int:
    t_start = time.time()
    print("═" * 100)
    print("  b17 救援：出場規則格點（PIT WF 12+6，5y，MIN5，s2 保留，7 格預宣告）")
    print("═" * 100)

    tickers = load_stocks()
    print(f"\nstocks.txt 共 {len(tickers)} 隻；載入 EODHD…")
    stock_data, skipped = build_stock_data(tickers)
    print(f"已載入 {len(stock_data)} 隻（跳過 {skipped} 隻數據不足）")

    if len(stock_data) < 10:
        print("❌ 可用股票太少（<10），中止。請確認 data/eodhd_prices/ 是否存在。")
        return 1

    rows = []
    for name, params in GRID:
        rows.append(run_one(name, params, stock_data))

    print_table(rows)

    passed = [r for r in rows if r and r["verdict"].startswith("🟢")]
    if passed:
        print(f"\n🟢 通過數字門檻的格 {len(passed)} 個（仍需人工做高原檢查）：")
        for r in passed:
            print(f"   • {r['name']}  混合 {_fmt(r['summary']['blended'])}")
        print("\n   下一步：把整張表貼回對話 → 高原檢查 → 通過才走復活程序")
        print("   （LIVE_PRESET_KEYS 加 key + 協調帳本 reset；config.py 由 Claude 整檔重寫）。")
    else:
        print("\n⚠️ 本輪無格通過 +2.0% 門檻。把整張表貼回對話，先確認 T20 錨點對齊，")
        print("   再決定：(a) 結案接受 b17 alpha 太薄，或 (b) 是否還有非掃格的結構性方向。")

    elapsed = time.time() - t_start
    print(f"\n總耗時：{elapsed:.1f} 秒 ({elapsed/60:.1f} 分鐘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

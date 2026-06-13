"""
test_exit_rules_wf.py -- V22.2 Phase 3：止損 / 時間出場 對照（救援抓底策略 alpha 驗證）

═══════════════════════════════════════════════════════════════════
背景（接 HANDOVER27）
═══════════════════════════════════════════════════════════════════
  Phase 1：全 11 支 ACTIVE 延伸追蹤體檢 → 11/11 疑似 survivorship
           （真實出場% 比頂部 OOS 低 −10.84 ~ −21.32 pp）。
  Phase 2：b13 + s2+s5 對照 → 沒救回（−5.55% → −6.52%，反而更差）。
           否證了「s2 出場太慢是元兇」——s2、s5 都是「獲利了結型出場」
           （漲上去才觸發），對「買了不漲」的長抱輸家完全無能為力。

  核心洞察：要把被 Fold 邊界強制平倉的長抱輸家「真正拉出來」，
           缺的是【止損型 stop_loss_pct】或【時間型 max_hold_days】出場——
           這兩種會在「買了不漲」時觸發，s2 / s5 不會。

  Phase 3 目的：用止損 / 時間出場測 b13 / b12+b15 的進場到底有沒有 alpha。
              這是降級前必跑的最後一關，避免誤殺真有 alpha 的進場。

  卡點：WF 自訂頁沒有 max_hold_days 輸入欄位（只有止損% / 止盈% / 同時持倉上限）。
       run_portfolio_walk_forward 本身支援該參數，所以用本 script 帶參數跑。

═══════════════════════════════════════════════════════════════════
測試矩陣（統一設定：投資組合 / PIT ON / 5年 / IS12 OOS6 / 0.26% / 0.1%）
═══════════════════════════════════════════════════════════════════
  每支策略跑 3 個出場變體：
    • s2          ：布林上軌出場（baseline，重現 Phase 1/2 −5.55% 那一欄）
    • s2 + 時間20 ：max_hold_days=20（超時砍倉，會接住長抱輸家）
    • s2 + 止損10 ：stop_loss_pct=10（跌 10% 砍倉，會接住下跌輸家）

  策略：b13 縮量反轉、b12+b15 資金流向+下影線（主力）

  ⚠️ min_hold_days：預設 None（對齊 WF 自訂模式；HANDOVER27 第四節指定）。
     本測試測「砍長抱輸家」，min_hold 影響小（5 天 << 65 天長抱），可接受。
     要嚴格對齊原 preset 的 MIN5，把下方 MIN_HOLD_DAYS 改成 5 再跑一輪即可。

═══════════════════════════════════════════════════════════════════
判讀的診斷簽名（HANDOVER27 第四節）
═══════════════════════════════════════════════════════════════════
  救得回（進場 alpha 真，需止損/時間保護）：
    強制平倉數大幅下降（被時間/止損接住）
    + 真實出場% 收進 −3% 門檻內或轉正
    + 平均持倉從 ~65 天掉到 ~20 天
  救不回：
    頂部 OOS 垮 + 真實仍負 → 進場根本無 alpha，長抱單是真虧 → 確認降級
    頂部 OOS 撐住 + 真實回正 → alpha 真、出場可救

═══════════════════════════════════════════════════════════════════
使用方法
═══════════════════════════════════════════════════════════════════
  cd 專案根目錄
  python scripts/test_exit_rules_wf.py

  需要 data/eodhd_prices/*.json（PIT 股票池）。
  預設跑 2 策略 × 3 變體 = 6 跑。太慢可在 RUN_LIST 註解掉部分。
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
from walk_forward import run_portfolio_walk_forward, _extended_summary
from config import (
    COMMISSION_PCT,
    SLIPPAGE_PCT,
)

# ══════════════════════════════════════════════════════════════════
# 全域設定（要改 min_hold 對齊原 preset MIN5 就改這裡）
# ══════════════════════════════════════════════════════════════════
MIN_HOLD_DAYS = 5      # 5=對齊 ACTIVE preset（cooldown 自動沿用成 5，與 Phase 1 同口徑）
                       # None=WF 自訂模式（cooldown=0 不冷卻 → 重複摸底同股，baseline 更兇）
SURVIVOR_GAP_THRESHOLD = -3.0   # 真實出場% − 頂部OOS% < 此值 → 疑 survivorship（偵測門檻，非獲利門檻）


# ══════════════════════════════════════════════════════════════════
# 策略定義（不碰 config.py；買賣 tuple 直接寫在腳本內）
# ══════════════════════════════════════════════════════════════════
def make_buy(*active) -> tuple:
    """active=('b12','b15') → 18-tuple，對應位置 True，其他 False。"""
    idx = {f"b{i+1}": i for i in range(18)}
    t = [False] * 18
    for a in active:
        t[idx[a]] = True
    return tuple(t)


SELL_S2    = (False, True, False, False, False, False, False, False)  # s2 布林上軌出場
SELL_S2_S5 = (False, True, False, False, True,  False, False, False)  # s2 + s5(RSI>70) OR 出場

# 策略基底（買入訊號）
STRATEGIES = {
    "b13 縮量反轉": make_buy("b13"),
    "b12+b15 資金流向+下影線(主力)": make_buy("b12", "b15"),
}

# 出場變體（每支策略都跑這 4 個 → 湊齊四欄對照）
#   s2、s2+s5 都是「獲利了結型出場」（漲才觸發，對買了不漲無效）→ 作對照/控制組
#   時間、止損 是「會在買了不漲時觸發」的出場 → 真正的救援測試
EXIT_VARIANTS = {
    "s2 (baseline)":  {"sell": SELL_S2,    "stop_loss_pct": None, "max_hold_days": None},
    "s2 + s5":        {"sell": SELL_S2_S5, "stop_loss_pct": None, "max_hold_days": None},
    "s2 + 時間20":    {"sell": SELL_S2,    "stop_loss_pct": None, "max_hold_days": 20},
    "s2 + 止損10":    {"sell": SELL_S2,    "stop_loss_pct": 10,   "max_hold_days": None},
}

# 預設跑哪些（(策略名, 變體名)；太慢可註解掉部分）
RUN_LIST = [
    ("b13 縮量反轉",                  "s2 (baseline)"),
    ("b13 縮量反轉",                  "s2 + s5"),
    ("b13 縮量反轉",                  "s2 + 時間20"),
    ("b13 縮量反轉",                  "s2 + 止損10"),
    ("b12+b15 資金流向+下影線(主力)", "s2 (baseline)"),
    ("b12+b15 資金流向+下影線(主力)", "s2 + s5"),
    ("b12+b15 資金流向+下影線(主力)", "s2 + 時間20"),
    ("b12+b15 資金流向+下影線(主力)", "s2 + 止損10"),
]

# Phase 1 baseline 對照（HANDOVER27 第二節，s2 / 自訂模式）
PHASE1_BASELINE = {
    "b13 縮量反轉":                  {"oos": 7.28, "true": -5.55, "forced": 296, "days": 65},
    "b12+b15 資金流向+下影線(主力)": {"oos": 7.25, "true": -3.59, "forced": 51,  "days": 68},
}


# ══════════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════════
def build_stock_data(tickers: list):
    """載入全部可用 EODHD（提供 PIT 模式的 ref_df 時間軸 + fallback）。"""
    stock_data = {}
    skipped = 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        stock_data[tkr] = df
    return stock_data, skipped


def summarize_wf(wf_results: list) -> dict:
    """頂部 OOS 摘要（與 test_pattern_combos_wf.py 一致）
       + 全程強制平倉 + 延伸追蹤彙總（Phase 3 核心）。"""
    if not wf_results:
        return {
            "avg_oos": None, "oos_pos": 0, "valid_folds": 0, "total_folds": 0,
            "fold7_n": None, "total_forced": 0,
            "ext_closed": 0, "ext_still": 0, "ext_avg_return": None,
            "ext_win_rate": None, "ext_avg_days": None, "gap": None,
        }

    total_folds = len(wf_results)
    valid = [r for r in wf_results if r.get("valid_oos")]
    valid_folds = len(valid)

    oos_rets = [r["oos_metrics"].get("平均每筆回報%", 0.0) for r in valid if r["oos_metrics"]]
    avg_oos = sum(oos_rets) / len(oos_rets) if oos_rets else None
    oos_pos = sum(1 for r in valid if r["oos_metrics"].get("平均每筆回報%", 0.0) > 0)

    # 最後一個 Fold 的 OOS 樣本數（樣本薄虛高檢查）
    fold7_n = wf_results[-1].get("oos_trade_count", 0) if wf_results else None

    # ★延伸追蹤（反 survivorship 核心）：把全部 Fold 邊界強制平倉的單撈回來續持★
    total_forced = sum(r.get("forced_exit_count", 0) for r in wf_results)
    all_extended = [t for r in wf_results for t in r.get("oos_extended_trades", [])]
    ext = _extended_summary(all_extended)

    ext_closed     = ext.get("closed", 0)
    ext_still      = ext.get("still_held", 0)
    ext_avg_return = ext.get("avg_return")   # 真實出場%
    ext_win_rate   = ext.get("win_rate")     # 真實勝率
    ext_avg_days   = ext.get("avg_days")      # 平均持倉

    # 差距 = 真實出場% − 頂部OOS%（< −3 → 疑 survivorship）
    gap = None
    if ext_avg_return is not None and avg_oos is not None:
        gap = ext_avg_return - avg_oos

    return {
        "avg_oos": avg_oos, "oos_pos": oos_pos, "valid_folds": valid_folds,
        "total_folds": total_folds, "fold7_n": fold7_n,
        "total_forced": total_forced,
        "ext_closed": ext_closed, "ext_still": ext_still,
        "ext_avg_return": ext_avg_return, "ext_win_rate": ext_win_rate,
        "ext_avg_days": ext_avg_days, "gap": gap,
    }


def gatekeeper(s: dict) -> str:
    """守門員判定：真實出場% − 頂部OOS% 的差距門檻（HANDOVER 鐵則）。"""
    gap = s["gap"]
    if gap is None:
        if s["total_forced"] == 0:
            return "⚪ 無強制平倉"
        return "⚪ 無延伸交易可判"
    if gap < SURVIVOR_GAP_THRESHOLD:
        return f"🔴 疑survivorship({gap:+.1f}pp)"
    if gap < 0:
        return f"🟡 尚可({gap:+.1f}pp)"
    return f"🟢 紮實({gap:+.1f}pp)"


def run_one(strat_name: str, buy: tuple, variant_name: str, exit_kw: dict,
            stock_data: dict) -> dict:
    print(f"\n────────────────────────────────────────")
    print(f"▶ {strat_name}  ｜  {variant_name}")
    sl = exit_kw.get("stop_loss_pct")
    md = exit_kw.get("max_hold_days")
    sell = exit_kw.get("sell", SELL_S2)
    sell_desc = "s2 布林上軌" + (" + s5(RSI>70)" if sell[4] else "")
    print(f"  出場：{sell_desc}"
          + (f" + 止損 {sl}%" if sl else "")
          + (f" + 超時 {md} 日" if md else "")
          + f"  ｜ min_hold={MIN_HOLD_DAYS}")
    t0 = time.time()

    last_print = [0.0]
    def cb(fold, total_folds, ticker):
        now = time.time()
        if now - last_print[0] > 1.0:
            print(f"    fold {fold}/{total_folds}  {ticker}", end="\r", flush=True)
            last_print[0] = now

    wf = run_portfolio_walk_forward(
        stock_data,
        buy_sigs=buy,
        sell_sigs=sell,
        is_months=12,
        oos_months=6,
        trade_size=100_000,
        slippage=SLIPPAGE_PCT,
        commission_pct=COMMISSION_PCT,
        stop_loss_pct=exit_kw.get("stop_loss_pct"),
        max_hold_days=exit_kw.get("max_hold_days"),
        min_hold_days=MIN_HOLD_DAYS,
        track_extended=True,          # ★Phase 3 核心：必須開，否則拿不到真實出場%★
        use_pit_universe=True,        # ★PIT 股票池修正生存者偏差★
        progress_cb=cb,
    )
    print(" " * 80, end="\r")

    s = summarize_wf(wf)
    g = gatekeeper(s)
    elapsed = time.time() - t0

    oos_str   = f"{s['avg_oos']:+.2f}%"        if s["avg_oos"]        is not None else "N/A"
    true_str  = f"{s['ext_avg_return']:+.2f}%" if s["ext_avg_return"] is not None else "N/A"
    gap_str   = f"{s['gap']:+.2f}pp"           if s["gap"]            is not None else "N/A"
    wr_str    = f"{s['ext_win_rate']:.1f}%"    if s["ext_win_rate"]   is not None else "N/A"
    days_str  = f"{s['ext_avg_days']:.0f}天"   if s["ext_avg_days"]   is not None else "N/A"

    print(f"  ✓ {elapsed:.1f}s")
    print(f"    頂部OOS {oos_str}  →  真實出場 {true_str}  (差距 {gap_str})")
    print(f"    真實勝率 {wr_str}  平均持倉 {days_str}  "
          f"強制平倉 {s['total_forced']}  真實出場數 {s['ext_closed']}"
          + (f"  仍持倉 {s['ext_still']}" if s["ext_still"] else ""))
    print(f"    守門員：{g}")

    return {"strat": strat_name, "variant": variant_name, "summary": s, "grade": g}


def print_table(rows: list):
    print("\n" + "═" * 110)
    print("  Phase 3：止損 / 時間出場 對照 — 延伸追蹤總表（PIT WF 12+6, $100k, PIT ON）")
    print("═" * 110)
    print(f"{'策略 / 出場':<34} {'頂部OOS':>9} {'真實出場':>9} {'差距':>9} "
          f"{'真實勝率':>9} {'平均持倉':>9} {'強制平倉':>9} {'真實數':>8} {'守門員':>20}")
    print("─" * 110)
    last_strat = None
    for r in rows:
        if r is None:
            continue
        if last_strat is not None and r["strat"] != last_strat:
            print("─" * 110)
        last_strat = r["strat"]
        s = r["summary"]
        label = f"{r['strat'][:14]} ｜ {r['variant']}"
        if len(label) > 33:
            label = label[:32] + "…"
        oos_str  = f"{s['avg_oos']:+.2f}"        if s["avg_oos"]        is not None else "N/A"
        true_str = f"{s['ext_avg_return']:+.2f}" if s["ext_avg_return"] is not None else "N/A"
        gap_str  = f"{s['gap']:+.2f}"            if s["gap"]            is not None else "N/A"
        wr_str   = f"{s['ext_win_rate']:.1f}"    if s["ext_win_rate"]   is not None else "N/A"
        days_str = f"{s['ext_avg_days']:.0f}"    if s["ext_avg_days"]   is not None else "N/A"
        print(f"{label:<34} {oos_str:>9} {true_str:>9} {gap_str:>9} "
              f"{wr_str:>9} {days_str:>9} {s['total_forced']:>9} {s['ext_closed']:>8} "
              f"{r['grade']:>20}")
    print("═" * 110)


def print_diagnosis(rows: list):
    """逐策略做「救得回 / 救不回」診斷（HANDOVER27 第四節簽名）。"""
    print("\n" + "═" * 110)
    print("  Phase 3 診斷：進場 alpha 真偽（每支策略 baseline vs 止損/時間）")
    print("═" * 110)

    by_strat = {}
    for r in rows:
        if r is None:
            continue
        by_strat.setdefault(r["strat"], {})[r["variant"]] = r["summary"]

    for strat, variants in by_strat.items():
        base = variants.get("s2 (baseline)")
        print(f"\n▶ {strat}")
        ph1 = PHASE1_BASELINE.get(strat)
        if ph1 and base:
            print(f"  Phase 1 對照（s2 自訂）：頂部 +{ph1['oos']:.2f}% / 真實 {ph1['true']:+.2f}% "
                  f"/ 強制 {ph1['forced']} / 持倉 {ph1['days']}天")
            print(f"  本輪 baseline：       頂部 {fmt(base['avg_oos'],'%')} / "
                  f"真實 {fmt(base['ext_avg_return'],'%')} / 強制 {base['total_forced']} / "
                  f"持倉 {fmt(base['ext_avg_days'],'天')}")

        for vname in ("s2 + 時間20", "s2 + 止損10"):
            v = variants.get(vname)
            if not v or not base:
                continue
            verdict = diagnose_variant(base, v)
            print(f"  ── {vname}：{verdict}")

    print("\n" + "═" * 110)
    print("💡 收斂判讀：")
    print("   • 救得回 = 強制平倉大幅↓ + 真實出場% 收進 −3% 內或轉正 + 平均持倉 65→~20")
    print("            → 進場 alpha 真，需止損/時間保護 → 全 ACTIVE 改出場規則方向成立。")
    print("   • 救不回(無alpha) = 頂部OOS 垮 + 真實仍負 → 長抱單是真虧 → 確認降級（路線 B）。")
    print("   • 救不回(可救)    = 頂部OOS 撐住 + 真實回正 → alpha 真、出場可救。")
    print("   下一步：把本表貼回對話，我做 s2 / s2+s5 / s2+時間 / s2+止損 四欄對照，定降級幅度。")


def diagnose_variant(base: dict, v: dict) -> str:
    """單一變體 vs baseline 的救援診斷。"""
    parts = []

    # 1) 強制平倉變化
    bf, vf = base["total_forced"], v["total_forced"]
    if bf > 0:
        drop = (bf - vf) / bf * 100
        parts.append(f"強制平倉 {bf}→{vf}({drop:+.0f}%)")
    else:
        parts.append(f"強制平倉 {bf}→{vf}")

    # 2) 真實出場%（這變體本身的真實出場，已含止損/時間接住的單）
    vt = v["ext_avg_return"]
    vo = v["avg_oos"]
    if vt is not None:
        parts.append(f"真實出場 {vt:+.2f}%")
    if vo is not None:
        parts.append(f"頂部OOS {vo:+.2f}%")

    # 3) 平均持倉
    vd = v["ext_avg_days"]
    if vd is not None:
        parts.append(f"持倉 {vd:.0f}天")

    # 綜合判定
    forced_dropped = (bf > 0 and vf <= bf * 0.5)              # 強制平倉砍半以上
    true_ok = (vt is not None and vt >= SURVIVOR_GAP_THRESHOLD)  # 真實收進 −3% 內或轉正
    oos_holds = (vo is not None and vo > 0)                    # 頂部仍正
    days_short = (vd is not None and vd <= 30)                 # 持倉明顯縮短

    if forced_dropped and true_ok and days_short:
        tag = "✅ 救得回（進場 alpha 真，需止損/時間保護）"
    elif (vo is not None and vo <= 0) and (vt is not None and vt < SURVIVOR_GAP_THRESHOLD):
        tag = "🔴 救不回·無 alpha（頂部垮+真實仍負 → 確認降級）"
    elif oos_holds and true_ok:
        tag = "🟢 alpha 真、出場可救（頂部撐住+真實回正）"
    else:
        tag = "🟡 部分改善（需與四欄對照表合看）"

    return tag + "  ｜ " + "  ".join(parts)


def fmt(x, suffix=""):
    return f"{x:+.2f}{suffix}" if isinstance(x, (int, float)) else "N/A"


def main() -> int:
    t_start = time.time()
    print("═" * 110)
    print("  V22.2 Phase 3：止損 / 時間出場 對照（救援抓底策略 alpha 驗證）")
    print(f"  策略 b13 / b12+b15  ×  出場 s2 / s2+時間20 / s2+止損10")
    print(f"  設定：投資組合 / PIT ON / 5年 / IS12 OOS6 / "
          f"手續費{COMMISSION_PCT} / 滑點{SLIPPAGE_PCT} / min_hold={MIN_HOLD_DAYS}")
    print("═" * 110)

    tickers = load_stocks()
    print(f"\nstocks.txt 共 {len(tickers)} 隻；載入 EODHD 提供時間軸…")
    stock_data, skipped = build_stock_data(tickers)
    print(f"已載入 {len(stock_data)} 隻（跳過 {skipped} 隻數據不足）")

    if len(stock_data) < 10:
        print("❌ 可用股票太少（<10），中止。請確認 data/eodhd_prices/ 是否存在。")
        return 1

    rows = []
    for strat_name, variant_name in RUN_LIST:
        buy = STRATEGIES.get(strat_name)
        exit_kw = EXIT_VARIANTS.get(variant_name)
        if buy is None or exit_kw is None:
            print(f"  ⚠️ ({strat_name}, {variant_name}) 未定義，跳過")
            continue
        rows.append(run_one(strat_name, buy, variant_name, exit_kw, stock_data))

    print_table(rows)
    print_diagnosis(rows)

    elapsed = time.time() - t_start
    print(f"\n總耗時：{elapsed:.1f} 秒 ({elapsed/60:.1f} 分鐘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
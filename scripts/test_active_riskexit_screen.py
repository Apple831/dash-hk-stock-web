"""
test_active_riskexit_screen.py -- V22.2 Phase 4：全 11 支 ACTIVE 風險出場篩選

═══════════════════════════════════════════════════════════════════
背景（接 HANDOVER27 + Phase 3）
═══════════════════════════════════════════════════════════════════
  Phase 1：全 11 支 ACTIVE 純 s2 出場 → 11/11 疑 survivorship（頂部 OOS 灌水 −10~−21pp）。
  Phase 2：b13 + s2+s5 → 沒救（s5 是另一個「漲才出」的獲利了結出場）。
  Phase 3：b13 / b12+b15 配【止損 stop10 / 時間 max_hold20】→ survivorship 被修掉
           （差距從 −17pp 收進 −3.7pp 內、強制平倉砍半、持倉 72→20-35 天），
           但「修好」露出的真相是「打平 ~ 微正」（b13+止損 +0.82%、b12+b15+時間 +0.29%）。
           ★複現確認：s2 與 s2+s5 兩支數字幾乎/完全相同 → s5 對抓底訊號零幫助★。

  Phase 4 目的（路線 B「先搶救再降」）：
    把出場換成風險出場後，對全 11 支 ACTIVE 掃一輪，看有沒有哪支在誠實口徑
    （真實出場% / 延伸追蹤）下站上「明顯正值」（不只打平），避免誤殺真有 alpha 的進場。
    篩選器用【止損 10%】——Phase 3 顯示它在 b13 給出唯一正差距、口徑最誠實。
    通過的少數再用時間出場細測（把 RISK_EXIT 切到 time 再跑一次）。

═══════════════════════════════════════════════════════════════════
判讀（benchmark 已轉真實出場%，頂部 OOS 不再採信）
═══════════════════════════════════════════════════════════════════
  止損清乾淨後，頂部OOS 與真實出場% 會收斂（差距→0）——此時兩者一致，可互相佐證。
  篩選分級（真實出場% 為主，頂部OOS 佐證）：
    🟢 保留候選 ：真實出場% ≥ KEEP_THRESHOLD（明顯正、值得保留實盤觀察）
    🟡 打平觀察 ：0 ≤ 真實出場% < KEEP_THRESHOLD（噪音內，傾向降級）
    🔴 確認降級 ：真實出場% < 0（風險出場後仍負，進場無 alpha）
    ⚠️ 未清乾淨 ：差距仍 < −3pp（止損沒接住，極少見，需查）

═══════════════════════════════════════════════════════════════════
使用方法
═══════════════════════════════════════════════════════════════════
  cd 專案根目錄
  python scripts/test_active_riskexit_screen.py

  預設掃全 11 支 ACTIVE × 止損10（11 跑，約 22 分鐘）。
  要改測時間出場：把 RISK_EXIT 改成 "time"（或在 RUN_LIST 留通過的幾支）。
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
from walk_forward import run_portfolio_walk_forward, _extended_summary
from config import (
    ACTIVE_PRESETS,
    COMMISSION_PCT,
    SLIPPAGE_PCT,
)

# ══════════════════════════════════════════════════════════════════
# 設定
# ══════════════════════════════════════════════════════════════════
RISK_EXIT = "stop"          # "stop"=止損10%（篩選器）；"time"=時間20日（通過者細測）
STOP_LOSS_PCT = 10
MAX_HOLD_DAYS = 20

SURVIVOR_GAP_THRESHOLD = -3.0   # 真實出場% − 頂部OOS% < 此 → 仍 survivorship（偵測門檻）
KEEP_THRESHOLD = 2.0            # 真實出場% ≥ 此 → 🟢 保留候選（明顯正，非打平）。Ivan 可調。

# 預設跑全部 ACTIVE。要只跑特定幾支，把名稱填進這裡（用 config 的完整 key 含 💎）。
RUN_LIST = list(ACTIVE_PRESETS.keys())

# Phase 1（純 s2，舊口徑）頂部 OOS / 真實出場 對照（HANDOVER27 第二節）
PHASE1 = {
    "b13": (7.28, -5.55), "b14": (5.84, -8.40), "b15": (6.55, -7.06),
    "b16": (7.54, -5.47), "b17": (8.15, -8.26), "b18": (6.85, -6.17),
    "b12+b15": (7.25, -3.59), "b13+b15": (8.33, -7.47),
    "b15+b17": (9.86, -6.38), "b12+b6": (10.26, -11.06), "b15+b6": (9.74, -5.17),
}


# ══════════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════════
def build_stock_data(tickers: list):
    stock_data, skipped = {}, 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        stock_data[tkr] = df
    return stock_data, skipped


def summarize_wf(wf_results: list) -> dict:
    if not wf_results:
        return {"avg_oos": None, "oos_pos": 0, "valid_folds": 0, "fold7_n": None,
                "total_forced": 0, "ext_closed": 0, "ext_still": 0,
                "ext_avg_return": None, "ext_win_rate": None, "ext_avg_days": None,
                "gap": None}
    valid = [r for r in wf_results if r.get("valid_oos")]
    oos_rets = [r["oos_metrics"].get("平均每筆回報%", 0.0) for r in valid if r["oos_metrics"]]
    avg_oos = sum(oos_rets) / len(oos_rets) if oos_rets else None
    oos_pos = sum(1 for r in valid if r["oos_metrics"].get("平均每筆回報%", 0.0) > 0)
    fold7_n = wf_results[-1].get("oos_trade_count", 0)

    total_forced = sum(r.get("forced_exit_count", 0) for r in wf_results)
    all_ext = [t for r in wf_results for t in r.get("oos_extended_trades", [])]
    ext = _extended_summary(all_ext)
    ext_avg = ext.get("avg_return")
    gap = (ext_avg - avg_oos) if (ext_avg is not None and avg_oos is not None) else None

    return {"avg_oos": avg_oos, "oos_pos": oos_pos, "valid_folds": len(valid),
            "fold7_n": fold7_n, "total_forced": total_forced,
            "ext_closed": ext.get("closed", 0), "ext_still": ext.get("still_held", 0),
            "ext_avg_return": ext_avg, "ext_win_rate": ext.get("win_rate"),
            "ext_avg_days": ext.get("avg_days"), "gap": gap}


def verdict(s: dict) -> str:
    gap = s["gap"]
    true_ret = s["ext_avg_return"]
    if gap is not None and gap < SURVIVOR_GAP_THRESHOLD:
        return f"⚠️ 未清乾淨({gap:+.1f}pp)"
    if true_ret is None:
        return "⚪ 無延伸交易可判"
    if true_ret >= KEEP_THRESHOLD:
        return f"🟢 保留候選({true_ret:+.2f}%)"
    if true_ret >= 0:
        return f"🟡 打平觀察({true_ret:+.2f}%)"
    return f"🔴 確認降級({true_ret:+.2f}%)"


def short_key(name: str) -> str:
    """'💎 b12+b15 資金流向+下影線' → 'b12+b15' 用於對照 PHASE1。"""
    body = name.replace("💎", "").strip()
    token = body.split(" ")[0]
    return token


def run_one(name: str, preset: dict, stock_data: dict) -> dict:
    sl = STOP_LOSS_PCT if RISK_EXIT == "stop" else None
    md = MAX_HOLD_DAYS if RISK_EXIT == "time" else None
    exit_desc = f"止損 {sl}%" if sl else f"超時 {md} 日"

    print(f"\n────────────────────────────────────────")
    print(f"▶ {name}")
    print(f"  出場：s2 布林上軌 + {exit_desc}  ｜ min_hold={preset.get('min_hold_days')}")
    t0 = time.time()

    last = [0.0]
    def cb(fold, total, ticker):
        now = time.time()
        if now - last[0] > 1.0:
            print(f"    fold {fold}/{total}  {ticker}", end="\r", flush=True)
            last[0] = now

    wf = run_portfolio_walk_forward(
        stock_data,
        buy_sigs=preset["buy"],
        sell_sigs=preset["sell"],
        is_months=12, oos_months=6, trade_size=100_000,
        slippage=SLIPPAGE_PCT, commission_pct=COMMISSION_PCT,
        stop_loss_pct=sl, max_hold_days=md,
        min_hold_days=preset.get("min_hold_days"),
        track_extended=True, use_pit_universe=True,
        progress_cb=cb,
    )
    print(" " * 80, end="\r")

    s = summarize_wf(wf)
    v = verdict(s)
    elapsed = time.time() - t0

    oos_str  = f"{s['avg_oos']:+.2f}%"        if s["avg_oos"]        is not None else "N/A"
    true_str = f"{s['ext_avg_return']:+.2f}%" if s["ext_avg_return"] is not None else "N/A"
    gap_str  = f"{s['gap']:+.2f}pp"           if s["gap"]            is not None else "N/A"
    wr_str   = f"{s['ext_win_rate']:.1f}%"    if s["ext_win_rate"]   is not None else "N/A"
    days_str = f"{s['ext_avg_days']:.0f}天"   if s["ext_avg_days"]   is not None else "N/A"

    print(f"  ✓ {elapsed:.1f}s  頂部OOS {oos_str} → 真實出場 {true_str} (差距 {gap_str})")
    print(f"    真實勝率 {wr_str}  平均持倉 {days_str}  強制平倉 {s['total_forced']}  "
          f"真實出場數 {s['ext_closed']}")
    print(f"    判定：{v}")

    return {"name": name, "key": short_key(name), "summary": s, "verdict": v}


def print_table(rows: list):
    exit_label = f"止損{STOP_LOSS_PCT}%" if RISK_EXIT == "stop" else f"時間{MAX_HOLD_DAYS}日"
    print("\n" + "═" * 116)
    print(f"  Phase 4：全 ACTIVE × s2+{exit_label} 篩選 — 延伸追蹤總表（PIT WF 12+6, $100k, PIT ON）")
    print(f"  ★benchmark = 真實出場%（頂部 OOS 已證 survivorship-prone，僅供佐證）★")
    print("═" * 116)
    print(f"{'策略':<26} {'頂部OOS':>9} {'真實出場':>9} {'差距':>9} "
          f"{'真實勝率':>9} {'平均持倉':>9} {'強制平倉':>9} {'Phase1真實':>11} {'判定':>20}")
    print("─" * 116)
    # 依真實出場% 由高到低排序，最好的浮到上面
    rows_sorted = sorted(
        [r for r in rows if r],
        key=lambda r: (r["summary"]["ext_avg_return"] is not None,
                       r["summary"]["ext_avg_return"] or -999),
        reverse=True,
    )
    for r in rows_sorted:
        s = r["summary"]
        name = r["name"].replace("💎", "").strip()
        if len(name) > 25:
            name = name[:24] + "…"
        oos_str  = f"{s['avg_oos']:+.2f}"        if s["avg_oos"]        is not None else "N/A"
        true_str = f"{s['ext_avg_return']:+.2f}" if s["ext_avg_return"] is not None else "N/A"
        gap_str  = f"{s['gap']:+.2f}"            if s["gap"]            is not None else "N/A"
        wr_str   = f"{s['ext_win_rate']:.1f}"    if s["ext_win_rate"]   is not None else "N/A"
        days_str = f"{s['ext_avg_days']:.0f}"    if s["ext_avg_days"]   is not None else "N/A"
        p1 = PHASE1.get(r["key"])
        p1_str = f"{p1[1]:+.2f}" if p1 else "—"
        print(f"{name:<26} {oos_str:>9} {true_str:>9} {gap_str:>9} "
              f"{wr_str:>9} {days_str:>9} {s['total_forced']:>9} {p1_str:>11} {r['verdict']:>20}")
    print("═" * 116)


def print_recommendation(rows: list):
    keep   = [r for r in rows if r and "🟢" in r["verdict"]]
    flat   = [r for r in rows if r and "🟡" in r["verdict"]]
    drop   = [r for r in rows if r and "🔴" in r["verdict"]]
    dirty  = [r for r in rows if r and "⚠️" in r["verdict"]]

    print("\n" + "═" * 116)
    print("  Phase 4 篩選結論（路線 B）")
    print("═" * 116)
    print(f"\n🟢 保留實盤候選（真實出場% ≥ {KEEP_THRESHOLD:.1f}%）：{len(keep)} 支")
    for r in keep:
        print(f"   • {r['name']}  →  {r['verdict']}")
    print(f"\n🟡 打平觀察（0 ~ {KEEP_THRESHOLD:.1f}%，傾向降級）：{len(flat)} 支")
    for r in flat:
        print(f"   • {r['name']}  →  {r['verdict']}")
    print(f"\n🔴 確認降級（風險出場後仍負）：{len(drop)} 支")
    for r in drop:
        print(f"   • {r['name']}  →  {r['verdict']}")
    if dirty:
        print(f"\n⚠️ 止損未清乾淨（差距仍 < {SURVIVOR_GAP_THRESHOLD}pp，需查）：{len(dirty)} 支")
        for r in dirty:
            print(f"   • {r['name']}  →  {r['verdict']}")

    print("\n" + "─" * 116)
    print("💡 下一步：")
    if keep:
        print(f"   • 🟢 {len(keep)} 支用時間出場細測（把 RISK_EXIT 改 'time' 重跑），確認穩健後保留實盤。")
        print(f"   • 其餘降級 + 帳本 reset + ledger.py caption 改寫（benchmark 轉真實出場%）。")
    else:
        print(f"   • 無一支真實出場% 站上 {KEEP_THRESHOLD:.1f}%：全 ACTIVE 在誠實口徑下打平/負。")
        print(f"     → 確認路線 B 降級：清空實盤推播 / 降 💎 / 帳本 reset。")
    print(f"   • KEEP_THRESHOLD 目前 {KEEP_THRESHOLD:.1f}%；嫌嚴/鬆可改腳本頂部再判讀（不需重跑）。")


def main() -> int:
    t_start = time.time()
    exit_label = f"止損{STOP_LOSS_PCT}%" if RISK_EXIT == "stop" else f"時間{MAX_HOLD_DAYS}日"
    print("═" * 116)
    print(f"  V22.2 Phase 4：全 {len(RUN_LIST)} 支 ACTIVE × s2+{exit_label} 風險出場篩選（路線 B）")
    print(f"  設定：投資組合 / PIT ON / 5年 / IS12 OOS6 / "
          f"手續費{COMMISSION_PCT} / 滑點{SLIPPAGE_PCT}")
    print(f"  benchmark = 真實出場%（延伸追蹤）；保留門檻 KEEP_THRESHOLD = {KEEP_THRESHOLD:.1f}%")
    print("═" * 116)

    tickers = load_stocks()
    print(f"\nstocks.txt 共 {len(tickers)} 隻；載入 EODHD…")
    stock_data, skipped = build_stock_data(tickers)
    print(f"已載入 {len(stock_data)} 隻（跳過 {skipped} 隻數據不足）")
    if len(stock_data) < 10:
        print("❌ 可用股票太少（<10），中止。")
        return 1

    rows = []
    for name in RUN_LIST:
        preset = ACTIVE_PRESETS.get(name)
        if preset is None:
            print(f"  ⚠️ {name} 不在 ACTIVE_PRESETS，跳過")
            continue
        rows.append(run_one(name, preset, stock_data))

    print_table(rows)
    print_recommendation(rows)

    elapsed = time.time() - t_start
    print(f"\n總耗時：{elapsed:.1f} 秒 ({elapsed/60:.1f} 分鐘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

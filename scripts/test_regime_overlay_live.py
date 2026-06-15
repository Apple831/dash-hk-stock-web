"""
test_regime_overlay_live.py
── 制度曝險疊加：震盪市是不是 LIVE 這本帳的「不該交易」制度？──

═══════════════════════════════════════════════════════════════════
承前兩輪的結論
═══════════════════════════════════════════════════════════════════
  b1 突破 = 偽 beta 無 alpha；b5+s2 = 與 b19 同因子（扣 beta 後超額相關 +0.97）。
  → long-only 單股技術訊號只有一個有效因子（超賣反轉），加訊號無法分散。
  逐 fold 又顯示：高震盪佔比的 fold，b19 與 b5 都不賺。
  → 推論：真正的「不同市況」槓桿不是第二個訊號，而是【制度曝險管理】——
     在這本帳挨餓的制度（震盪市）直接減/停倉。現金在爛制度報酬=0，已贏 b5 的 −1.89%。

═══════════════════════════════════════════════════════════════════
本腳本怎麼測（便宜且精準：每支只跑一次全天候 WF）
═══════════════════════════════════════════════════════════════════
  對 LIVE 四支各跑一次全天候投組 WF，收集 blended cohort 交易
  （in-window oos_trades ∪ 邊界延伸已平單），逐筆用【進場日的 HSI 制度】分桶：
      🟢 牛市 / 🟡 震盪市bucket / 🔴 熊市   （🟡 再拆 震盪市 / 轉折期）
  各桶 cohort 平均報酬 = 該制度進場的真實期望。

  暫停某制度 = 把該桶交易移除 → 看整本帳 blended 的 lift 與被砍掉的交易比例。
  這直接等價於 production 端「該制度日停止進場」（非複利定額，逐筆獨立，無資金佔用偏差）。

═══════════════════════════════════════════════════════════════════
判讀
═══════════════════════════════════════════════════════════════════
  • 若 🟡（或細到 震盪市 label）cohort 明顯為負 → 暫停它能提升整本帳，疊加成立。
    下一步：把震盪市閘做進 daily_scan（LIVE 在該制度停止推播），紙上帳本驗證。
  • 若 🟡 cohort ≈ 0 或正 → 震盪市沒在拖累，疊加沒用，制度槓桿這條也排除。

使用：python scripts/test_regime_overlay_live.py   （約 17-20 分鐘，4 支各一輪）
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
from data import load_stocks, get_cached
from historical_universe import load_eodhd_prices
from indicators import calculate_indicators
from regime import regime_history
from walk_forward import run_portfolio_walk_forward
from config import ACTIVE_PRESETS, LIVE_PRESET_KEYS, COMMISSION_PCT, SLIPPAGE_PCT

BUCKET_OF = {
    "強牛市": "🟢 牛市", "弱牛市": "🟢 牛市", "牛市警惕": "🟢 牛市",
    "震盪市": "🟡 震盪市", "轉折期": "🟡 震盪市",
    "強熊市": "🔴 熊市", "弱熊市": "🔴 熊市", "熊市觀察": "🔴 熊市",
}
BUCKET_ORDER = ["🟢 牛市", "🟡 震盪市", "🔴 熊市"]
PASS_KW = ("stop_loss_pct", "take_profit_pct", "max_hold_days",
           "min_hold_days", "cooldown_days", "trailing_stop_pct")


def build_regime_label_series():
    hsi = get_cached("^HSI", "5y")
    if hsi is None or hsi.empty:
        print("⚠️ 無法取得 ^HSI")
        return None
    hsi = calculate_indicators(hsi)
    hist = regime_history(hsi, n_bars=len(hsi))
    if not hist:
        return None
    ser = pd.Series({r["date"]: r["label"] for r in hist}).sort_index()
    counts = ser.map(lambda x: BUCKET_OF.get(x, "?")).value_counts()
    parts = []
    for b in BUCKET_ORDER:
        if b in counts:
            parts.append(f"{b} {counts[b] / len(ser) * 100:.0f}%")
    print(f"  ^HSI {len(ser)} 日制度分布：" + "  ".join(parts))
    return ser


def build_stock_data(tickers):
    sd, skipped = {}, 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        sd[tkr] = df
    return sd, skipped


def _preset_kwargs(preset):
    return {k: preset[k] for k in PASS_KW if k in preset and preset[k] is not None}


def collect_blended_trades(label, preset, sd):
    """跑一次全天候 WF，回傳 blended cohort 的 (進場日Timestamp, 回報%) list。"""
    print(f"\n▶ {label}  全天候 WF…")
    t0 = time.time()
    last = [0.0]

    def cb(f, tot, tk):
        now = time.time()
        if now - last[0] > 1.0:
            print(f"    fold {f}/{tot}  {tk}", end="\r", flush=True)
            last[0] = now

    wf = run_portfolio_walk_forward(
        sd, buy_sigs=preset["buy"], sell_sigs=preset["sell"],
        is_months=12, oos_months=6, trade_size=100_000,
        slippage=SLIPPAGE_PCT, commission_pct=COMMISSION_PCT,
        hsi_filter=None, track_extended=True, use_pit_universe=True,
        progress_cb=cb, **_preset_kwargs(preset),
    )
    print(" " * 80, end="\r")

    trades = []
    for r in wf:
        for t in r.get("oos_trades", []):
            if t.get("回報%") is not None:
                trades.append((pd.Timestamp(t["買入日期"]), t["回報%"]))
        for t in r.get("oos_extended_trades", []):
            if not t.get("_still_held_at_end", False) and t.get("回報%") is not None:
                trades.append((pd.Timestamp(t["買入日期"]), t["回報%"]))
    print(f"  ✓ {time.time() - t0:.1f}s  ｜ {len(trades)} 筆 blended cohort")
    return trades


def tag_trades(trades, label_ser):
    """每筆貼上進場日的制度 label 與 bucket。"""
    tagged = []
    for ts, ret in trades:
        lab = None
        if label_ser is not None:
            try:
                v = label_ser.asof(ts)
                lab = v if isinstance(v, str) else None
            except Exception:
                lab = None
        tagged.append((ts, ret, lab, BUCKET_OF.get(lab, "?")))
    return tagged


def _stat(rets):
    if not rets:
        return None, 0, None
    n = len(rets)
    mean = sum(rets) / n
    wr = sum(1 for x in rets if x > 0) / n * 100
    return mean, n, wr


def print_bucket_table(tagged, indent="    "):
    total = [t[1] for t in tagged]
    tm, tn, tw = _stat(total)
    tm_s = f"{tm:+.2f}%" if tm is not None else "N/A"
    tw_s = f"{tw:.0f}%" if tw is not None else "N/A"
    print(f"{indent}{'制度桶':<14}{'筆數':>7}{'平均報酬':>10}{'勝率':>8}")
    print(f"{indent}{'─' * 40}")
    for b in BUCKET_ORDER:
        rets = [t[1] for t in tagged if t[3] == b]
        m, n, w = _stat(rets)
        if n == 0:
            continue
        m_s = f"{m:+.2f}%" if m is not None else "N/A"
        w_s = f"{w:.0f}%" if w is not None else "N/A"
        flag = "  ← 拖累" if (m is not None and m < 0) else ""
        print(f"{indent}{b:<14}{n:>7}{m_s:>10}{w_s:>8}{flag}")
        if b == "🟡 震盪市":  # 拆 震盪市 / 轉折期
            for sub in ("震盪市", "轉折期"):
                sr = [t[1] for t in tagged if t[2] == sub]
                sm, sn, sw = _stat(sr)
                if sn == 0:
                    continue
                sm_s = f"{sm:+.2f}%" if sm is not None else "N/A"
                sw_s = f"{sw:.0f}%" if sw is not None else "N/A"
                print(f"{indent}  └ {sub:<10}{sn:>7}{sm_s:>10}{sw_s:>8}")
    print(f"{indent}{'─' * 40}")
    print(f"{indent}{'全部':<14}{tn:>7}{tm_s:>10}{tw_s:>8}")


def overlay_lift(tagged, drop_pred, name):
    total = [t[1] for t in tagged]
    kept = [t[1] for t in tagged if not drop_pred(t)]
    tm, tn, _ = _stat(total)
    km, kn, _ = _stat(kept)
    if tm is None or km is None:
        return
    pruned = tn - kn
    pct = pruned / tn * 100 if tn else 0
    lift = km - tm
    print(f"  {name:<22} blended {tm:+.2f}% → {km:+.2f}%  "
          f"(lift {lift:+.2f}pp，砍 {pruned} 筆 {pct:.0f}%)")


def main():
    t_start = time.time()
    print("═" * 88)
    print("  制度曝險疊加：震盪市是不是 LIVE 這本帳的「不該交易」制度？")
    print("  每支跑一次全天候 WF，blended cohort 按進場日制度分桶 → 暫停爛桶的 lift")
    print("═" * 88)

    print("\n建立 HSI 每日制度 label 序列…")
    label_ser = build_regime_label_series()

    keys = [k for k in LIVE_PRESET_KEYS if k in ACTIVE_PRESETS]
    keys.sort()
    print(f"\nLIVE 白名單 {len(keys)} 支：")
    for k in keys:
        print(f"  • {k}")

    tickers = load_stocks()
    print(f"\nstocks.txt {len(tickers)} 隻；載入 EODHD…")
    sd, skipped = build_stock_data(tickers)
    print(f"已載入 {len(sd)} 隻（跳過 {skipped}）")
    if len(sd) < 10:
        print("❌ 可用股票太少")
        return 1

    all_tagged = []
    per_strat = {}
    for k in keys:
        trades = collect_blended_trades(k, ACTIVE_PRESETS[k], sd)
        tagged = tag_trades(trades, label_ser)
        per_strat[k] = tagged
        all_tagged += tagged

    # ── 各策略分桶 ────────────────────────────────────────────────
    print("\n" + "═" * 88)
    print("  各 LIVE 策略：進場制度 × cohort 報酬")
    print("═" * 88)
    for k in keys:
        print(f"\n{k}")
        print_bucket_table(per_strat[k])

    # ── 合併 LIVE 整本帳 ──────────────────────────────────────────
    print("\n" + "═" * 88)
    print("  合併 LIVE 整本帳（四支 cohort 匯總）")
    print("═" * 88)
    print_bucket_table(all_tagged, indent="  ")

    # ── 疊加 lift ─────────────────────────────────────────────────
    print("\n" + "═" * 88)
    print("  暫停制度的 lift（合併帳）")
    print("═" * 88)
    overlay_lift(all_tagged, lambda t: t[3] == "🟡 震盪市",
                 "暫停整個 🟡 震盪市桶")
    overlay_lift(all_tagged, lambda t: t[2] == "震盪市",
                 "只暫停 震盪市 label")
    overlay_lift(all_tagged, lambda t: t[2] == "轉折期",
                 "只暫停 轉折期 label")
    print("═" * 88)

    # ── 結論 ──────────────────────────────────────────────────────
    zd = [t[1] for t in all_tagged if t[3] == "🟡 震盪市"]
    zm, zn, _ = _stat(zd)
    print("\n判讀：")
    if zm is None or zn == 0:
        print("  震盪市 cohort 樣本不足，無法判定。")
    elif zm < -0.5:
        print(f"  ✅ 🟡 震盪市 cohort 平均 {zm:+.2f}%（{zn} 筆）明顯為負 → 暫停它能提升整本帳。")
        print("     疊加成立。下一步：把震盪市閘接進 daily_scan（LIVE 在該制度停止推播），")
        print("     用紙上帳本驗證 lift 真的兌現；並決定停整個 🟡 桶還是只停高 CoV 震盪市 label。")
    elif zm < 0.5:
        print(f"  ⚠️ 🟡 震盪市 cohort 平均 {zm:+.2f}%（{zn} 筆）≈ 打平 → 暫停只省手續費，效益薄。")
        print("     疊加邊際；要不要做看砍掉的交易比例與回撤改善（需另量）。")
    else:
        print(f"  ✗ 🟡 震盪市 cohort 平均 {zm:+.2f}%（{zn} 筆）為正 → 震盪市沒拖累整本帳。")
        print("     制度曝險疊加這條也排除；剩下只有橫斷面相對強弱(B)還沒試。")

    print(f"\n總耗時 {time.time() - t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

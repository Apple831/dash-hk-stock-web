"""
test_regime_sizing.py
── 路徑 A：制度條件式定倉（把「錢在哪」換成「賺更多」，不需新訊號）──

═══════════════════════════════════════════════════════════════════
為什麼是這支
═══════════════════════════════════════════════════════════════════
  long-only 訊號搜尋四連敗收線（b1/b5/RS動量/RS反轉）→ 本帳只有一個會賺的因子
  （超賣反轉）。加訊號分散不了它，但可以「更聰明地下注」。
  制度疊加(A) 已證：錢集中在牛市(+5.20%)/熊市(+4.41%)，震盪市(-3%)最毒（已閘）。
  現況：所有 LIVE 策略齊頭輕倉 → 沒把「肥制度壓大注、瘦制度壓小注」變成 PnL。
  本腳本量化「制度條件定倉 vs 齊頭定倉」的已實現報酬增益。

═══════════════════════════════════════════════════════════════════
做法
═══════════════════════════════════════════════════════════════════
  1. LIVE 四支各跑全天候投組 WF，收 blended cohort（in-window ∪ 邊界延伸已平單），
     逐筆記 (進場日, 出場日, 回報%, 進場日制度 label)。
  2. 按進場日制度分桶，每桶算：n / 平均% / 標準差 / Sharpe(=平均/標準差，最可信品質指標) /
     勝率 / 成長最優 Kelly f*（解 max Σ ln(1+f·r)）/ ¼-Kelly / 進場時平均同時持倉數。
  3. 給「制度 → 相對定倉乘數」（以 ¼-Kelly 正規化成『重分配、非加槓桿』；震盪市=0 已閘）。
  4. 量 lift：制度加權 vs 齊頭的每單位資本已實現報酬（剔震盪市＝實盤現況基線），
     並做 leave-one-regime-out 穩健檢查（lift 是否單靠超配某一制度撐起）。

═══════════════════════════════════════════════════════════════════
鐵則 / 讀法（務必連同數字一起看，否則會超押）
═══════════════════════════════════════════════════════════════════
  ★ per-trade Kelly 假設『序列下注』。實際多倉並行 → 每倉分數 ≈ f / 平均並行數，
    切勿把 per-trade f* 全押在每一筆。腳本給的「每倉 ¼-Kelly」已除並行數。
  ★ 熊市桶肥但 episode 集中（見 test_bear_scope：強熊 N_eff~5）→ per-trade std 低估尾險，
    其 Kelly 偏高是假象，熊市乘數須折扣、比照 b19/b13+b17 輕倉等級，勿照單全收。
  ★ 牛市桶是「乾淨的肥」（broad、較不集中）→ 相對最可信的加碼對象。
  ★ 分桶報酬是相對/複利口徑，非字面 HKD；絕對槓桿上限仍由 MC 破產率/maxDD/VaR 管（與此解耦）。
  ★ production hook：daily_scan 用『前一收盤制度』給每個推播標定倉乘數（如同 ⚠️輕倉標籤，PIT 乾淨）。

使用：python scripts/test_regime_sizing.py   （LIVE 四支各一輪全天候 WF，約 12-15 分鐘）
"""
import os
import sys
import math
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
from config import (
    ACTIVE_PRESETS, LIVE_PRESET_KEYS, BEAR_EXEMPT_PRESETS,
    BEAR_LABELS_HARD, COMMISSION_PCT, SLIPPAGE_PCT,
)

PASS_KW = ("stop_loss_pct", "take_profit_pct", "max_hold_days",
           "min_hold_days", "cooldown_days", "trailing_stop_pct")

GATED_LABEL = "震盪市"        # 已被 daily_scan 閘掉 → 定倉乘數 0、且不計入基線
KELLY_FRAC = 0.25            # 用 ¼-Kelly（全 Kelly 太激進且估計脆弱）
MIN_BUCKET_N = 30           # 桶內樣本下限（低於此定倉數字不可信）


# ══════════════════════════════════════════════════════════════════
# 制度 label 序列（PIT：asof 取 ≤ 進場日的最後已知 label）
# ══════════════════════════════════════════════════════════════════
def build_regime_label_series():
    hsi = get_cached("^HSI", "5y")
    if hsi is None or hsi.empty:
        return None
    hsi = calculate_indicators(hsi)
    hist = regime_history(hsi, n_bars=len(hsi))
    if not hist:
        return None
    return pd.Series({r["date"]: r["label"] for r in hist}).sort_index()


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


def _trade_dates(t):
    """回 (buy_ts, sell_ts) 或 (buy_ts, None)。"""
    b = t.get("_buy_date")
    if b is None and t.get("買入日期"):
        try:
            b = pd.Timestamp(t["買入日期"])
        except Exception:
            b = None
    s = t.get("_sell_date")
    if s is None and t.get("賣出日期") and "持倉" not in str(t.get("賣出日期")):
        try:
            s = pd.Timestamp(t["賣出日期"])
        except Exception:
            s = None
    return (pd.Timestamp(b) if b is not None else None,
            pd.Timestamp(s) if s is not None else None)


def collect_live_trades(sd, label_ser):
    """LIVE 四支各跑全天候 WF，回 [(buy_ts, sell_ts, ret%, regime_label), …]。"""
    live = [k for k in LIVE_PRESET_KEYS if k in ACTIVE_PRESETS]
    all_trades = []
    for k in live:
        preset = ACTIVE_PRESETS[k]
        print(f"\n▶ {k}  全天候 PIT WF…")
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

        cnt = 0
        for r in wf:
            pool = list(r.get("oos_trades", []))
            pool += [t for t in r.get("oos_extended_trades", [])
                     if not t.get("_still_held_at_end", False)]
            for t in pool:
                if t.get("回報%") is None:
                    continue
                b, s = _trade_dates(t)
                if b is None:
                    continue
                lab = None
                if label_ser is not None:
                    try:
                        v = label_ser.asof(b)
                        lab = v if isinstance(v, str) else None
                    except Exception:
                        lab = None
                all_trades.append((b, s, float(t["回報%"]), lab))
                cnt += 1
        print(f"  ✓ {time.time() - t0:.1f}s  ｜ {cnt} 筆")
    return all_trades


# ══════════════════════════════════════════════════════════════════
# 統計 / Kelly / 並行數
# ══════════════════════════════════════════════════════════════════
def _stats(rets):
    n = len(rets)
    if n == 0:
        return None
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / n if n > 1 else 0.0
    std = var ** 0.5
    wr = sum(1 for x in rets if x > 0) / n * 100
    sharpe = mean / std if std > 0 else None
    return {"n": n, "mean": mean, "std": std, "wr": wr, "sharpe": sharpe}


def kelly_star(rets_pct, f_max=3.0, step=0.01):
    """解 max_f (1/n)Σ ln(1+f·r)，r 為分數。回 (f*, 每筆對數成長)。"""
    rf = [x / 100.0 for x in rets_pct]
    best_f, best_g = 0.0, 0.0
    f = 0.0
    while f <= f_max + 1e-9:
        g, ok = 0.0, True
        for r in rf:
            x = 1.0 + f * r
            if x <= 1e-9:
                ok = False
                break
            g += math.log(x)
        if ok:
            g /= len(rf)
            if g > best_g:
                best_g, best_f = g, f
        f += step
    return best_f, best_g


def avg_concurrency_at_entry(all_trades, mask_idx):
    """對 mask_idx 指定的交易，算其進場時全帳(四支合併)已開倉的平均並行數。"""
    intervals = [(b, s) for (b, s, _, _) in all_trades if b is not None and s is not None]
    vals = []
    for i in mask_idx:
        bi = all_trades[i][0]
        if bi is None:
            continue
        open_n = sum(1 for (b, s) in intervals if b <= bi < s)
        vals.append(open_n)
    return (sum(vals) / len(vals)) if vals else 0.0


# ══════════════════════════════════════════════════════════════════
def main():
    t_start = time.time()
    print("═" * 96)
    print("  路徑 A：制度條件式定倉（LIVE 四支 blended cohort 按進場日制度分桶）")
    print("═" * 96)

    label_ser = build_regime_label_series()
    if label_ser is None:
        print("❌ 無制度序列")
        return 1

    tickers = load_stocks()
    print(f"\nstocks.txt {len(tickers)} 隻；載入 EODHD…")
    sd, skipped = build_stock_data(tickers)
    print(f"已載入 {len(sd)} 隻（跳過 {skipped}）")
    if len(sd) < 10:
        return 1

    all_trades = collect_live_trades(sd, label_ser)
    print(f"\n合併 LIVE cohort 共 {len(all_trades)} 筆")

    # ── 分桶（依進場日制度 raw label）──────────────────────────────
    buckets = {}
    for i, (_, _, ret, lab) in enumerate(all_trades):
        buckets.setdefault(lab if lab else "（無label）", []).append(i)

    # 各桶統計
    print("\n" + "═" * 96)
    print("  各制度桶：分布 × Kelly × 並行數")
    print("═" * 96)
    print(f"  {'制度':<10}{'n':>6}{'平均%':>9}{'std':>8}{'Sharpe':>9}"
          f"{'勝率':>7}{'Kelly f*':>10}{'¼-Kelly':>9}{'平均並行':>9}{'每倉¼K':>9}")
    print("  " + "─" * 90)

    rows = {}
    for lab, idx in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        rets = [all_trades[i][2] for i in idx]
        st = _stats(rets)
        fstar, _ = kelly_star(rets)
        qk = fstar * KELLY_FRAC
        conc = avg_concurrency_at_entry(all_trades, idx)
        per_pos_qk = qk / max(1.0, conc)
        rows[lab] = {**st, "fstar": fstar, "qk": qk, "conc": conc, "per_pos_qk": per_pos_qk}
        sh = f"{st['sharpe']:+.3f}" if st["sharpe"] is not None else "N/A"
        thin = "  ⚠薄" if st["n"] < MIN_BUCKET_N else ""
        print(f"  {lab:<10}{st['n']:>6}{st['mean']:>+8.2f}%{st['std']:>8.2f}{sh:>9}"
              f"{st['wr']:>6.0f}%{fstar:>10.2f}{qk:>9.2f}{conc:>9.1f}{per_pos_qk:>9.2f}{thin}")

    # ── 相對定倉乘數（剔震盪市；以 ¼-Kelly 正規化成『重分配』）──────
    print("\n" + "═" * 96)
    print("  制度 → 相對定倉乘數（基準 1.0 = 現行齊頭；震盪市=0 已閘；總風險預算不變的重分配）")
    print("═" * 96)
    tradeable = {lab: r for lab, r in rows.items()
                 if lab != GATED_LABEL and lab != "（無label）" and r["n"] >= MIN_BUCKET_N
                 and r["qk"] > 0}
    # 以「交易筆數加權的 ¼-Kelly 均值」為基準，使平均乘數≈1（重分配非加槓桿）
    tot_n = sum(rows[lab]["n"] for lab in tradeable)
    base_qk = (sum(rows[lab]["qk"] * rows[lab]["n"] for lab in tradeable) / tot_n) if tot_n else 0.0
    mult = {}
    for lab, r in rows.items():
        if lab == GATED_LABEL:
            mult[lab] = 0.0
        elif lab in tradeable and base_qk > 0:
            mult[lab] = r["qk"] / base_qk
        else:
            mult[lab] = None  # 薄樣本/負編 → 不給乘數
    for lab in sorted(rows, key=lambda l: -(rows[l]["mean"])):
        m = mult[lab]
        ms = "0（閘）" if lab == GATED_LABEL else (f"{m:.2f}×" if m is not None else "— 樣本薄/負編，沿用 1.0×")
        flag = ""
        if lab in BEAR_LABELS_HARD:
            flag = "  ⚠ episode集中：乘數須折扣、比照 b19/b13+b17 輕倉，勿照收"
        if lab == "牛市":
            flag = "  ✅ 乾淨的肥（broad）：相對最可信加碼對象"
        print(f"  {lab:<10}{ms:>16}{flag}")

    # ── lift：制度加權 vs 齊頭（剔震盪市＝實盤現況基線）─────────────
    print("\n" + "═" * 96)
    print("  增益量化（剔除震盪市＝實盤現況；制度加權 = 每筆乘其制度乘數後的資本加權平均報酬）")
    print("═" * 96)

    def weighted_mean(exclude_label=None):
        num = den = 0.0
        flat_sum = flat_n = 0
        for i, (_, _, ret, lab) in enumerate(all_trades):
            if lab == GATED_LABEL or lab is None:
                continue
            if exclude_label is not None and lab == exclude_label:
                continue
            m = mult.get(lab)
            if m is None:
                m = 1.0
            num += m * ret
            den += m
            flat_sum += ret
            flat_n += 1
        flat = flat_sum / flat_n if flat_n else None
        wtd = num / den if den else None
        return flat, wtd, flat_n

    flat, wtd, n_base = weighted_mean()
    if flat is not None and wtd is not None:
        print(f"  齊頭（現況）          : {flat:+.3f}%   （{n_base} 筆，已剔震盪市）")
        print(f"  制度加權              : {wtd:+.3f}%")
        print(f"  ➤ lift               : {wtd - flat:+.3f}pp")

        # leave-one-regime-out：lift 是否單靠超配某一制度
        print("\n  ── 穩健檢查：剔掉某一制度後，lift 是否仍在 ──")
        labs_for_loo = [l for l in tradeable if mult.get(l) and mult[l] > 1.05]
        if not labs_for_loo:
            print("     （無顯著超配制度，lift 來源分散）")
        for l in sorted(labs_for_loo, key=lambda x: -mult[x]):
            f2, w2, _ = weighted_mean(exclude_label=l)
            if f2 is not None and w2 is not None:
                tag = "✅仍正" if (w2 - f2) > 0 else "⚠️轉負(該制度撐起)"
                print(f"     剔【{l}】(乘數{mult[l]:.2f}×)後 lift {w2 - f2:+.3f}pp  {tag}")

    print("\n  ── 落地（production hook）──")
    print("     daily_scan 用『前一收盤制度』查上表乘數，給每個推播標定倉建議（如 ⚠️輕倉 標籤，PIT 乾淨）。")
    print("     熊市乘數先按住在 b19/b13+b17 輕倉等級（episode 集中、尾險被低估），勿照 Kelly 全收。")
    print("     絕對倉位天花板另由 MC 破產率/maxDD/VaR 決定（與本相對乘數解耦）。")
    print("═" * 96)
    print(f"\n總耗時 {time.time() - t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

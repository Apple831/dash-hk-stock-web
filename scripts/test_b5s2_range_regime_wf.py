"""
test_b5s2_range_regime_wf.py
── 尋找與 ROC 急跌反轉「正交」的新 edge：b5+s2 區間回歸 × 震盪市閘 ──

═══════════════════════════════════════════════════════════════════
為什麼是這支（承 b1 突破失敗的制度洞察）
═══════════════════════════════════════════════════════════════════
  b1 突破已證實死亡：無 alpha 之偽 beta，且 b19 流血的 fold b1 也虧。
  關鍵發現＝整本帳的錢都來自恐慌/強熊（ROC 家族最肥），在「震盪市」集體挨餓
  （b19 震盪市 −2.80% 最毒）。所以真分散 = 找一個【專在震盪市賺錢】的 edge。

  震盪市賺錢的機制 = 區間回歸：在區間底買、區間頂賣。
    • 買 = b5（收盤 < 布林下軌，跌到區間底）
    • 賣 = s2（收盤 > 布林上軌，漲到區間頂）★這就是區間回歸的誠實出場★
  與 b19「暴跌恐慌反彈 + 時間出場」完全不同的觸發、出場、主場。

  cohort 注意：抄底家族 s2 在下跌股「永不觸發 → 邊界強平灌水」。但本策略把進場
  閘在震盪市（價格在區間內擺盪），s2 會真的觸發 → 沒有那個 cohort 問題。
  blended（in-window ∪ 邊界延伸已平單，逐筆）仍是誠實尺，延伸追蹤照跑。

═══════════════════════════════════════════════════════════════════
假說與對照（這支的靈魂）
═══════════════════════════════════════════════════════════════════
  b5 單獨是「指標閾值」訊號，港股 PIT 通常沒 alpha（如 RSI<30 單獨）。
  所以假說【不是】「b5 有邊」，而是「b5+s2 被【震盪市制度】條件化後才有邊」。
  → 全天候對照組 (no gate) 預期打平/負；震盪市閘預期站上 +2%。
    若如此，edge 來自【制度條件化】本身，這正是針對制度缺口的真分散。

═══════════════════════════════════════════════════════════════════
判準（過了才精修 → MC vs b19 → 輕倉 LIVE）
═══════════════════════════════════════════════════════════════════
  ① 震盪市閘 blended ≥ +2.0%
  ② 逐 fold 正報酬 ≥ 60%
  ③ 全天候對照明顯較差（證明邊來自制度條件化，非 b5 本身）
  ④ 對 b19【超額】相關低（扣掉 HSI 窗報酬的市場 beta 後）＋ b19 流血 fold 時 b5 不虧
     ＋ 高震盪市佔比的 fold b5 應跑贏 b19 ★真分散的經濟證據★

使用：python scripts/test_b5s2_range_regime_wf.py
      （投組 PIT WF，約 20-25 分鐘：3 個 b5+s2 變體 + b19 基準各一輪）
"""
import os
import sys
import time
import statistics

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
from config import ACTIVE_PRESETS, B_NAMES, S_NAMES, COMMISSION_PCT, SLIPPAGE_PCT

# ── 候選：b5 區間底買 + s2 區間頂賣（程式化建 tuple）──────────────
B5_BUY  = tuple(name == "b5" for name in B_NAMES)
S2_SELL = tuple(name == "s2" for name in S_NAMES)
MIN_HOLD = 5

# ── 震盪市 bucket（MA缺口<2% 的非趨勢狀態：震盪市 + 轉折期）────────
ZHENDANG_LABELS = ("震盪市", "轉折期")

B19_KEY = "💎 b19 深度ROC超跌反彈"


def build_stock_data(tickers):
    sd, skipped = {}, 0
    for tkr in tickers:
        df = load_eodhd_prices(tkr)
        if df.empty or len(df) < 62:
            skipped += 1
            continue
        sd[tkr] = df
    return sd, skipped


def build_zhendang_filter():
    """用 HSI 每日制度建一條 boolean Series：True = 震盪市 bucket（可進場）。"""
    hsi = get_cached("^HSI", "5y")
    if hsi is None or hsi.empty:
        print("⚠️ 無法取得 ^HSI，震盪市閘將回退為全允許")
        return None, None
    hsi = calculate_indicators(hsi)
    hist = regime_history(hsi, n_bars=len(hsi))
    if not hist:
        return None, hsi
    ser = pd.Series(
        {r["date"]: (r["label"] in ZHENDANG_LABELS) for r in hist}
    ).sort_index()
    share = ser.mean() * 100 if len(ser) else 0.0
    print(f"  ^HSI {len(ser)} 日；震盪市 bucket 佔 {share:.0f}%")
    return ser, hsi


def _rets(trades):
    return [t["回報%"] for t in trades if t.get("回報%") is not None]


def _fold_blended(fold):
    rs = _rets(fold.get("oos_trades", []))
    for t in fold.get("oos_extended_trades", []):
        if not t.get("_still_held_at_end", False) and t.get("回報%") is not None:
            rs.append(t["回報%"])
    return (sum(rs) / len(rs)) if rs else None


def analyze(wf):
    strat_rets, ext_closed_rets, fold_blended, fold_spans = [], [], [], []
    for r in wf:
        strat_rets += _rets(r.get("oos_trades", []))
        for t in r.get("oos_extended_trades", []):
            if not t.get("_still_held_at_end", False) and t.get("回報%") is not None:
                ext_closed_rets.append(t["回報%"])
        fold_blended.append(_fold_blended(r))
        fold_spans.append((r.get("oos_start"), r.get("oos_end")))

    allr = strat_rets + ext_closed_rets
    blended = sum(allr) / len(allr) if allr else None
    wr = (sum(1 for x in allr if x > 0) / len(allr) * 100) if allr else None
    valid = [x for x in fold_blended if x is not None]
    pos_fold = (sum(1 for x in valid if x > 0) / len(valid) * 100) if valid else None
    return {
        "blended": blended, "n_total": len(allr), "wr": wr,
        "fold_blended": fold_blended, "fold_spans": fold_spans,
        "pos_fold_rate": pos_fold, "n_valid_folds": len(valid),
    }


def run_variant(label, buy, sell, stock_data, *,
                hsi_filter=None, max_hold_days=None, min_hold_days=MIN_HOLD):
    bits = []
    bits.append("s2 區間頂" if any(sell) else "（無策略賣）")
    if max_hold_days:
        bits.append(f"安全超時{max_hold_days}日")
    bits.append("震盪市閘" if hsi_filter is not None else "全天候")
    print(f"\n▶ {label}  ｜ {' + '.join(bits)}")
    t0 = time.time()
    last = [0.0]

    def cb(f, tot, tk):
        now = time.time()
        if now - last[0] > 1.0:
            print(f"    fold {f}/{tot}  {tk}", end="\r", flush=True)
            last[0] = now

    wf = run_portfolio_walk_forward(
        stock_data, buy_sigs=buy, sell_sigs=sell,
        is_months=12, oos_months=6, trade_size=100_000,
        slippage=SLIPPAGE_PCT, commission_pct=COMMISSION_PCT,
        max_hold_days=max_hold_days, min_hold_days=min_hold_days,
        hsi_filter=hsi_filter,
        track_extended=True, use_pit_universe=True, progress_cb=cb,
    )
    print(" " * 80, end="\r")
    a = analyze(wf)
    b, pf, wr = a["blended"], a["pos_fold_rate"], a["wr"]
    b_s = f"{b:+.2f}%" if b is not None else "N/A"
    pf_s = f"{pf:.0f}%" if pf is not None else "N/A"
    wr_s = f"{wr:.1f}%" if wr is not None else "N/A"
    print(f"  ✓ {time.time() - t0:.1f}s")
    print(f"    blended {b_s}  ｜ 逐fold正 {pf_s} ({a['n_valid_folds']}fold)"
          f"  ｜ 合計 {a['n_total']} 筆  ｜ 勝率 {wr_s}")
    return {"label": label, **a}


def _pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 2:
        return None
    try:
        return statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs])
    except Exception:
        return None


def _win_ret(close_ser, d0, d1):
    """HSI 窗報酬 %（asof 對齊，作為市場 beta proxy）。"""
    if close_ser is None or d0 is None or d1 is None:
        return None
    try:
        p0 = close_ser.asof(d0)
        p1 = close_ser.asof(d1)
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            return None
        return (p1 / p0 - 1) * 100
    except Exception:
        return None


def main():
    t_start = time.time()
    print("═" * 92)
    print("  b5+s2 區間回歸 × 震盪市閘：尋找專在震盪市賺錢、與 ROC 桶正交的 edge")
    print("  誠實尺 = s2(區間頂) 出場的 blended ≥ +2%；重點 = 全天候對照 + 對 b19 超額正交")
    print("═" * 92)

    if B19_KEY not in ACTIVE_PRESETS:
        print(f"❌ 找不到基準 preset {B19_KEY}")
        return 1
    b19_preset = ACTIVE_PRESETS[B19_KEY]

    print("\n建立震盪市制度閘（^HSI 每日制度）…")
    zhendang, hsi = build_zhendang_filter()
    hsi_close = hsi["Close"] if hsi is not None and "Close" in hsi.columns else None

    tickers = load_stocks()
    print(f"\nstocks.txt {len(tickers)} 隻；載入 EODHD…")
    sd, skipped = build_stock_data(tickers)
    print(f"已載入 {len(sd)} 隻（跳過 {skipped}）")
    if len(sd) < 10:
        print("❌ 可用股票太少")
        return 1

    # ── 三個 b5+s2 變體 ───────────────────────────────────────────
    v_gate = run_variant("b5+s2 震盪市閘", B5_BUY, S2_SELL, sd,
                         hsi_filter=zhendang, max_hold_days=None)
    v_gate_md = run_variant("b5+s2 震盪市閘+超時20", B5_BUY, S2_SELL, sd,
                            hsi_filter=zhendang, max_hold_days=20)
    v_all = run_variant("b5+s2 全天候對照", B5_BUY, S2_SELL, sd,
                        hsi_filter=None, max_hold_days=None)

    # ── b19 基準 ──────────────────────────────────────────────────
    v_b19 = run_variant("b19 基準（ROC桶代表）", b19_preset["buy"], b19_preset["sell"], sd,
                        hsi_filter=None,
                        max_hold_days=b19_preset.get("max_hold_days", 20),
                        min_hold_days=b19_preset.get("min_hold_days", 5))

    # ── 總表 ──────────────────────────────────────────────────────
    print("\n" + "═" * 92)
    print("  b5+s2 區間回歸 — 三變體 + b19 基準")
    print("═" * 92)
    print(f"{'變體':<24}{'blended':>11}{'逐fold正%':>11}{'合計筆數':>10}{'判準①②':>12}")
    print("─" * 92)
    rows = [v_gate, v_gate_md, v_all, v_b19]
    for r in rows:
        b, pf = r["blended"], r["pos_fold_rate"]
        b_s = f"{b:+.2f}%" if b is not None else "N/A"
        pf_s = f"{pf:.0f}%" if pf is not None else "N/A"
        is_b5 = r["label"].startswith("b5+s2") and "全天候" not in r["label"]
        gate12 = is_b5 and (b is not None and b >= 2.0 and pf is not None and pf >= 60.0)
        mark = ("✅過" if gate12 else "✗未過") if r["label"].startswith("b5+s2") else "—基準—"
        print(f"{r['label']:<24}{b_s:>11}{pf_s:>11}{r['n_total']:>10}{mark:>12}")
    print("═" * 92)

    # ── 對照判準③：制度條件化是否產生邊 ───────────────────────────
    print("\n③ 制度條件化檢定（邊是否來自震盪市閘、而非 b5 本身）：")
    bg, ba = v_gate["blended"], v_all["blended"]
    if bg is not None and ba is not None:
        lift = bg - ba
        print(f"   震盪市閘 {bg:+.2f}%  vs  全天候 {ba:+.2f}%  → 制度提升 {lift:+.2f}pp")
        if lift > 1.0 and bg >= 2.0:
            print("   ✅ 邊明顯來自制度條件化（震盪市閘遠優於全天候）。")
        elif bg < 2.0:
            print("   ✗ 即使加閘 blended 仍 < +2%：區間回歸在此池沒站上門檻。")
        else:
            print("   ⚠️ 閘有幫助但提升有限，需看正交性是否值得。")

    # ── 判準④：對 b19 超額正交 + 逐 fold 制度關係 ──────────────────
    best_b5 = v_gate if (v_gate["blended"] or -99) >= (v_gate_md["blended"] or -99) else v_gate_md
    b5f = best_b5["fold_blended"]
    b19f = v_b19["fold_blended"]
    spans = v_b19["fold_spans"]

    hsi_fold = [_win_ret(hsi_close, d0, d1) for (d0, d1) in spans]
    raw_corr = _pearson(b5f, b19f)
    # 超額（扣 HSI 窗報酬）
    b5_ex = [(x - h) if (x is not None and h is not None) else None for x, h in zip(b5f, hsi_fold)]
    b19_ex = [(y - h) if (y is not None and h is not None) else None for y, h in zip(b19f, hsi_fold)]
    ex_corr = _pearson(b5_ex, b19_ex)

    bleed = [x for x, y in zip(b5f, b19f) if (x is not None and y is not None and y < 0)]
    bleed_mean = sum(bleed) / len(bleed) if bleed else None

    print(f"\n④ 對 b19 正交性（最佳 b5 變體：{best_b5['label']}）：")
    rc = f"{raw_corr:+.2f}" if raw_corr is not None else "N/A"
    ec = f"{ex_corr:+.2f}" if ex_corr is not None else "N/A"
    bm = f"{bleed_mean:+.2f}%" if bleed_mean is not None else "N/A"
    print(f"   原始相關 {rc}（含市場 beta）  ｜  ★超額相關 {ec}（扣 HSI beta，這個才準）")
    print(f"   b19 流血 {len(bleed)} 個 fold 時，b5 平均 {bm}")

    # ── 逐 fold 明細：制度佔比 vs 兩策略 ──────────────────────────
    print("\n   逐 fold（震盪市佔比 / HSI窗 / b19 / b5）：")
    print(f"   {'fold':<5}{'OOS起':<12}{'震盪%':>7}{'HSI窗':>9}{'b19':>9}{'b5':>9}")
    for i, (d0, d1) in enumerate(spans):
        if zhendang is not None and d0 is not None and d1 is not None:
            m = (zhendang.index >= d0) & (zhendang.index <= d1)
            zsh = zhendang[m].mean() * 100 if m.any() else float("nan")
        else:
            zsh = float("nan")
        d0s = d0.strftime("%Y-%m-%d") if d0 is not None else "?"
        h = hsi_fold[i]
        b19v = b19f[i]
        b5v = b5f[i]
        fz = f"{zsh:.0f}%" if zsh == zsh else "N/A"
        fh = f"{h:+.1f}%" if h is not None else "N/A"
        fb19 = f"{b19v:+.2f}%" if b19v is not None else "N/A"
        fb5 = f"{b5v:+.2f}%" if b5v is not None else "N/A"
        print(f"   {i+1:<5}{d0s:<12}{fz:>7}{fh:>9}{fb19:>9}{fb5:>9}")
    print("═" * 92)

    # ── 結論 ──────────────────────────────────────────────────────
    print("\n判讀：")
    bg_ok = (v_gate["blended"] is not None and v_gate["blended"] >= 2.0
             and v_gate["pos_fold_rate"] is not None and v_gate["pos_fold_rate"] >= 60.0)
    bgmd_ok = (v_gate_md["blended"] is not None and v_gate_md["blended"] >= 2.0
               and v_gate_md["pos_fold_rate"] is not None and v_gate_md["pos_fold_rate"] >= 60.0)
    if not (bg_ok or bgmd_ok):
        print("  ✗ 震盪市閘變體未過 blended≥+2% 與 逐fold正≥60%。")
        print("    → 區間回歸在此池沒站上門檻；下一條可試橫斷面相對強弱或波動率壓縮突破。")
    elif ex_corr is not None and ex_corr < 0.3 and (bleed_mean is None or bleed_mean >= 0):
        print(f"  ✅ ①②過、③制度提升明顯、④超額相關 {ec} 低且 b19 流血時 b5 不虧。")
        print("     → 找到專在震盪市賺錢、與 ROC 桶正交的 edge。下一步：精修訊號 → MC vs b19 → ⚠️輕倉 LIVE。")
    else:
        print(f"  ⚠️ ①②過但 ④超額相關 {ec}（或 b19 流血時 b5 也虧）→ 分散有限。")
        print("     先別上，檢查是否只是換個方式吃同一段市場 beta。")

    print(f"\n總耗時 {time.time() - t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

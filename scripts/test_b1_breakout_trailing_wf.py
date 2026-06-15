"""
test_b1_breakout_trailing_wf.py
── 尋找與 ROC 急跌反轉「正交」的新 edge：b1 突破動量 + 移動止損 ──

═══════════════════════════════════════════════════════════════════
為什麼要這支
═══════════════════════════════════════════════════════════════════
  V22.3 結論：現行 4 支 LIVE（b19 / b17+b6 / b15+b17 / b13+b17）全是同一個
  風險因子【ROC 超跌反轉 + 確認 + 時間出場】的不同包裝 = 非真分散。硬熊 ROC
  反轉一失效會一起回撤，故全部只能輕倉。

  真正的分散解 = 找一個與 ROC「反號」的 edge：買強勢（突破），不買弱勢（抄底）。
  b1 = 收盤突破前 20 日高 + 量 > 1.5×均量（純形態 + 量確認，2 條件，合 A3 鐵則），
  正好是抄底家族的反號，是最乾淨的正交候選。

  方法學鐵則（與抄底家族鏡像）：
    • 抄底家族的誠實出場 = 時間出場（10% 止損會在反彈前砍 = 壞出場）。
    • 動量家族的誠實出場 = 移動止損（固定超時會在趨勢未走完就砍 = 壞出場）。
    → 所以 b1 的誠實尺 = 「移動止損版 blended ≥ +2%」（不是時間版）。
    → blended 口徑與 test_b17_blended 完全相同：
        mean( in-window 策略單 回報%  ∪  邊界強制單延伸實現 回報% )，逐筆。
      （延伸追蹤套用同一移動止損規則，引擎已透傳；剝離 cohort 選擇偏誤。）

═══════════════════════════════════════════════════════════════════
三道判準（過了才值得鑄 b20 精修版 → 進 MC 閘）
═══════════════════════════════════════════════════════════════════
  ① 移動止損版 blended ≥ +2.0%                （edge 本身有沒有錢）
  ② 逐 fold 正報酬 ≥ 60%                       （非單一事件 / 過擬合）
  ③ 對 b19 逐 fold 相關係數低（理想 < +0.3）   ★真正的重點★
       且「b19 流血的 fold（blended < 0）」b1 平均 ≥ 0
       → 證明 ROC 桶回撤時 b1 能補位 = 真分散，不是再加一支同向部位。

  注意：①② 沒過 = b1 突破在港股 PIT 沒 edge（指標閾值類常如此），收掉換別的形態。
        ①② 過但 ③ 不過（與 b19 高正相關）= 賺錢但不分散，意義不大。
        三者全過 = 找到正交 edge，才進下一步（鑄 b20 精修 → max_hold/trailing 敏感度 → MC vs b19）。

使用：python scripts/test_b1_breakout_trailing_wf.py
      （投組 PIT WF，約 10-15 分鐘：4 個 trailing 檔位 + b19 基準各一輪）
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

from data import load_stocks
from historical_universe import load_eodhd_prices
from walk_forward import run_portfolio_walk_forward
from config import ACTIVE_PRESETS, B_NAMES, COMMISSION_PCT, SLIPPAGE_PCT

# ── 候選：b1 突破動量（程式化建 buy tuple，免硬編碼 19 位）──────────
B1_BUY = tuple(name == "b1" for name in B_NAMES)
B1_SELL = tuple(False for _ in range(8))   # 純移動止損出場，不掛 s2（s2=布林上軌=見強勢就賣，對動量是壞出場）
B1_MIN_HOLD = 5
TRAILING_GRID = [8, 10, 12, 15]            # 移動止損回撤 % 檔位

# ── 基準：既有 ROC 桶代表（b19，用它自己的誠實出場 = 時間20）──────
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


def _rets(trades):
    return [t["回報%"] for t in trades if t.get("回報%") is not None]


def _fold_blended(fold):
    """單一 fold 的 blended：in-window 策略單 ∪ 邊界延伸已平單，逐筆平均。"""
    rs = _rets(fold.get("oos_trades", []))
    for t in fold.get("oos_extended_trades", []):
        if not t.get("_still_held_at_end", False) and t.get("回報%") is not None:
            rs.append(t["回報%"])
    if not rs:
        return None, 0
    return sum(rs) / len(rs), len(rs)


def analyze(wf):
    """全期 blended + 逐 fold blended 序列。"""
    strat_rets, ext_closed_rets = [], []
    fold_blended = []          # 每 fold 一個 blended（None 表該 fold 無單）
    for r in wf:
        strat_rets += _rets(r.get("oos_trades", []))
        for t in r.get("oos_extended_trades", []):
            if not t.get("_still_held_at_end", False) and t.get("回報%") is not None:
                ext_closed_rets.append(t["回報%"])
        fb, _ = _fold_blended(r)
        fold_blended.append(fb)

    allr = strat_rets + ext_closed_rets
    blended = sum(allr) / len(allr) if allr else None
    wr = (sum(1 for x in allr if x > 0) / len(allr) * 100) if allr else None
    valid_folds = [x for x in fold_blended if x is not None]
    pos_fold_rate = (sum(1 for x in valid_folds if x > 0) / len(valid_folds) * 100
                     if valid_folds else None)
    return {
        "blended": blended,
        "n_total": len(allr),
        "wr": wr,
        "fold_blended": fold_blended,
        "pos_fold_rate": pos_fold_rate,
        "n_valid_folds": len(valid_folds),
    }


def run_variant(label, buy, sell, stock_data, *,
                trailing_stop_pct=None, max_hold_days=None, min_hold_days=5):
    bits = []
    if trailing_stop_pct:
        bits.append(f"移動止損 {trailing_stop_pct}%")
    if max_hold_days:
        bits.append(f"時間 {max_hold_days}日")
    print(f"\n▶ {label}  ｜ 出場：{' + '.join(bits) if bits else '（無）'}")
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
        trailing_stop_pct=trailing_stop_pct,
        max_hold_days=max_hold_days,
        min_hold_days=min_hold_days,
        track_extended=True, use_pit_universe=True, progress_cb=cb,
    )
    print(" " * 80, end="\r")
    a = analyze(wf)
    b = a["blended"]
    pf = a["pos_fold_rate"]
    wr = a["wr"]
    b_s = f"{b:+.2f}%" if b is not None else "N/A"
    pf_s = f"{pf:.0f}%" if pf is not None else "N/A"
    wr_s = f"{wr:.1f}%" if wr is not None else "N/A"
    print(f"  ✓ {time.time() - t0:.1f}s")
    print(f"    blended {b_s}  ｜ 逐fold正報酬 {pf_s} ({a['n_valid_folds']} 有效fold)"
          f"  ｜ 合計 {a['n_total']} 筆  ｜ 勝率 {wr_s}")
    return {"label": label, **a}


def _pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 2:
        return None
    px = [p[0] for p in pairs]
    py = [p[1] for p in pairs]
    try:
        return statistics.correlation(px, py)
    except Exception:
        return None


def orthogonality(b1_row, b19_row):
    """b1 對 b19 的逐 fold 正交性檢定。"""
    b1f = b1_row["fold_blended"]
    b19f = b19_row["fold_blended"]
    corr = _pearson(b1f, b19f)

    # b19 流血的 fold（blended < 0）裡 b1 的表現
    b1_when_b19_bleeds = [
        x for x, y in zip(b1f, b19f)
        if (x is not None and y is not None and y < 0)
    ]
    bleed_mean = (sum(b1_when_b19_bleeds) / len(b1_when_b19_bleeds)
                  if b1_when_b19_bleeds else None)
    return corr, bleed_mean, len(b1_when_b19_bleeds)


def main():
    t_start = time.time()
    print("═" * 92)
    print("  b1 突破動量 + 移動止損：尋找與 ROC 急跌反轉正交的新 edge")
    print("  誠實尺 = 移動止損版 blended ≥ +2%（動量家族的正確出場）；重點 = 對 b19 正交性")
    print("═" * 92)

    if B19_KEY not in ACTIVE_PRESETS:
        print(f"❌ 找不到基準 preset {B19_KEY}")
        return 1
    b19_preset = ACTIVE_PRESETS[B19_KEY]

    tickers = load_stocks()
    print(f"\nstocks.txt {len(tickers)} 隻；載入 EODHD…")
    sd, skipped = build_stock_data(tickers)
    print(f"已載入 {len(sd)} 隻（跳過 {skipped}）")
    if len(sd) < 10:
        print("❌ 可用股票太少")
        return 1

    # ① b1 突破 × trailing 檔位
    b1_rows = []
    for tp in TRAILING_GRID:
        b1_rows.append(
            run_variant(f"b1 突破 / 移動止損{tp}%", B1_BUY, B1_SELL, sd,
                        trailing_stop_pct=tp, max_hold_days=None,
                        min_hold_days=B1_MIN_HOLD)
        )

    # ② b19 基準（用它自己的誠實出場：時間20）
    b19_row = run_variant("b19 基準 / 時間20日（ROC 桶代表）",
                          b19_preset["buy"], b19_preset["sell"], sd,
                          trailing_stop_pct=None,
                          max_hold_days=b19_preset.get("max_hold_days", 20),
                          min_hold_days=b19_preset.get("min_hold_days", 5))

    # ── 總表 ──────────────────────────────────────────────────────
    print("\n" + "═" * 92)
    print("  b1 突破動量 — 各 trailing 檔位 vs 三道判準")
    print("═" * 92)
    print(f"{'出場':<22}{'blended':>11}{'逐fold正%':>11}{'合計筆數':>10}{'判準①②':>12}")
    print("─" * 92)
    best = None
    for r in b1_rows:
        b, pf = r["blended"], r["pos_fold_rate"]
        b_s = f"{b:+.2f}%" if b is not None else "N/A"
        pf_s = f"{pf:.0f}%" if pf is not None else "N/A"
        gate12 = (b is not None and b >= 2.0 and pf is not None and pf >= 60.0)
        mark = "✅過" if gate12 else "✗未過"
        print(f"{r['label']:<22}{b_s:>11}{pf_s:>11}{r['n_total']:>10}{mark:>12}")
        if gate12 and (best is None or (r['blended'] or -99) > (best['blended'] or -99)):
            best = r
    print("═" * 92)

    # ── 正交性檢定（重點）──────────────────────────────────────────
    print("\n" + "═" * 92)
    print("  ★ 正交性檢定：b1 突破 vs b19 ROC 桶（逐 fold 對齊）★")
    print("═" * 92)
    for r in b1_rows:
        corr, bleed_mean, n_bleed = orthogonality(r, b19_row)
        corr_s = f"{corr:+.2f}" if corr is not None else "N/A"
        bleed_s = f"{bleed_mean:+.2f}%" if bleed_mean is not None else "N/A"
        verdict = ""
        if corr is not None:
            if corr < 0.3:
                verdict = "→ 低相關，具分散潛力"
            elif corr < 0.6:
                verdict = "→ 中度相關，分散有限"
            else:
                verdict = "→ 高相關，幾乎同向（非真分散）"
        print(f"  {r['label']:<22} 相關 {corr_s:>6}   "
              f"b19流血{n_bleed}個fold時 b1 平均 {bleed_s:>8}   {verdict}")
    print("═" * 92)

    # ── 結論 ──────────────────────────────────────────────────────
    print("\n判讀：")
    if best is None:
        print("  ✗ 無任何 trailing 檔位同時過 blended≥+2% 與 逐fold正≥60%。")
        print("    → b1 突破在港股 PIT 沒有可保留的 edge（與 b17 單獨類似），")
        print("      收掉這條，改試別的形態（如波動率壓縮突破 / 橫斷面相對強弱）。")
    else:
        corr, bleed_mean, n_bleed = orthogonality(best, b19_row)
        corr_s = f"{corr:+.2f}" if corr is not None else "N/A"
        b_s = f"{best['blended']:+.2f}%"
        print(f"  ✅ ①② 過關最佳檔位：{best['label']}（blended {b_s}）。")
        if corr is not None and corr < 0.3 and (bleed_mean is None or bleed_mean >= 0):
            print(f"  ✅ ③ 對 b19 相關 {corr_s} 低且 b19 流血時 b1 不虧 → 真正交 edge。")
            print("     下一步：鑄 b20 精修突破訊號 → trailing/max_hold 敏感度 → MC vs b19 → ⚠️輕倉 LIVE。")
        else:
            print(f"  ⚠️ ③ 對 b19 相關 {corr_s}（或流血 fold b1 也虧）→ 賺錢但分散有限，")
            print("     意義不大；先別鑄 b20，回頭調突破定義或換 edge。")

    print(f"\n總耗時 {time.time() - t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

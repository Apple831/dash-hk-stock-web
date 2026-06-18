"""
test_cross_sectional_rs_wf.py
── 路徑 B：橫斷面相對強弱（cross-sectional relative strength）──
  long-only 唯一還沒試、結構上真的與 ROC 急跌反轉正交的因子。

═══════════════════════════════════════════════════════════════════
為什麼是這支（承 HANDOVER31/32 的「單一因子」硬結論）
═══════════════════════════════════════════════════════════════════
  b1 突破 = 偽 beta；b5 區間回歸 = 與 b19 同因子（扣 HSI beta 後超額相關 +0.97）。
  → 在「long-only ＋ 單股 ＋ 自己看自己」這個盒子裡只有一個有效因子：超賣反轉。
  任何「重新量測自己跌多少」的新訊號都會撞回 b19。

  唯一沒試過、資訊維度真的不同的 = 橫斷面相對強弱：
    不看「這隻自己跌多少」，看「這隻在全池裡排第幾」。
  ★方向很關鍵★
    • RS 動量（買相對最強 top-K%）＝ 與「買跌」反號 → 結構正交，這才是真測試。
    • RS 反轉（買相對最弱 bot-K%）＝ 約等於買跌 → 預期撞回 b19（放對照組證明它崩）。

═══════════════════════════════════════════════════════════════════
注入方式（核心檔一律不碰；全在本進程 monkey-patch）
═══════════════════════════════════════════════════════════════════
  難點：use_pit_universe=True 時，walk_forward fold 迴圈用 load_eodhd_prices(tkr)
  「重新載入」每隻 PIT 股 → 預掛在 sd 上的欄位會被丟掉。
  解法：
    1. 先用全池 EODHD 收盤建「每日 LB 日報酬的橫斷面百分位」面板（無前視：date t
       只用 ≤t 的收盤；未上市股當日 NaN→自動排除，天然 PIT 乾淨）。
    2. patch walk_forward.load_eodhd_prices：載入後把該股的 _rs_pct 當欄位掛回 df。
    3. patch precompute_signals（_wf 與 _bt 都要）：讀 df["_rs_pct"]，依方向算
       eligibility，覆寫【已廢棄的 b1 突破槽】→ 跑 buy=只選 b1 = 純 RS 進場訊號。
       （沿用 test_b17_regime_intensity 的覆寫槽手法，不動組合邏輯、不碰 tuple 結構。）
  ⚠️ PIT 近似：排名橫斷面 = 「當日有足夠歷史的所有股」，未再套 min_turnover/min_price
     的每日過濾（引擎已在 fold 層用 PIT 池限制可交易標的）。對首輪正交性篩選足夠；
     若 RS 出現邊、精修時再收緊橫斷面到逐日 PIT 池。

═══════════════════════════════════════════════════════════════════
判準（過了才精修 → MC vs b19 → 輕倉 LIVE）
═══════════════════════════════════════════════════════════════════
  ① blended ≥ +2.0%（同升 LIVE 硬尺；動量家族誠實出場＝移動止損，故主測 trailing）
  ② 正 fold 比率 ≥ 60%
  ③ ★最關鍵★ 對 b19 的【超額相關】低（每 fold 報酬扣掉 HSI 窗報酬的市場 beta 後）：
       低（< +0.5）→ 疑似真正交 edge（本帳第一個！）
       高（≥ +0.5）→ RS 動量也塌回超賣反轉 → 實證「本帳只有一個因子、收工」
     對照組 RS 反轉預期超額相關高（≈ 證明買弱＝買跌）。

使用：python scripts/test_cross_sectional_rs_wf.py
      （PIT 投組 WF：b19 基準 + 4 個 RS 變體，各一輪，約 25-35 分鐘）
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
import indicators as _ind
import backtest as _bt
import walk_forward as _wf
from data import load_stocks, get_cached
from walk_forward import run_portfolio_walk_forward
from config import ACTIVE_PRESETS, COMMISSION_PCT, SLIPPAGE_PCT

# ── 透傳給引擎的 preset 欄位 ──────────────────────────────────────
PASS_KW = ("stop_loss_pct", "take_profit_pct", "max_hold_days",
           "min_hold_days", "cooldown_days", "trailing_stop_pct")

# ── b1..b19 / s1..s8 tuple 工具（不動結構，只程式化建選擇）────────
B_IDX = {f"b{i + 1}": i for i in range(19)}
SELL_NONE = tuple([False] * 8)   # 無策略訊號出場 → 只靠 trailing / 超時（動量家族誠實出場）


def make_buy(*names):
    t = [False] * 19
    for nme in names:
        t[B_IDX[nme]] = True
    return tuple(t)


# ── 候選網格（top=20% quintile；方向 mom=買最強 / rev=買最弱對照）──
GRID = [
    {"name": "RS動量 top20 LB60 移動止損12%",  "lb": 60,  "top": 0.20, "side": "mom",
     "exit": {"trailing_stop_pct": 12.0}},
    {"name": "RS動量 top20 LB60 超時20日",      "lb": 60,  "top": 0.20, "side": "mom",
     "exit": {"max_hold_days": 20}},
    {"name": "RS動量 top20 LB120 移動止損12%", "lb": 120, "top": 0.20, "side": "mom",
     "exit": {"trailing_stop_pct": 12.0}},
    {"name": "RS反轉 bot20 LB60 超時20日(對照)", "lb": 60,  "top": 0.20, "side": "rev",
     "exit": {"max_hold_days": 20}},
]

# ══════════════════════════════════════════════════════════════════
# 原函式備份 + 可變設定 cell（monkey-patch 用）
# ══════════════════════════════════════════════════════════════════
_ORIG_PRE = _ind.precompute_signals
_ORIG_LOAD = _wf.load_eodhd_prices     # fold 迴圈內呼叫的就是 walk_forward 命名空間這顆
_RS_CFG = {"lb": 60, "top": 0.20, "side": "mom"}
PANELS = {}                            # {lb: rank_pct DataFrame(columns=ticker)}


def _patched_load(ticker):
    """載入後把該股當日 RS 百分位掛成 df['_rs_pct']（PIT 分支用的就是這顆）。"""
    df = _ORIG_LOAD(ticker)
    if df is None or df.empty:
        return df
    panel = PANELS.get(_RS_CFG["lb"])
    if panel is not None and ticker in panel.columns:
        df = df.copy()
        df["_rs_pct"] = panel[ticker].reindex(df.index)
    return df


def _patched_pre(df, hsi_bullish=True):
    """覆寫已廢棄的 b1 槽 = 純 RS eligibility（依方向取 top / bottom 分位）。"""
    sigs = _ORIG_PRE(df, hsi_bullish)
    if "_rs_pct" in df.columns:
        pct = df["_rs_pct"]
        top = _RS_CFG["top"]
        if _RS_CFG["side"] == "mom":
            elig = (pct >= (1.0 - top))
        else:
            elig = (pct <= top)
        elig = elig.fillna(False)
    else:
        elig = pd.Series(False, index=df.index)
    if len(elig) > 61:
        elig.iloc[:61] = False          # 與引擎一致的 warmup（MA60 暖機）
    sigs["b1"] = elig
    return sigs


def install_patches():
    _wf.load_eodhd_prices = _patched_load
    _wf.precompute_signals = _patched_pre
    _bt.precompute_signals = _patched_pre


# ══════════════════════════════════════════════════════════════════
# 橫斷面 RS 面板（無前視；NaN = 未上市/歷史不足 → 自動排除）
# ══════════════════════════════════════════════════════════════════
def build_panels(lbs):
    closes, loaded = {}, {}
    for tkr in load_stocks():
        df = _ORIG_LOAD(tkr)
        if df is None or df.empty or len(df) < 62:
            continue
        loaded[tkr] = df
        closes[tkr] = df["Close"]
    wide = pd.DataFrame(closes).sort_index()
    for lb in lbs:
        ret = wide / wide.shift(lb) - 1.0          # date t 只用 ≤t 收盤
        PANELS[lb] = ret.rank(axis=1, pct=True)     # 橫斷面百分位；NaN 保持 NaN
        med_n = int(ret.notna().sum(axis=1).replace(0, pd.NA).dropna().median() or 0)
        print(f"  LB{lb}：橫斷面每日中位數約 {med_n} 隻可排名")
    return loaded


def _preset_kwargs(preset):
    return {k: preset[k] for k in PASS_KW if k in preset and preset[k] is not None}


# ══════════════════════════════════════════════════════════════════
# 跑一支策略 → blended + 逐 fold（供超額相關）
# ══════════════════════════════════════════════════════════════════
def _fold_cohort(r):
    c = [t["回報%"] for t in r.get("oos_trades", []) if t.get("回報%") is not None]
    c += [t["回報%"] for t in r.get("oos_extended_trades", [])
          if (not t.get("_still_held_at_end", False)) and t.get("回報%") is not None]
    return c


def run_strategy(name, buy, sell, exit_kw, sd):
    print(f"\n▶ {name}  全天候 PIT WF…")
    t0 = time.time()
    last = [0.0]

    def cb(f, tot, tk):
        now = time.time()
        if now - last[0] > 1.0:
            print(f"    fold {f}/{tot}  {tk}", end="\r", flush=True)
            last[0] = now

    wf = run_portfolio_walk_forward(
        sd, buy_sigs=buy, sell_sigs=sell,
        is_months=12, oos_months=6, trade_size=100_000,
        slippage=SLIPPAGE_PCT, commission_pct=COMMISSION_PCT,
        hsi_filter=None, track_extended=True, use_pit_universe=True,
        progress_cb=cb, **exit_kw,
    )
    print(" " * 80, end="\r")

    blended, folds, pos, tot = [], [], 0, 0
    for r in wf:
        in_win = [t["回報%"] for t in r.get("oos_trades", []) if t.get("回報%") is not None]
        cohort = _fold_cohort(r)
        blended += cohort
        if len(cohort) >= 5:
            tot += 1
            if sum(cohort) / len(cohort) > 0:
                pos += 1
        if len(in_win) >= 5:   # 逐 fold OOS 均報酬（供扣 beta 超額相關）
            folds.append((sum(in_win) / len(in_win),
                          pd.Timestamp(r["oos_start"]), pd.Timestamp(r["oos_end"])))
    bm = sum(blended) / len(blended) if blended else None
    pfr = pos / tot * 100 if tot else None
    print(f"  ✓ {time.time() - t0:.1f}s  ｜ blended {len(blended)} 筆"
          f"  ｜ 均 {('%+.2f%%' % bm) if bm is not None else 'N/A'}")
    return {"name": name, "blended_mean": bm, "blended_n": len(blended),
            "folds": folds, "pfr": pfr, "pos": pos, "tot": tot}


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / ((sxx ** 0.5) * (syy ** 0.5))


def excess_corr(var_folds, b19_folds, hsi):
    """每 fold 扣 HSI 窗報酬後，RS 與 b19 的超額相關（扣共同市場 beta）。"""
    b19map = {f[1]: f[0] for f in b19_folds}
    xs, ys = [], []
    for vm, os_, oe in var_folds:
        if os_ not in b19map:
            continue
        if hsi is not None:
            try:
                hret = (hsi.asof(oe) / hsi.asof(os_) - 1) * 100
            except Exception:
                hret = 0.0
        else:
            hret = 0.0
        xs.append(vm - hret)
        ys.append(b19map[os_] - hret)
    return _pearson(xs, ys), len(xs)


def verdict_rs(res, corr, is_control=False):
    bm, pfr = res["blended_mean"], res["pfr"]
    if is_control:
        cs = f"{corr:+.2f}" if corr is not None else "N/A"
        return f"（對照）blended {('%+.2f%%' % bm) if bm is not None else 'N/A'}、對 b19 超額相關 {cs}"
    if bm is None:
        return "⚠️ 無交易，無法判定（RS 進場可能太稀）"
    if bm < 2.0:
        return f"🔴 blended {bm:+.2f}% < +2% → RS 此參數無邊"
    cs = f"{corr:+.2f}" if corr is not None else "N/A"
    if corr is not None and corr >= 0.5:
        return (f"🟡 blended {bm:+.2f}% 過 +2%，但對 b19 超額相關 {cs} 偏高 → "
                f"與超賣反轉重疊、非真分散（疑似同因子）")
    return (f"🟢 blended {bm:+.2f}%、對 b19 超額相關 {cs} 低、正 fold {pfr:.0f}% → "
            f"疑似真正交 edge，值得精修 → MC vs b19 → 輕倉 LIVE")


def main():
    t_start = time.time()
    print("═" * 92)
    print("  路徑 B：橫斷面相對強弱（唯一未試、結構正交的 long-only 因子）")
    print("═" * 92)

    lbs = sorted({g["lb"] for g in GRID})
    print(f"\n建立橫斷面 RS 面板（LB={lbs}）…")
    sd = build_panels(lbs)
    print(f"已載入 {len(sd)} 隻")
    if len(sd) < 20:
        print("❌ 可用股票太少")
        return 1

    print("\n載入 ^HSI（扣 beta 用）…")
    hsi_raw = get_cached("^HSI", "5y")
    hsi = hsi_raw["Close"].sort_index() if (hsi_raw is not None and not hsi_raw.empty) else None
    print("  ✓ HSI 就緒" if hsi is not None else "  ⚠️ 無 HSI，超額相關退化為原始相關")

    # ── b19 基準（先跑、未 patch，乾淨）──────────────────────────
    b19_key = next((k for k in ACTIVE_PRESETS if "b19" in k), None)
    if b19_key is None:
        print("❌ 找不到 b19 基準")
        return 1
    print(f"\n=== 基準 b19（{b19_key}）===")
    b19 = run_strategy(b19_key, ACTIVE_PRESETS[b19_key]["buy"],
                       ACTIVE_PRESETS[b19_key]["sell"],
                       _preset_kwargs(ACTIVE_PRESETS[b19_key]), sd)

    # ── 裝 patch，跑 RS 變體 ────────────────────────────────────
    install_patches()
    buy_rs = make_buy("b1")            # 純 RS（覆寫 b1 槽）
    results = []
    for g in GRID:
        _RS_CFG.update(lb=g["lb"], top=g["top"], side=g["side"])
        res = run_strategy(g["name"], buy_rs, SELL_NONE, g["exit"], sd)
        corr, nf = excess_corr(res["folds"], b19["folds"], hsi)
        res["corr"], res["nf"], res["is_control"] = corr, nf, (g["side"] == "rev")
        results.append(res)

    # ── 總表 ─────────────────────────────────────────────────────
    print("\n" + "═" * 92)
    print("  結果（blended ＝ in-window ∪ 邊界延伸已平單；超額相關 ＝ 扣 HSI 窗報酬後對 b19）")
    print("═" * 92)
    bm19 = f"{b19['blended_mean']:+.2f}%" if b19["blended_mean"] is not None else "N/A"
    print(f"  基準 b19：blended {bm19}（{b19['blended_n']} 筆，正 fold "
          f"{b19['pos']}/{b19['tot']}）")
    print(f"  {'變體':<30}{'blended':>10}{'正fold':>9}{'超額相關vs b19':>16}{'筆數':>8}")
    print("  " + "─" * 76)
    for res in results:
        bm = f"{res['blended_mean']:+.2f}%" if res["blended_mean"] is not None else "N/A"
        pf = f"{res['pos']}/{res['tot']}" if res["tot"] else "N/A"
        cs = f"{res['corr']:+.2f}" if res["corr"] is not None else "N/A"
        print(f"  {res['name']:<30}{bm:>10}{pf:>9}{cs:>16}{res['blended_n']:>8}")

    # ── 判讀 ─────────────────────────────────────────────────────
    print("\n" + "═" * 92)
    print("  判讀")
    print("═" * 92)
    for res in results:
        print(f"\n  {res['name']}")
        print(f"      {verdict_rs(res, res['corr'], res['is_control'])}")

    print("\n  ── 整體 ──")
    moms = [r for r in results if not r["is_control"]]
    good = [r for r in moms if r["blended_mean"] is not None and r["blended_mean"] >= 2.0
            and (r["corr"] is None or r["corr"] < 0.5)]
    if good:
        print("  🟢 有 RS 動量變體同時過 +2% 且超額相關低 → 本帳可能有第二個因子！")
        print("     下一步：精修參數 → test_mc_candidates vs b19 → 過了輕倉 LIVE。")
    elif any(r["blended_mean"] is not None and r["blended_mean"] >= 2.0 for r in moms):
        print("  🟡 RS 動量有 +2% 的變體，但超額相關偏高 → 邊與超賣反轉重疊，非真分散。")
    else:
        print("  🔴 RS 動量全未過 +2%。若對照組 RS 反轉超額相關又高 → 實證")
        print("     『long-only 此池只有超賣反轉一個因子』，分散須走制度曝險管理（已上線的震盪市閘）")
        print("     或結構性換盒子（多空 / 配對 / 事件驅動），非再加 long-only 訊號。")
    print("═" * 92)
    print(f"\n總耗時 {time.time() - t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

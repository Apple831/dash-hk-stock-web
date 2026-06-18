"""
test_bear_scope_wf.py
── 三搶救策略的「熊市 scope」episode 集中度驗證（路徑 A 決策腳本）──
  決定 b17+b6 / b15+b17 / b13+b17 能不能加進 BEAR_EXEMPT_PRESETS。

═══════════════════════════════════════════════════════════════════
為什麼跑這支（承 HANDOVER32 / 制度曝險疊加(A) 的附帶發現）
═══════════════════════════════════════════════════════════════════
  制度疊加分桶顯示：LIVE 四支在 🔴 熊市 cohort 都很肥（合併 +4.41%），其中三支
  搶救策略（b17+b6 / b15+b17 / b13+b17）在硬熊日（BEAR_LABELS_HARD = 強熊市/弱熊市）
  目前被 daily_scan 熊市閘門「停掃」（BEAR_EXEMPT_PRESETS 只有 b19）
  → 每個硬熊日都把它們關在門外，可能漏掉它們最賺的制度。

  ★ 但鐵則：勿單憑桶聚合放行。★
  b19 的熊市 alpha 本就 episode 集中（強熊市 266 筆 ≈ 2-3 episode、有效獨立事件個位數），
  我們當初是用「輕倉 + 熊市豁免」才接受它的。這三支的 +4~6% 很可能也是少數幾段
  暴跌反彈撐起來的幻覺；若是，硬熊停掃反而是對的。

═══════════════════════════════════════════════════════════════════
本腳本怎麼測（沿用 overlay 腳本的 blended cohort 機制，只多量集中度）
═══════════════════════════════════════════════════════════════════
  對 b19（基準/已豁免）+ 三支搶救策略各跑一次全天候投組 WF，收集 blended cohort
  （in-window oos_trades ∪ 邊界延伸已平單），逐筆貼【進場日的 HSI 制度 label】，
  抽出【硬熊 cohort】（label ∈ BEAR_LABELS_HARD），量四件事：

    ① cohort 平均報酬           要 ≥ +2.0% 才有資格談（同升 LIVE 的硬尺）
    ② episode 集中度            把硬熊交易按進場日聚成 episode（相鄰兩筆間隔 > GAP_DAYS
                                = 換一個 episode），報有效獨立事件數
                                N_eff = (Σnᵢ)² / Σnᵢ²（inverse-HHI；越小越集中）
    ③ 剔最賺 episode 後 cohort   把貢獻最大的那段暴跌反彈整段拿掉，看 cohort 是否仍站得住
                                （＝ b19「剔除 2022 後仍 ≈+1.8%」式的單一事件依賴檢查）
    ④ 含硬熊交易的 fold 正報酬率  是否跨多個 fold 而非單一 fold 撐起

═══════════════════════════════════════════════════════════════════
判讀（最終 BEAR_EXEMPT_PRESETS 決定權在 Ivan）
═══════════════════════════════════════════════════════════════════
  把 b19 當作「已接受的 episode 集中基準線」。某支搶救策略：
    🟢 可比照 b19 加入豁免（輕倉）：cohort ≥ +2%、N_eff 不比 b19 更集中、
        剔最賺後仍 ≥ 0、含硬熊 fold 過半為正。
    🟡 邊際：cohort ≥ +2% 但集中度接近 b19 下緣 → 加也只能比照 b19（輕倉 + 同風險等級看待）。
    🔴 不建議：cohort < +2%、或剔最賺後崩 → 硬熊停掃是對的，別加。
  ⚠️ 全部都是「進場閘層」cohort（逐筆獨立、無資金佔用偏差），等價於 production
     端硬熊日放它們進場推播後的真實期望。

使用：python scripts/test_bear_scope_wf.py   （約 17-20 分鐘，4 支各一輪全天候 WF）
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
from config import (
    ACTIVE_PRESETS, LIVE_PRESET_KEYS, BEAR_EXEMPT_PRESETS,
    BEAR_LABELS_HARD, COMMISSION_PCT, SLIPPAGE_PCT,
)

# ── 透傳給引擎的 preset 欄位（與 overlay / test_* 腳本一致）───────────
PASS_KW = ("stop_loss_pct", "take_profit_pct", "max_hold_days",
           "min_hold_days", "cooldown_days", "trailing_stop_pct")

# ── episode 聚類門檻：相鄰兩筆進場日間隔 > 此天數 = 換一個 episode ───
GAP_DAYS = 20
# ── 判定門檻 ─────────────────────────────────────────────────────
MEAN_FLOOR = 2.0      # cohort 平均報酬硬尺（同升 LIVE）
MIN_HARD_TRADES = 30  # 硬熊樣本下限（低於此統計不可信）
MIN_FOLD_BEAR = 3     # 一個 fold 至少含幾筆硬熊交易才納入「fold 正報酬率」
NEFF_FLOOR = 3.0      # 有效獨立事件數絕對下限（個位數中再低就是 2-3 段幻覺）


# ══════════════════════════════════════════════════════════════════
# HSI 每日制度 label 序列（無前視：asof 取 ≤ 進場日的最後已知 label）
# ══════════════════════════════════════════════════════════════════
def build_regime_label_series():
    hsi = get_cached("^HSI", "5y")
    if hsi is None or hsi.empty:
        print("⚠️ 無法取得 ^HSI，硬熊分桶無法進行")
        return None
    hsi = calculate_indicators(hsi)
    hist = regime_history(hsi, n_bars=len(hsi))
    if not hist:
        return None
    ser = pd.Series({r["date"]: r["label"] for r in hist}).sort_index()
    hard_days = ser.map(lambda x: x in BEAR_LABELS_HARD).sum()
    print(f"  ^HSI {len(ser)} 日；其中硬熊（{'/'.join(sorted(BEAR_LABELS_HARD))}）"
          f"{hard_days} 日（{hard_days / len(ser) * 100:.0f}%）")
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
    """跑一次全天候 WF，回傳 blended cohort 的 (進場日Timestamp, 回報%, fold序) list。"""
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
    for fi, r in enumerate(wf):
        for t in r.get("oos_trades", []):
            if t.get("回報%") is not None:
                trades.append((pd.Timestamp(t["買入日期"]), t["回報%"], fi))
        for t in r.get("oos_extended_trades", []):
            if not t.get("_still_held_at_end", False) and t.get("回報%") is not None:
                trades.append((pd.Timestamp(t["買入日期"]), t["回報%"], fi))
    print(f"  ✓ {time.time() - t0:.1f}s  ｜ {len(trades)} 筆 blended cohort")
    return trades


def tag_trades(trades, label_ser):
    """每筆貼上進場日的制度 label → (ts, ret, label, fold)。"""
    tagged = []
    for ts, ret, fi in trades:
        lab = None
        if label_ser is not None:
            try:
                v = label_ser.asof(ts)
                lab = v if isinstance(v, str) else None
            except Exception:
                lab = None
        tagged.append((ts, ret, lab, fi))
    return tagged


def _stat(rets):
    if not rets:
        return None, 0, None
    n = len(rets)
    mean = sum(rets) / n
    wr = sum(1 for x in rets if x > 0) / n * 100
    return mean, n, wr


def cluster_episodes(pairs, gap_days=GAP_DAYS):
    """pairs: [(ts, ret), …]（未排序）→ 依進場日聚成 episode（相鄰間隔 > gap_days 換段）。
    回 list[ list[(ts, ret)] ]，已按時間排序。"""
    if not pairs:
        return []
    sp = sorted(pairs, key=lambda x: x[0])
    episodes, cur, prev = [], [], None
    for ts, ret in sp:
        if prev is not None and (ts - prev).days > gap_days:
            episodes.append(cur)
            cur = []
        cur.append((ts, ret))
        prev = ts
    if cur:
        episodes.append(cur)
    return episodes


def analyze_hard_bear(name, tagged):
    """抽硬熊 cohort，量 ①平均 ②N_eff ③剔最賺 episode 後平均 ④含硬熊 fold 正報酬率。"""
    hard = [(t[0], t[1], t[3]) for t in tagged if t[2] in BEAR_LABELS_HARD]
    mean, n, wr = _stat([x[1] for x in hard])

    metrics = {
        "name": name, "mean": mean, "n": n, "wr": wr,
        "n_eff": 0.0, "n_episodes": 0, "mean_drop": None,
        "drop_label": "", "fold_pos_rate": None, "fold_pos": 0, "fold_tot": 0,
        "episodes": [],
    }
    if n == 0:
        return metrics

    # ── episode 集中度 ───────────────────────────────────────────
    eps = cluster_episodes([(ts, ret) for ts, ret, _ in hard])
    counts = [len(e) for e in eps]
    tot = sum(counts)
    metrics["n_episodes"] = len(eps)
    metrics["n_eff"] = (tot * tot) / sum(c * c for c in counts) if counts else 0.0

    ep_rows = []
    for e in eps:
        ts0, ts1 = e[0][0], e[-1][0]
        ep_rets = [r for _, r in e]
        em, en, _ = _stat(ep_rets)
        contrib = sum(ep_rets)            # 該段對 cohort 總和的貢獻
        ep_rows.append((ts0, ts1, en, em, contrib))
    metrics["episodes"] = ep_rows

    # ── 剔「貢獻最大」episode 後，cohort 是否仍站得住 ─────────────
    imax = max(range(len(eps)), key=lambda j: sum(r for _, r in eps[j]))
    remaining = [r for j, e in enumerate(eps) if j != imax for _, r in e]
    md, _, _ = _stat(remaining)
    metrics["mean_drop"] = md
    r0, r1, _, _, _ = ep_rows[imax]
    metrics["drop_label"] = f"{r0.date()}~{r1.date()}"

    # ── 含硬熊交易的 fold 正報酬率 ───────────────────────────────
    by_fold = {}
    for ts, ret, fi in hard:
        by_fold.setdefault(fi, []).append(ret)
    qualifying = {fi: rs for fi, rs in by_fold.items() if len(rs) >= MIN_FOLD_BEAR}
    if qualifying:
        pos = sum(1 for rs in qualifying.values() if sum(rs) / len(rs) > 0)
        metrics["fold_pos"] = pos
        metrics["fold_tot"] = len(qualifying)
        metrics["fold_pos_rate"] = pos / len(qualifying) * 100
    return metrics


def print_metrics(m, is_benchmark=False):
    tag = "（基準 / 已豁免）" if is_benchmark else ""
    print(f"\n{m['name']} {tag}")
    if m["n"] == 0:
        print("    硬熊 cohort 0 筆（此池無硬熊進場）")
        return
    mean_s = f"{m['mean']:+.2f}%" if m["mean"] is not None else "N/A"
    wr_s = f"{m['wr']:.0f}%" if m["wr"] is not None else "N/A"
    drop_s = f"{m['mean_drop']:+.2f}%" if m["mean_drop"] is not None else "N/A"
    fr_s = (f"{m['fold_pos_rate']:.0f}% ({m['fold_pos']}/{m['fold_tot']})"
            if m["fold_pos_rate"] is not None else "N/A（無 fold 達門檻）")
    print(f"    硬熊 cohort 平均報酬 : {mean_s}   勝率 {wr_s}   筆數 {m['n']}")
    print(f"    episode 段數         : {m['n_episodes']}   "
          f"有效獨立事件 N_eff = {m['n_eff']:.1f}")
    print(f"    剔最賺 episode 後平均 : {drop_s}   （剔掉 {m['drop_label']} 那段）")
    print(f"    含硬熊 fold 正報酬率  : {fr_s}")
    if m["episodes"]:
        print(f"    ── episode 明細（gap>{GAP_DAYS}日換段）──")
        for ts0, ts1, en, em, contrib in m["episodes"]:
            em_s = f"{em:+.2f}%" if em is not None else "N/A"
            print(f"       {ts0.date()} ~ {ts1.date()}  "
                  f"{en:>4} 筆  平均 {em_s}  總貢獻 {contrib:+.1f}")


def verdict(c, b):
    """c=候選 metrics, b=b19 基準 metrics。回 (符號, 文字)。"""
    if c["n"] < MIN_HARD_TRADES:
        return "⚠️", (f"硬熊樣本僅 {c['n']} 筆（< {MIN_HARD_TRADES}）統計不可信 → "
                     f"傾向不加，需更多硬熊樣本才能判定")
    ok_mean = c["mean"] is not None and c["mean"] >= MEAN_FLOOR
    neff_bar = max(NEFF_FLOOR, b["n_eff"] * 0.8) if b["n_eff"] else NEFF_FLOOR
    ok_neff = c["n_eff"] >= neff_bar
    ok_drop = c["mean_drop"] is not None and c["mean_drop"] >= 0.0
    ok_fold = c["fold_pos_rate"] is not None and c["fold_pos_rate"] >= 50.0

    fails = []
    if not ok_mean:
        fails.append(f"cohort {c['mean']:+.2f}% < +{MEAN_FLOOR:.0f}%")
    if not ok_drop:
        md = "N/A" if c["mean_drop"] is None else f"{c['mean_drop']:+.2f}%"
        fails.append(f"剔最賺後 {md}（單一事件依賴）")
    if not ok_neff:
        fails.append(f"N_eff {c['n_eff']:.1f} 比 b19({b['n_eff']:.1f}) 更集中")
    if not ok_fold:
        fr = "N/A" if c["fold_pos_rate"] is None else f"{c['fold_pos_rate']:.0f}%"
        fails.append(f"含硬熊 fold 正報酬率 {fr} < 50%")

    if ok_mean and ok_drop and ok_neff and ok_fold:
        return "🟢", "cohort 站得住、剔最賺後仍正、集中度不劣於 b19、跨 fold → 可比照 b19 加入豁免（輕倉）"
    if ok_mean and ok_drop and not ok_neff:
        return "🟡", ("cohort 與穩健性過關，但集中度接近/略劣於 b19 → 加也只能比照 b19"
                     "（輕倉 + 同 episode 集中風險等級看待）")
    return "🔴", "硬熊停掃是對的，別加。原因：" + "；".join(fails)


def main():
    t_start = time.time()
    print("═" * 92)
    print("  三搶救策略熊市 scope：episode 集中度驗證（決定能否加進 BEAR_EXEMPT_PRESETS）")
    print(f"  硬熊定義 BEAR_LABELS_HARD = {sorted(BEAR_LABELS_HARD)}")
    print("═" * 92)

    print("\n建立 HSI 每日制度 label 序列…")
    label_ser = build_regime_label_series()
    if label_ser is None:
        print("❌ 無制度序列，無法分桶")
        return 1

    live = [k for k in LIVE_PRESET_KEYS if k in ACTIVE_PRESETS]
    benchmark = sorted(k for k in live if k in BEAR_EXEMPT_PRESETS)   # b19
    candidates = sorted(k for k in live if k not in BEAR_EXEMPT_PRESETS)  # 三搶救
    print(f"\n基準（已豁免）{len(benchmark)} 支：")
    for k in benchmark:
        print(f"  • {k}")
    print(f"候選（待決定）{len(candidates)} 支：")
    for k in candidates:
        print(f"  • {k}")
    if not benchmark:
        print("⚠️ BEAR_EXEMPT_PRESETS 內無 LIVE 策略，無 b19 基準可比 → 仍可看絕對門檻")

    tickers = load_stocks()
    print(f"\nstocks.txt {len(tickers)} 隻；載入 EODHD…")
    sd, skipped = build_stock_data(tickers)
    print(f"已載入 {len(sd)} 隻（跳過 {skipped}）")
    if len(sd) < 10:
        print("❌ 可用股票太少")
        return 1

    all_keys = benchmark + candidates
    results = {}
    for k in all_keys:
        trades = collect_blended_trades(k, ACTIVE_PRESETS[k], sd)
        tagged = tag_trades(trades, label_ser)
        results[k] = analyze_hard_bear(k, tagged)

    # ── 各策略硬熊 cohort 明細 ───────────────────────────────────
    print("\n" + "═" * 92)
    print("  各策略硬熊 cohort × episode 集中度")
    print("═" * 92)
    for k in benchmark:
        print_metrics(results[k], is_benchmark=True)
    for k in candidates:
        print_metrics(results[k], is_benchmark=False)

    # ── 比照 b19 的判讀 ──────────────────────────────────────────
    print("\n" + "═" * 92)
    print("  判讀（以 b19 為已接受的 episode 集中基準線；最終 config 決定權在 Ivan）")
    print("═" * 92)
    b = results[benchmark[0]] if benchmark else {
        "n_eff": 0.0, "mean": None, "mean_drop": None, "n": 0}
    if benchmark:
        bm = f"{b['mean']:+.2f}%" if b["mean"] is not None else "N/A"
        bd = f"{b['mean_drop']:+.2f}%" if b["mean_drop"] is not None else "N/A"
        print(f"\n  基準 b19：硬熊 {bm}（{b['n']} 筆）  N_eff {b['n_eff']:.1f}  "
              f"剔最賺後 {bd}")
        print("  （b19 是『episode 集中但靠輕倉+豁免接受』的範例——候選不該比它更集中）\n")

    for k in candidates:
        sym, txt = verdict(results[k], b)
        print(f"  {sym} {k}")
        print(f"      {txt}")

    print("\n  ── 若有策略判 🟢/🟡，加入豁免的方式（Ivan 自管 config）──")
    print("     在 config.py 的 BEAR_EXEMPT_PRESETS 集合內，加入該策略的完整 key")
    print("     （含 💎 前綴，需與 ACTIVE_PRESETS 一字不差）；daily_scan 硬熊閘會自動放它進場。")
    print("     ⚠️ 同時確認它已在 LIGHT_POSITION_PRESETS（豁免 ≠ 無風險，硬熊接深跌反彈必輕倉）。")
    print("═" * 92)
    print(f"\n總耗時 {time.time() - t_start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

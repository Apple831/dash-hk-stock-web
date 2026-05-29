"""
test_pattern_combos_wf.py -- V22 形態+形態 AND 候選 PIT Walk-Forward 測試

═══════════════════════════════════════════════════════════════════
背景
═══════════════════════════════════════════════════════════════════
  verify_pattern_combos.py 已篩掉「子集冗餘」組合（b12+b18 保留72%、
  b15+b16 保留100% 都是子集包含，沒新資訊）。
  本腳本對 4 個「真·跨類別」候選跑完整 PIT Walk-Forward 驗證 alpha。

  ⚠️ 本腳本不修改 config.py。候選策略 dict 直接寫在腳本內，
     跑完通過才整檔重寫 config.py 升 💎。ACTIVE 保持 8 支乾淨。

═══════════════════════════════════════════════════════════════════
候選（剔除冗餘後，跨類別 + 互補 + 訊號充足）
═══════════════════════════════════════════════════════════════════
  🔬 b13+b17  縮量反轉 × 急跌（509 筆，唯一過 500 的真組合）
  🔬 b15+b17  下影線形態 × 急跌（370 筆，HANDOVER 點名）
  🔬 b12+b15  資金流向 × 下影線形態（280 筆，純跨類別）
  🔬 b13+b15  縮量反轉 × 下影線形態（274 筆，HANDOVER 點名雙形態）

  基準（單訊號，用來判斷 AND 是否帶來增量）：
  💎 b15 長下影線   （已知 PIT OOS +5.73%）
  💎 b17 ROC超跌反彈（已知 PIT OOS +8.56%）

═══════════════════════════════════════════════════════════════════
驗收標準（升 💎 的門檻）
═══════════════════════════════════════════════════════════════════
  1. OOS 平均 > 0%
  2. 正 Fold ≥ 6/7（≈85%）
  3. Fold7（最近期）樣本 ≥ 10 筆（避免樣本薄虛高陷阱）
  4. ★關鍵★ OOS 必須「明顯優於」組成它的單訊號基準，
     否則 AND 沒帶來增量價值，不如直接用單訊號。
     例：b15+b17 的 OOS 若 < b17 的 +8.56%，則該組合無意義。

═══════════════════════════════════════════════════════════════════
使用方法
═══════════════════════════════════════════════════════════════════
  cd 專案根目錄
  python scripts/test_pattern_combos_wf.py

  需要 data/eodhd_prices/*.json（PIT 股票池）。
  預設跑 4 候選 + 2 基準。若太慢，可在 RUN_LIST 註解掉部分。
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
from config import (
    COMMISSION_PCT,
    SLIPPAGE_PCT,
    WF_ROBUST_MAX_DEGRADATION,
    WF_ROBUST_MIN_OOS_POS_RATE,
    WF_WARNING_MAX_DEGRADATION,
    WF_WARNING_MIN_OOS_POS_RATE,
    WF_MIN_IS_RETURN_FOR_CALC,
)


# ══════════════════════════════════════════════════════════════════
# 策略定義（不碰 config.py）
# ══════════════════════════════════════════════════════════════════
def make_buy(*active) -> tuple:
    """active=('b13','b17') → 18-tuple，對應位置 True，其他 False。"""
    idx = {f"b{i+1}": i for i in range(18)}
    t = [False] * 18
    for a in active:
        t[idx[a]] = True
    return tuple(t)


SELL_S2 = (False, True, False, False, False, False, False, False)  # s2 布林上軌出場

CANDIDATES = {
    "🔬 b13+b17 縮量反轉+急跌": {
        "buy": make_buy("b13", "b17"), "sell": SELL_S2, "min_hold_days": 5,
        "note": "縮量反轉 × ROC急跌，跨類別，verify 509 筆（唯一過 500）",
    },
    "🔬 b15+b17 下影線+急跌": {
        "buy": make_buy("b15", "b17"), "sell": SELL_S2, "min_hold_days": 5,
        "note": "長下影線 × ROC急跌，HANDOVER 點名，verify 370 筆",
    },
    "🔬 b12+b15 資金流向+下影線": {
        "buy": make_buy("b12", "b15"), "sell": SELL_S2, "min_hold_days": 5,
        "note": "資金流向 × 長下影線，純跨類別，verify 280 筆",
    },
    "🔬 b13+b15 縮量反轉+下影線": {
        "buy": make_buy("b13", "b15"), "sell": SELL_S2, "min_hold_days": 5,
        "note": "縮量反轉 × 長下影線，HANDOVER 點名雙形態，verify 274 筆",
    },
}

BENCHMARKS = {
    "💎 b15 長下影線(基準)": {
        "buy": make_buy("b15"), "sell": SELL_S2, "min_hold_days": 5,
        "note": "單訊號基準，已知 PIT OOS +5.73%",
    },
    "💎 b17 ROC超跌反彈(基準)": {
        "buy": make_buy("b17"), "sell": SELL_S2, "min_hold_days": 5,
        "note": "單訊號基準，已知 PIT OOS +8.56%",
    },
}

# 預設跑哪些（太慢可註解掉部分）
RUN_LIST = [
    "🔬 b13+b17 縮量反轉+急跌",
    "🔬 b15+b17 下影線+急跌",
    "🔬 b12+b15 資金流向+下影線",
    "🔬 b13+b15 縮量反轉+下影線",
    "💎 b15 長下影線(基準)",
    "💎 b17 ROC超跌反彈(基準)",
]

ALL_SPECS = {**CANDIDATES, **BENCHMARKS}

# 已知單訊號 OOS 基準（用於 AND 增量判斷）
SINGLE_OOS = {"b15": 5.73, "b17": 8.56, "b12": 7.03, "b13": 6.32}


# ══════════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════════
def build_stock_data(tickers: list) -> dict:
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
    if not wf_results:
        return {"avg_is": None, "avg_oos": None, "avg_deg": None,
                "oos_pos": 0, "valid_folds": 0, "total_folds": 0, "fold7_n": None}
    total_folds = len(wf_results)
    valid = [r for r in wf_results if r.get("valid_oos")]
    valid_folds = len(valid)

    is_rets  = [r["is_metrics"].get("平均每筆回報%", 0.0)  for r in valid if r["is_metrics"]]
    oos_rets = [r["oos_metrics"].get("平均每筆回報%", 0.0) for r in valid if r["oos_metrics"]]
    avg_is  = sum(is_rets) / len(is_rets)   if is_rets  else None
    avg_oos = sum(oos_rets) / len(oos_rets) if oos_rets else None

    if avg_is is not None and avg_oos is not None and abs(avg_is) >= WF_MIN_IS_RETURN_FOR_CALC:
        avg_deg = (avg_is - avg_oos) / abs(avg_is) * 100
    else:
        avg_deg = None

    oos_pos = sum(1 for r in valid if r["oos_metrics"].get("平均每筆回報%", 0.0) > 0)

    # 最後一個 Fold 的 OOS 樣本數（樣本薄虛高檢查）
    fold7_n = None
    if wf_results:
        fold7_n = wf_results[-1].get("oos_trade_count", 0)

    return {"avg_is": avg_is, "avg_oos": avg_oos, "avg_deg": avg_deg,
            "oos_pos": oos_pos, "valid_folds": valid_folds,
            "total_folds": total_folds, "fold7_n": fold7_n}


def grade(s: dict, name: str) -> str:
    avg_oos = s["avg_oos"]
    if avg_oos is None:
        return "⚪ 無交易"
    pos_rate = (s["oos_pos"] / s["valid_folds"] * 100) if s["valid_folds"] else 0.0

    # 基本 alpha 門檻
    if avg_oos <= 0:
        return "🔴 OOS虧損"
    if pos_rate < WF_WARNING_MIN_OOS_POS_RATE:
        return "🔴 正Fold不足"

    # AND 增量判斷：與組成單訊號比較
    base = name.replace("🔬 ", "").split(" ")[0]  # e.g. "b13+b17"
    if "+" in base:
        parts = base.split("+")
        single_best = max((SINGLE_OOS.get(p, 0) for p in parts), default=0)
        if avg_oos <= single_best:
            return f"🟡 無增量(≤單訊號{single_best:.1f}%)"

    # 樣本薄檢查
    if s["fold7_n"] is not None and s["fold7_n"] < 10:
        return f"🟡 末Fold薄({s['fold7_n']}筆)"

    if pos_rate >= WF_ROBUST_MIN_OOS_POS_RATE:
        return "🟢 通過(可升💎)"
    return "🟡 尚可"


def run_one(name: str, spec: dict, stock_data: dict) -> dict:
    print(f"\n────────────────────────────────────────")
    print(f"▶ {name}")
    print(f"  {spec.get('note', '')}")
    t0 = time.time()

    last_print = [0.0]
    def cb(fold, total_folds, ticker):
        now = time.time()
        if now - last_print[0] > 1.0:
            print(f"    fold {fold}/{total_folds}  {ticker}", end="\r", flush=True)
            last_print[0] = now

    wf = run_portfolio_walk_forward(
        stock_data,
        buy_sigs=spec["buy"],
        sell_sigs=spec["sell"],
        is_months=12,
        oos_months=6,
        trade_size=100_000,
        slippage=SLIPPAGE_PCT,
        commission_pct=COMMISSION_PCT,
        min_hold_days=spec.get("min_hold_days"),
        cooldown_days=spec.get("cooldown_days"),
        seasonal_filter=spec.get("seasonal_filter", False),
        track_extended=False,
        use_pit_universe=True,   # ★ PIT 股票池修正生存者偏差
        progress_cb=cb,
    )
    print(" " * 80, end="\r")

    s = summarize_wf(wf)
    g = grade(s, name)
    elapsed = time.time() - t0

    is_str  = f"{s['avg_is']:+.2f}%"  if s["avg_is"]  is not None else "N/A"
    oos_str = f"{s['avg_oos']:+.2f}%" if s["avg_oos"] is not None else "N/A"
    deg_str = f"{s['avg_deg']:.1f}%"  if s["avg_deg"] is not None else "N/A"
    pos_str = f"{s['oos_pos']}/{s['valid_folds']}"
    f7_str  = f"{s['fold7_n']}" if s["fold7_n"] is not None else "N/A"

    print(f"  ✓ {elapsed:.1f}s  IS {is_str} → OOS {oos_str}  "
          f"退化 {deg_str}  正Fold {pos_str}  末Fold {f7_str}筆")
    print(f"  評級：{g}")

    return {"name": name, "summary": s, "grade": g}


def print_table(rows: list):
    print("\n" + "═" * 96)
    print("  V22 形態+形態 AND 候選 — PIT WF 對比表")
    print("═" * 96)
    print(f"{'策略':<30} {'IS%':>9} {'OOS%':>9} {'退化%':>9} "
          f"{'正Fold':>9} {'末Fold':>8} {'評級':>18}")
    print("─" * 96)
    for r in rows:
        if r is None:
            continue
        s = r["summary"]
        is_str  = f"{s['avg_is']:+.2f}"  if s["avg_is"]  is not None else "N/A"
        oos_str = f"{s['avg_oos']:+.2f}" if s["avg_oos"] is not None else "N/A"
        deg_str = f"{s['avg_deg']:.1f}"  if s["avg_deg"] is not None else "N/A"
        pos_str = f"{s['oos_pos']}/{s['valid_folds']}"
        f7_str  = f"{s['fold7_n']}" if s["fold7_n"] is not None else "N/A"
        name = r["name"]
        if len(name) > 29:
            name = name[:28] + "…"
        print(f"{name:<30} {is_str:>9} {oos_str:>9} {deg_str:>9} "
              f"{pos_str:>9} {f7_str:>8} {r['grade']:>18}")
    print("═" * 96)
    print("\n💡 判讀：候選的 OOS 必須明顯高於其組成單訊號基準，AND 才有增量價值。")
    print("   b15 基準 +5.73%、b17 基準 +8.56% — 含 b17 的組合門檻特別高。")


def main() -> int:
    t_start = time.time()
    print("═" * 96)
    print("  V22 形態+形態 AND 候選 PIT Walk-Forward（12+6, $100k, PIT ON）")
    print("═" * 96)

    tickers = load_stocks()
    print(f"\nstocks.txt 共 {len(tickers)} 隻；載入 EODHD 提供時間軸…")
    stock_data, skipped = build_stock_data(tickers)
    print(f"已載入 {len(stock_data)} 隻（跳過 {skipped} 隻數據不足）")

    if len(stock_data) < 10:
        print("❌ 可用股票太少（<10），中止。請確認 data/eodhd_prices/ 是否存在。")
        return 1

    rows = []
    for name in RUN_LIST:
        spec = ALL_SPECS.get(name)
        if spec is None:
            print(f"  ⚠️ {name} 未定義，跳過")
            continue
        rows.append(run_one(name, spec, stock_data))

    print_table(rows)

    # 列出通過的候選
    passed = [r for r in rows
              if r and "🟢" in r["grade"] and r["name"].startswith("🔬")]
    if passed:
        print(f"\n🟢 通過驗收、建議升 💎 的候選 {len(passed)} 個：")
        for r in passed:
            print(f"   • {r['name']}")
        print("\n   下一步：把結果貼回對話，我會整檔重寫 config.py 加入這些策略。")
    else:
        print("\n⚠️ 本批無候選通過完整驗收，可能需要：")
        print("   • 調整出場規則（試 s6 MACD死叉 或 s2+s6 組合）")
        print("   • 或接受「單訊號已是最優，AND 無增量」的結論")

    elapsed = time.time() - t_start
    print(f"\n總耗時：{elapsed:.1f} 秒 ({elapsed/60:.1f} 分鐘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

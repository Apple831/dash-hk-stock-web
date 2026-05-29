"""
verify_pattern_combos.py -- V22 形態+形態 AND 組合訊號數驗證

═══════════════════════════════════════════════════════════════════
背景（HANDOVER18 V22 鐵則）
═══════════════════════════════════════════════════════════════════
  • V22 主鐵則：港股 PIT 下「形態事件類」有 alpha，「指標閾值類」沒有
  • V22 衍生鐵則 2：b6 雙確認是樣本陷阱（Fold7 樣本砍 80-100%）
  • V22 衍生鐵則 4：AND > 2 條件 或 形態+指標 AND 會把訊號掐死
  • 戰略方向：探索「形態事件 + 形態事件」AND 組合

═══════════════════════════════════════════════════════════════════
本腳本做什麼
═══════════════════════════════════════════════════════════════════
  1. 跑全 stocks.txt × 5 年 EODHD 資料（或回退 yfinance 1 年）
  2. 統計 7 個形態事件類訊號的單訊號 baseline
  3. 跑 C(7,2) = 21 組形態+形態 AND
  4. 跑 7 組 b6+形態 對照（驗證 V22 衍生鐵則 2）
  5. 輸出建議：哪些組合值得進入 PIT WF

═══════════════════════════════════════════════════════════════════
判讀準則（基於 💎 b13-b18 PIT 已知數字校準）
═══════════════════════════════════════════════════════════════════
  💎 b13 PIT 每 Fold 26-265 筆，💎 b15 每 Fold 168-541 筆
  全市場 5 年 ≈ 12 個半年 Fold，所以 5 年總量大概是每 Fold × 12

  形態+形態 AND 總訊號數判讀：
    🟢 ≥ 500 筆/5y：每 Fold ≈ 40+，樣本充足，跑 PIT WF
    🟡 100-499 筆 ：每 Fold 8-40，邊界，可跑但留意末 Fold 萎縮
    🔴 < 100 筆   ：每 Fold < 8，AND 過嚴，直接淘汰

  b6+形態 對照組「砍掉率」判讀：
    > 80%：典型 b6 雙確認陷阱（Fold7 會歸零）
    60-80%：警示
    < 60%：罕見，但仍建議走純形態+形態路線

═══════════════════════════════════════════════════════════════════
使用方法
═══════════════════════════════════════════════════════════════════
  cd 專案根目錄
  python scripts/verify_pattern_combos.py

  EODHD 數據優先（路徑：data/eodhd_prices/*.json）
  若無 EODHD，自動回退 yfinance 1y（會比較不準確，因為樣本期短）

═══════════════════════════════════════════════════════════════════
注意：訊號重疊提示
═══════════════════════════════════════════════════════════════════
  以下組合本質高度重疊，verify 結果可能誤導：
    • b15+b16：b16 = b15 + 量強化，AND ≈ b16 單訊號（沒新資訊）
    • b13+b17：兩者都已內建 RSI 過濾（b13<40、b17<45），冗餘
    • b12+b18：兩者都是 MA20 下方 + 量能 + 陽燭，b18 是 b12 升級版
  策略開發優先選擇「跨類別」組合（觸底形態 × 量能/跌幅）。
"""
import os
import sys
from itertools import combinations

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

from data import load_stocks
from indicators import precompute_signals

# 嘗試 EODHD（5 年資料）優先，回退 yfinance（1 年）
try:
    from historical_universe import load_eodhd_prices
    _has_eodhd = True
except ImportError:
    _has_eodhd = False

if not _has_eodhd:
    from data import get_cached


# V22 形態事件類訊號（HANDOVER18 證明有 alpha）
PATTERN_SIGNALS = ["b12", "b13", "b14", "b15", "b16", "b17", "b18"]


def load_df(ticker: str):
    """讀股票資料：EODHD 優先（5y），否則 yfinance（1y）。"""
    if _has_eodhd:
        df = load_eodhd_prices(ticker)
        if not df.empty:
            return df, "eodhd"
    df = get_cached(ticker, "1y") if not _has_eodhd else _yfinance_fallback(ticker)
    return df, "yfinance"


def _yfinance_fallback(ticker: str):
    from data import get_cached as _gc
    return _gc(ticker, "1y")


def main():
    print("=" * 72)
    print("V22 形態+形態 AND 組合 verify")
    print("=" * 72)

    tickers = load_stocks()
    print(f"\n讀取 stocks.txt：{len(tickers)} 支")

    # 候選組合：C(7, 2) = 21 種形態+形態 AND
    pattern_combos = {}
    for a, b in combinations(PATTERN_SIGNALS, 2):
        pattern_combos[f"{a}+{b}"] = (a, b)

    # b6+形態 對照組（驗證 V22 衍生鐵則 2）
    b6_combos = {f"b6+{s}": ("b6", s) for s in PATTERN_SIGNALS}

    # 累積統計
    single_totals = {s: 0 for s in PATTERN_SIGNALS + ["b6"]}
    pattern_totals = {k: 0 for k in pattern_combos}
    b6_totals = {k: 0 for k in b6_combos}
    n_loaded = 0
    n_bars_total = 0
    data_source = "unknown"

    for tkr in tickers:
        df, src = load_df(tkr)
        if df.empty or len(df) < 62:
            continue
        data_source = src
        sigs = precompute_signals(df)
        for s in single_totals:
            single_totals[s] += int(sigs[s].sum())
        for cname, (a, b) in pattern_combos.items():
            pattern_totals[cname] += int((sigs[a] & sigs[b]).sum())
        for cname, (a, b) in b6_combos.items():
            b6_totals[cname] += int((sigs[a] & sigs[b]).sum())
        n_loaded += 1
        n_bars_total += len(df)

    print(f"資料來源：{data_source}")
    print(f"成功載入 {n_loaded} 支股票，共 {n_bars_total:,} 根 K 線\n")

    if n_loaded == 0:
        print("❌ 無任何股票資料，請確認 stocks.txt / EODHD / yfinance 配置。")
        return 1

    # ══════════════════════════════════════════════════════════════
    # 區塊 1：單訊號 baseline
    # ══════════════════════════════════════════════════════════════
    print("=" * 72)
    print("【1】單訊號 baseline（V22 主鐵則：形態類強，指標類弱）")
    print("=" * 72)
    print(f"{'訊號':<8} {'總訊號數':>12} {'評估':>10}  說明")
    print("-" * 72)
    for s in sorted(single_totals, key=lambda x: -single_totals[x]):
        n = single_totals[s]
        if n >= 2000:
            status, color = "🟢 充足", ""
        elif n >= 500:
            status, color = "🟡 普通", ""
        else:
            status, color = "🔴 稀疏", ""
        note = "(指標類，HANDOVER 已證雜訊)" if s == "b6" \
               else "(形態類，HANDOVER 證 alpha)"
        print(f"{s:<8} {n:>12,} {status:>10}  {note}")
    print()

    # ══════════════════════════════════════════════════════════════
    # 區塊 2：形態+形態 AND 組合（V22 候選新策略）
    # ══════════════════════════════════════════════════════════════
    print("=" * 72)
    print("【2】形態+形態 AND 組合（V22 候選新策略）")
    print("=" * 72)
    print(f"{'組合':<12} {'AND訊號':>10} {'較小單訊號':>12} {'保留%':>8} {'評估':>10}")
    print("-" * 72)

    pattern_results = sorted(pattern_totals.items(), key=lambda x: -x[1])
    pass_list, border_list, fail_list = [], [], []

    for cname, n in pattern_results:
        a, b = pattern_combos[cname]
        smaller = min(single_totals[a], single_totals[b]) or 1
        retain_pct = n / smaller * 100
        if n >= 500:
            status = "🟢 跑 WF"
            pass_list.append((cname, n))
        elif n >= 100:
            status = "🟡 邊界"
            border_list.append((cname, n))
        else:
            status = "🔴 過嚴"
            fail_list.append((cname, n))
        print(f"{cname:<12} {n:>10,} {smaller:>12,} {retain_pct:>7.1f}% {status:>10}")
    print()

    # ══════════════════════════════════════════════════════════════
    # 區塊 3：b6+形態 對照（驗證 V22 衍生鐵則 2）
    # ══════════════════════════════════════════════════════════════
    print("=" * 72)
    print("【3】b6+形態 對照（驗證 V22 衍生鐵則 2：b6 雙確認是樣本陷阱）")
    print("=" * 72)
    print(f"{'組合':<12} {'AND訊號':>10} {'單形態訊號':>12} {'砍掉%':>8} {'評估':>10}")
    print("-" * 72)

    b6_results = sorted(b6_totals.items(), key=lambda x: -x[1])
    for cname, n in b6_results:
        _, b = b6_combos[cname]
        single_n = single_totals[b]
        kill_pct = (1 - n / single_n) * 100 if single_n else 100
        if kill_pct > 80:
            status = "🔴 陷阱"
        elif kill_pct > 60:
            status = "🟡 警示"
        else:
            status = "🟢 合理"
        print(f"{cname:<12} {n:>10,} {single_n:>12,} {kill_pct:>7.1f}% {status:>10}")
    print()

    # ══════════════════════════════════════════════════════════════
    # 區塊 4：建議
    # ══════════════════════════════════════════════════════════════
    print("=" * 72)
    print("【4】下一步建議")
    print("=" * 72)

    if pass_list:
        print(f"\n🟢 通過 verify（≥500 訊號）的形態+形態組合 {len(pass_list)} 個：")
        for c, n in pass_list:
            a, b = pattern_combos[c]
            print(f"   • {c:<14} 總訊號 {n:>5,} 筆  (建議跑 PIT WF)")
    if border_list:
        print(f"\n🟡 邊界組合（100-499 訊號）{len(border_list)} 個（可選擇性測試）：")
        for c, n in border_list:
            print(f"   • {c:<14} 總訊號 {n:>5,} 筆")
    if fail_list:
        print(f"\n🔴 AND 過嚴淘汰（<100 訊號）{len(fail_list)} 個。")

    if pass_list:
        print("\n📝 建議下一步流程：")
        print("   1. 在 indicators.py 確認對應訊號定義無誤")
        print("   2. 在 config.py 加入候選策略 dict（標 🔬 試驗中）")
        print("      範本：")
        first_pass = pass_list[0][0]
        a, b = pattern_combos[first_pass]
        a_num, b_num = a[1:], b[1:]
        print(f'        "🔬 {first_pass} [新策略名]": {{')
        print(f'            "desc": "【🧪 測試中】V22 形態+形態 AND：{a}+{b} 雙形態確認，s2 出場，MIN5",')
        print(f'            "buy":  (...{a} 與 {b} 位置設 True 其他 False...),')
        print(f'            "sell": (False, True, False, False, False, False, False, False),')
        print(f'            "min_hold_days": 5,')
        print(f'        }},')
        print("   3. 跑 pages/walkforward.py 投資組合模式 + PIT 股票池 ON")
        print("   4. 驗收標準：OOS > 0%、正Fold ≥ 6/7、退化率 < 100%")
        print("   5. Fold7 樣本 ≥ 10 才能避免「樣本薄虛高」陷阱")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

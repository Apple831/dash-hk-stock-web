# ══════════════════════════════════════════════════════════════════
# signals.py — 訊號評估 & 評分
# ══════════════════════════════════════════════════════════════════
#
# v17 修復（2026-04-26）— 來自策略邏輯審查報告：
# 🔴 Bug 3: evaluate_signals 漏 b11 (KDJ超賣金叉) 和 s8 (KDJ高位死叉)
#   修復：補上對應的描述，讓個股分析 Tab 看得到實盤主力策略的 s8 訊號
# ══════════════════════════════════════════════════════════════════

import pandas as pd
from indicators import precompute_signals


def signal_strength_score(df: pd.DataFrame, n_signals_hit: int,
                          vol_ma_last: float = None) -> float:
    if df.empty or len(df) < 2:
        return 0.0
    c      = df.iloc[-1]
    vol_ma = vol_ma_last if vol_ma_last is not None else df["Volume"].rolling(20).mean().iloc[-1]

    sig_score = min(n_signals_hit * 10, 40)

    vol_ratio = float(c["Volume"]) / float(vol_ma) if vol_ma > 0 else 1.0
    raw_vol   = min((vol_ratio - 1) / 2 * 30, 30)
    is_up_day = float(c["Close"]) >= float(c["Open"])
    vol_score = raw_vol if is_up_day else raw_vol * 0.5

    rsi_score = max(0, (30 - float(c["RSI"])) / 30 * 15) if float(c["RSI"]) <= 50 else 0
    j_score   = max(0, (10 - float(c["J"])) / 10 * 15) if float(c["J"]) <= 50 else 0

    return round(sig_score + vol_score + rsi_score + j_score, 1)


def evaluate_signals(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 62:
        return {"buy": [], "sell": []}

    sigs = precompute_signals(df)
    last = {k: bool(v.iloc[-1]) for k, v in sigs.items()}

    c       = df.iloc[-1]
    p       = df.iloc[-2]
    vol_avg = df["Volume"].rolling(20).mean().iloc[-1]
    resist  = df["High"].iloc[-21:-1].max()

    buy_signals = [
        ("① 突破阻力位 + 放量",
         f"收盤 {c['Close']:.2f} {'>' if last['b1'] else '<='} 前高 {resist:.2f}，量比 {c['Volume']/vol_avg:.1f}x",
         last["b1"]),
        ("② MA5 金叉 MA20",
         f"MA5={c['MA5']:.2f}  MA20={c['MA20']:.2f}  昨MA5={p['MA5']:.2f}",
         last["b2"]),
        ("③ 底背離（價創新低 MACD未）",
         f"DIF={c['DIF']:.4f}  RSI={c['RSI']:.1f}  需RSI<40 + swing low背離 + 價差>3%",
         last["b3"]),
        ("④ 底部形態突破（放量站上MA20）",
         f"站上MA20={'是' if bool(c['Close']>c['MA20']) else '否'}  量比={c['Volume']/vol_avg:.1f}x",
         last["b4"]),
        ("⑤ 布林帶下軌買入",
         f"收盤 {c['Close']:.2f}  BB下軌 {c['BB_lower']:.2f}",
         last["b5"]),
        ("⑥ RSI 超賣（< 30）",
         f"RSI = {c['RSI']:.1f}",
         last["b6"]),
        ("⑦ MACD 金叉（DIF上穿DEA）",
         f"DIF={c['DIF']:.4f}  DEA={c['DEA']:.4f}  昨DIF={p['DIF']:.4f}",
         last["b7"]),
        ("⑧ 個股趨勢確認（MA20 > MA60）",
         f"MA20={c['MA20']:.2f}  MA60={c['MA60']:.2f}  {'✅ 上升趨勢' if last['b8'] else '❌ 非上升趨勢'}",
         last["b8"]),
        ("⑨ 52週新高突破（真突破）",
         f"現價 {c['Close']:.2f}  需 >= 52週高點",
         last["b9"]),
        ("⑩ 縮量回調至 MA20",
         f"MA20={c['MA20']:.2f}  量比={c['Volume']/vol_avg:.1f}x（需<0.8x，上升趨勢中）",
         last["b10"]),
        # ── v17 新增：b11 (KDJ 超賣金叉) ─────────────────────────
        ("⑪ KDJ 超賣金叉（K<20, D<20, K上穿D）",
         f"K={c['K']:.1f}  D={c['D']:.1f}  J={c['J']:.1f}  昨K={p['K']:.1f}  昨D={p['D']:.1f}",
         last["b11"]),
    ]

    pct_chg = (c["Close"] - p["Close"]) / p["Close"] * 100
    ph      = df["Close"].iloc[-10:].max()

    sell_signals = [
        ("⑫ 頭部形態跌破 MA20（放量）",
         f"跌破MA20={'是' if bool(c['Close']<c['MA20']) else '否'}  量比={c['Volume']/vol_avg:.1f}x",
         last["s1"]),
        ("⑬ 布林帶上軌賣出",
         f"收盤 {c['Close']:.2f}  BB上軌 {c['BB_upper']:.2f}",
         last["s2"]),
        ("⑭ 上漲縮量（警惕頂部）",
         f"近高={ph:.2f}  量比={c['Volume']/vol_avg:.1f}x（需<0.6x）",
         last["s3"]),
        ("⑮ 放量急跌",
         f"跌幅={pct_chg:.2f}%  量比={c['Volume']/vol_avg:.1f}x",
         last["s4"]),
        ("⑯ RSI 超買（> 70）",
         f"RSI = {c['RSI']:.1f}",
         last["s5"]),
        ("⑰ MACD 死叉（DIF下穿DEA）",
         f"DIF={c['DIF']:.4f}  DEA={c['DEA']:.4f}  昨DIF={p['DIF']:.4f}",
         last["s6"]),
        ("⑱ 三日陰線 + 跌破MA20",
         f"連續3根陰線={'是' if (c['Close']<c['Open']) else '否（今日）'}  收盤<MA20={'是' if bool(c['Close']<c['MA20']) else '否'}",
         last["s7"]),
        # ── v17 新增：s8 (KDJ 高位死叉) ──────────────────────────
        ("⑲ KDJ 高位死叉（K>80, D>80, K下穿D）",
         f"K={c['K']:.1f}  D={c['D']:.1f}  J={c['J']:.1f}  昨K={p['K']:.1f}  昨D={p['D']:.1f}",
         last["s8"]),
    ]

    return {"buy": buy_signals, "sell": sell_signals}

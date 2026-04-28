# ══════════════════════════════════════════════════════════════════
# indicators.py — 技術指標計算 & 訊號向量化計算
# ══════════════════════════════════════════════════════════════════

import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["MA5"]  = df["Close"].rolling(5).mean()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()

    exp1 = df["Close"].ewm(span=12, adjust=False).mean()
    exp2 = df["Close"].ewm(span=26, adjust=False).mean()
    df["DIF"]       = exp1 - exp2
    df["DEA"]       = df["DIF"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["DIF"] - df["DEA"]

    low9  = df["Low"].rolling(9).min()
    high9 = df["High"].rolling(9).max()
    denom = (high9 - low9).replace(0, 1)
    rsv   = (df["Close"] - low9) / denom * 100
    df["K"] = rsv.ewm(com=2, adjust=False).mean()
    df["D"] = df["K"].ewm(com=2, adjust=False).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]

    bb_mid         = df["Close"].rolling(20).mean()
    bb_std         = df["Close"].rolling(20).std()
    df["BB_upper"] = bb_mid + 2 * bb_std
    df["BB_mid"]   = bb_mid
    df["BB_lower"] = bb_mid - 2 * bb_std

    delta     = df["Close"].diff()
    gain      = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss      = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs        = gain / loss.replace(0, 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))

    return df


# ── Swing Low 識別（無前視偏差）────────────────────────────────────
def _swing_lows(close_ser: pd.Series, window: int = 10) -> pd.Series:
    left_min = close_ser.rolling(window + 1, min_periods=window + 1).min()
    is_swing_low = close_ser <= left_min
    return is_swing_low.fillna(False)


# ── 底背離序列 ──────────────────────────────────────────────────────
def _compute_b3_series(df: pd.DataFrame) -> pd.Series:
    swing_lo      = _swing_lows(df["Close"], window=5)
    prev_sl_close = df["Close"].where(swing_lo).ffill().shift(1)
    prev_sl_dif   = df["DIF"].where(swing_lo).ffill().shift(1)
    min_price_diff = (prev_sl_close - df["Close"]) / prev_sl_close > 0.03

    b3 = (
        swing_lo &
        min_price_diff &
        (df["Close"] < prev_sl_close) &
        (df["DIF"]   > prev_sl_dif)   &
        (df["RSI"]   < 40)
    )
    return b3.fillna(False)


# ── 向量化計算所有買賣訊號 ──────────────────────────────────────────
def precompute_signals(df: pd.DataFrame, hsi_bullish: bool = True) -> dict:
    c      = df
    p      = df.shift(1)
    vol_ma = df["Volume"].rolling(20).mean()

    # ── 買入訊號 ──────────────────────────────────────────────────
    resist = df["High"].shift(1).rolling(20).max()
    b1 = (c["Close"] > resist) & (c["Volume"] > vol_ma * 1.5)

    b2 = (c["MA5"] > c["MA20"]) & (p["MA5"] <= p["MA20"])

    b3 = _compute_b3_series(df)

    close_ma10 = df["Close"].rolling(10).mean().shift(1)
    ma60_ma10  = df["MA60"].rolling(10).mean().shift(1)
    was_below  = close_ma10 < ma60_ma10
    b4 = was_below & (c["Close"] > c["MA20"]) & (p["Close"] <= p["MA20"]) & (c["Volume"] > vol_ma * 1.3)

    # ── GATE 移除 ──────────────────────────────────────────────────
    # 原代碼：b5/b6 在 hsi_bullish=False（熊市）時強制為 False。
    # 移除原因：WF 驗證顯示 b5+b6 在熊市（弱熊+8%/204筆、強熊+12.5%/228筆）
    # 表現優於牛市，均值回歸策略在高波動環境反而更有效。
    # 保留 gate 導致 WF 與實盤掃描行為不一致，現統一為全天候觸發。
    # hsi_bullish 參數保留以維持向後相容，但不再影響 b5/b6。
    b5 = c["Close"] < c["BB_lower"]
    b6 = c["RSI"] < 30
    # ── END GATE 移除 ─────────────────────────────────────────────

    b7 = (c["DIF"] > c["DEA"]) & (p["DIF"] <= p["DEA"])

    b8 = c["MA20"] > c["MA60"]

    close_52w_high = df["Close"].rolling(min(252, len(df)), min_periods=60).max().shift(1)
    b9 = c["Close"] >= close_52w_high

    in_uptrend = c["MA20"] > c["MA60"]
    near_ma20  = (c["Close"] >= c["MA20"] * 0.98) & (c["Close"] <= c["MA20"] * 1.03)
    low_volume = c["Volume"] < vol_ma * 0.8
    b10 = in_uptrend & near_ma20 & low_volume

    # ── b11: KDJ 超賣金叉（本次新增）──────────────────────────
    # K, D 都在 20 以下（深度超賣）+ K 上穿 D（金叉）
    # 比 b6 (RSI<30) 更嚴格，預期樣本較少但精度更高
    b11 = (c["K"] < 20) & (c["D"] < 20) & (c["K"] > c["D"]) & (p["K"] <= p["D"])

    # ── 賣出訊號 ──────────────────────────────────────────────────
    close_ma10u = df["Close"].rolling(10).mean().shift(1)
    ma60_ma10u  = df["MA60"].rolling(10).mean().shift(1)
    was_above   = close_ma10u > ma60_ma10u
    s1 = was_above & (c["Close"] < c["MA20"]) & (p["Close"] >= p["MA20"]) & (c["Volume"] > vol_ma * 1.3)

    s2 = c["Close"] > c["BB_upper"]

    # ── BUG FIX 1 ──────────────────────────────────────────────────
    close_max10 = df["Close"].shift(1).rolling(10).max()
    s3 = (c["Close"] >= close_max10 * 0.995) & (c["Volume"] < vol_ma * 0.6)
    # ── END FIX 1 ─────────────────────────────────────────────────

    pct_chg = c["Close"].pct_change() * 100
    s4 = (pct_chg < -2) & (c["Volume"] > vol_ma * 1.5)

    s5 = c["RSI"] > 70

    s6 = (c["DIF"] < c["DEA"]) & (p["DIF"] >= p["DEA"])

    three_red = (
        (df["Close"] < df["Open"]) &
        (df["Close"].shift(1) < df["Open"].shift(1)) &
        (df["Close"].shift(2) < df["Open"].shift(2))
    )
    s7 = three_red & (c["Close"] < c["MA20"])

    # ── s8: KDJ 高位死叉（本次新增）──────────────────────────
    # K, D 都在 80 以上（深度超買）+ K 下穿 D（死叉）
    # 對應 b11，給 💎M30 系列一個 s6+s8 雙出場選項
    s8 = (c["K"] > 80) & (c["D"] > 80) & (c["K"] < c["D"]) & (p["K"] >= p["D"])

    # 前61行 mask
    mask = pd.Series(False, index=df.index)
    mask.iloc[:61] = True

    sigs = {}
    for name, s in [("b1",b1),("b2",b2),("b3",b3),("b4",b4),("b5",b5),
                    ("b6",b6),("b7",b7),("b8",b8),("b9",b9),("b10",b10),
                    ("b11",b11),
                    ("s1",s1),("s2",s2),("s3",s3),("s4",s4),
                    ("s5",s5),("s6",s6),("s7",s7),("s8",s8)]:
        sigs[name] = s.fillna(False) & ~mask
    return sigs

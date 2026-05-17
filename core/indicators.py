# ══════════════════════════════════════════════════════════════════
# indicators.py — 技術指標計算 & 訊號向量化計算
# ══════════════════════════════════════════════════════════════════

import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # 異常 bar 遮蔽：用前值填充，避免污染 EMA 但保留時序
    if "is_anomaly" in df.columns:
        anomaly_mask = df["is_anomaly"].fillna(False)
        if anomaly_mask.any():
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in df.columns:
                    df.loc[anomaly_mask, col] = None
            df[["Open", "High", "Low", "Close", "Volume"]] = (
                df[["Open", "High", "Low", "Close", "Volume"]].ffill()
            )
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

    # ── b9 DEPRECATED 2026-05-10 ────────────────────────────────
    # 熊市過濾後訊號過少，AND 邏輯全部歸零，已永久廢棄。
    # 禁止在此發出任何網絡請求（get_cached 已移除）。
    b9 = pd.Series(False, index=df.index)

    in_uptrend = c["MA20"] > c["MA60"]
    near_ma20  = (c["Close"] >= c["MA20"] * 0.98) & (c["Close"] <= c["MA20"] * 1.03)
    low_volume = c["Volume"] < vol_ma * 0.8
    b10 = in_uptrend & near_ma20 & low_volume

    # ── b11: KDJ 超賣金叉（本次新增）──────────────────────────
    # K, D 都在 20 以下（深度超賣）+ K 上穿 D（金叉）
    # 比 b6 (RSI<30) 更嚴格，預期樣本較少但精度更高
    b11 = (c["K"] < 20) & (c["D"] < 20) & (c["K"] > c["D"]) & (p["K"] <= p["D"])

    # ── b12: 資金流向（本次新增）────────────────────────────────
    # Layer 1: Close < MA20（超賣區間）
    # Layer 2: 2× vol_ma < Volume < 8× vol_ma（大量，排除異常爆量）
    # Layer 3: Close > Open（陽燭，當日多方勝出）
    b12 = (
        (c["Close"] < c["MA20"]) &
        (c["Volume"] > vol_ma * 2) &
        (c["Volume"] < vol_ma * 8) &
        (c["Close"] > c["Open"])
    )

    # ── b13: 縮量後放量陽線（賣壓枯竭反轉）─────────────────────
    # 放寬：2天縮量（原3天）+ 放量降至1.2x（原1.5x）
    b13 = (
        (df["Volume"].shift(1) < df["Volume"].shift(2)) &
        (c["Volume"] > vol_ma * 1.2) &
        (c["Close"] > c["Open"]) &
        (c["Close"] < c["MA20"]) &
        (c["RSI"] < 40)
    )

    # ── b14: 低位半吞噬形態（強力買入確認）──────────────────────
    # 放寬：今收 >= 昨開昨收中點（原完整吞噬）+ 放量降至1.2x（原1.5x）
    b14 = (
        (p["Close"] < p["Open"]) &
        (c["Close"] > c["Open"]) &
        (c["Open"] <= p["Close"]) &
        (c["Close"] >= (p["Open"] + p["Close"]) / 2) &
        (c["Volume"] > vol_ma * 1.2) &
        (c["Close"] < c["MA20"])
    )


    # ── b15: 長下影線（低位支撐確認）────────────────────────────
    # 放寬：下影線 > 0.8%（原1.5%）
    _lower_shadow = df[["Open", "Close"]].min(axis=1) - df["Low"]
    _body_size    = (df["Close"] - df["Open"]).abs()
    _mid_price    = (df["High"] + df["Low"]) / 2
    b15 = (
        (_lower_shadow > _body_size * 2) &
        (_lower_shadow > df["Close"] * 0.008) &
        (df["Close"] > _mid_price) &
        (c["Close"] < c["MA20"]) &
        (c["Volume"] > vol_ma * 1.0)
    )

    # ── b16: 長下影線+資金流入（b15 形態 + 放量確認，量門檻放寬）────
    # 與 b15+b12 AND 的差別：量下限從 2x 降至 1.5x，上限從 8x 放寬至 12x
    # 原因：b15 下影線當日往往是恐慌性拋售後拉回，量不一定達到 2x
    _lower_shadow_b16 = df[["Open", "Close"]].min(axis=1) - df["Low"]
    _body_size_b16    = (df["Close"] - df["Open"]).abs()
    _mid_price_b16    = (df["High"] + df["Low"]) / 2
    b16 = (
        (_lower_shadow_b16 > _body_size_b16 * 2) &
        (_lower_shadow_b16 > df["Close"] * 0.008) &
        (df["Close"] > _mid_price_b16) &
        (c["Close"] < c["MA20"]) &
        (c["Volume"] > vol_ma * 1.5) &
        (c["Volume"] < vol_ma * 12) &
        (c["Close"] > c["Open"])
    )

    # ── b17: 5日ROC超跌反彈 ────────────────────────────────
    # 5天跌速異常（ROC5 < -8%），今日陽燭初步反轉
    # 與 b6 RSI超賣互補：捕捉急跌但 RSI 未到30的情境
    roc5 = (df["Close"] - df["Close"].shift(5)) / df["Close"].shift(5) * 100
    b17 = (
        (roc5 < -8) &
        (c["Close"] < c["MA20"]) &
        (c["RSI"] < 45) &
        (c["Close"] > c["Open"])
    )

    # ── b18: Z-Score 資金流向（b12 升級版）──────────────────
    # 用標準差衡量成交量異常，自動適應不同股票的量能波動率
    # Z = (今日量 - 20日均量) / 20日標準差
    vol_std = df["Volume"].rolling(20).std().replace(0, float("nan"))
    vol_z = (df["Volume"] - vol_ma) / vol_std
    b18 = (
        (c["Close"] < c["MA20"]) &
        (vol_z > 2.0) &
        (vol_z < 5.0) &
        (c["Close"] > c["Open"])
    )

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
                    ("b11",b11),("b12",b12),
                    ("b13",b13),("b14",b14),("b15",b15),("b16",b16),
                    ("b17",b17),("b18",b18),
                    ("s1",s1),("s2",s2),("s3",s3),("s4",s4),
                    ("s5",s5),("s6",s6),("s7",s7),("s8",s8)]:
        sigs[name] = s.fillna(False) & ~mask
    return sigs


def is_seasonal(df: pd.DataFrame) -> pd.Series:
    return pd.Series(df.index.month.isin([1, 4, 10]), index=df.index)

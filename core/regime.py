import pandas as pd


def detect_regime(df: pd.DataFrame) -> dict:
    """
    8-regime detection matching Streamlit V18 logic.

    Returns dict keys:
      label      — detailed regime string with emoji  e.g. "🟢 強牛市"
      bucket     — 3-category bucket "🟢 牛市" / "🟡 震盪市" / "🔴 熊市"
      color      — Bootstrap color string
      price      — float or None
      pct        — 1-day % change or None
      ma_gap_pct — (MA20-MA60)/MA60*100
      macd_pct   — MACD_Hist/Close*100
      cov_20     — 20-day CoV of Close (std/mean*100)
    """
    if df.empty or len(df) < 60:
        return {
            "label": "資料不足", "bucket": "🟡 震盪市", "color": "secondary",
            "price": None, "pct": None,
            "ma_gap_pct": None, "macd_pct": None, "cov_20": None,
        }

    c  = df.iloc[-1]
    p  = df.iloc[-2]

    ma20  = float(c["MA20"])
    ma60  = float(c["MA60"])
    hist  = float(c["MACD_Hist"])
    close = float(c["Close"])

    ma_gap_pct = (ma20 - ma60) / ma60 * 100 if ma60 != 0 else 0.0
    macd_pct   = hist / close * 100          if close != 0 else 0.0

    roll   = df["Close"].iloc[-20:]
    mean_r = float(roll.mean())
    cov_20 = float(roll.std() / mean_r * 100) if mean_r != 0 else 0.0

    if abs(ma_gap_pct) < 2.0:
        if cov_20 > 2.0:
            label, bucket, color = "震盪市",  "🟡 震盪市", "warning"
        else:
            label, bucket, color = "轉折期",  "🟡 震盪市", "info"
    elif ma_gap_pct > 2.0:
        if macd_pct > 0.5:
            label, bucket, color = "強牛市",  "🟢 牛市", "success"
        elif macd_pct > 0:
            label, bucket, color = "弱牛市",  "🟢 牛市", "success"
        else:
            label, bucket, color = "牛市警惕","🟢 牛市", "warning"
    else:
        if macd_pct < -0.5:
            label, bucket, color = "強熊市",  "🔴 熊市", "danger"
        elif macd_pct < 0:
            label, bucket, color = "弱熊市",  "🔴 熊市", "danger"
        else:
            label, bucket, color = "熊市觀察","🔴 熊市", "warning"

    prev_close = float(p["Close"])
    pct = (close / prev_close - 1) * 100 if prev_close != 0 else 0.0

    return {
        "label":      label,
        "bucket":     bucket,
        "color":      color,
        "price":      close,
        "pct":        pct,
        "ma_gap_pct": round(ma_gap_pct, 2),
        "macd_pct":   round(macd_pct, 4),
        "cov_20":     round(cov_20, 2),
    }


# ── 向量化制度歷史序列 ─────────────────────────────────────────────
# 一次計算最近 n_bars 根 K 線的制度標籤，避免 O(N) 重複呼叫 detect_regime。
# 回傳 list 為時序順序（舊 → 新），最後一筆為當前 K 線的制度。
def regime_history(df: pd.DataFrame, n_bars: int = 120) -> list:
    if df.empty or len(df) < 62:
        return []

    n        = min(int(n_bars), len(df))
    recent   = df.iloc[-n:]
    ma_gap   = (recent["MA20"] - recent["MA60"]) / recent["MA60"] * 100
    macd_pct = recent["MACD_Hist"] / recent["Close"].replace(0, float("nan")) * 100
    full_cov = df["Close"].rolling(20).std() / df["Close"].rolling(20).mean() * 100
    cov_20   = full_cov.iloc[-n:]

    rows = []
    for i in range(len(recent)):
        mg = float(ma_gap.iloc[i])   if pd.notna(ma_gap.iloc[i])   else 0.0
        mp = float(macd_pct.iloc[i]) if pd.notna(macd_pct.iloc[i]) else 0.0
        cv = float(cov_20.iloc[i])   if pd.notna(cov_20.iloc[i])   else 0.0

        if abs(mg) < 2.0:
            label, color = ("震盪市", "warning") if cv > 2.0 else ("轉折期", "info")
        elif mg > 2.0:
            if mp > 0.5:  label, color = "強牛市",  "success"
            elif mp > 0:  label, color = "弱牛市",  "success"
            else:         label, color = "牛市警惕","warning"
        else:
            if mp < -0.5: label, color = "強熊市",  "danger"
            elif mp < 0:  label, color = "弱熊市",  "danger"
            else:         label, color = "熊市觀察","warning"

        rows.append({
            "date":  recent.index[i],
            "label": label,
            "color": color,
        })
    return rows

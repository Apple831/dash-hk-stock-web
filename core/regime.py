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

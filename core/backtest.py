# ══════════════════════════════════════════════════════════════════
# backtest.py -- 回測引擎、績效指標、網格搜索
# ══════════════════════════════════════════════════════════════════
#
# V18 修復（2026-04-27）-- 來自 V17.0 策略複審報告：
#
# 🔴-2: cooldown_days 解耦（方案 B）
#   舊版：cooldown_days = min_hold_days or 30，強制所有無 MIN 策略也有 30 天冷卻，
#         導致「[無MIN對照]」對照組失去意義。
#   新版：cooldown_days 變獨立參數
#     - 顯式傳值 → 用該值
#     - None + min_hold_days 有設 → 用 min_hold_days（向後相容 v17 行為）
#     - None + min_hold_days 也 None → 0（不設冷卻）
#   策略可在 config 透過 cooldown_days 鍵單獨指定。
#
# 🟡-2: T+1 sell 持倉天數 off-by-1
#   修復：當 reason 是「策略訊號」/「超時」時 days_held + 1
#         （因為實際出場在 i+1 而非 i，舊版少算 1 天）
#
# 🟡-3: cooldown 沒在平倉後重置
#   修復：部位平倉時若該部位是「最近一次進場」，把 last_entry_idx 重設到平倉日，
#         讓平倉之後的冷卻期從平倉日重新計算。
#
# 🟡-4: assert 改 raise ValueError
#   修復：min/max hold days 互斥檢查改為 raise ValueError，UI 可以乾淨地用 try/except 顯示。
#
# 🟡-7: 港股 lot size 取整
#   修復：新增 LOT_SIZE_MAP 和 _floor_to_lot 助手，shares 計算時 floor 到整手。
#         未在 map 中的股票退回到 1 股（舊行為）。
#
# 🟡-10: equity_df 在 T+1 sell 時 record 在次日
#   修復：策略 sell 與超時改用 idx_arr[i+1] 作為 equity 記錄日期，與 cash flow 一致。
#
# v17 修復沿用：
# 🔴 race condition guard（entry_idx >= i 跳過）
# 🔴 策略 sell 改 T+1 close
# 🟡 commission_pct 自動疊加 0.13%
# 🟡 max/min hold days 邊界
# ══════════════════════════════════════════════════════════════════

import pandas as pd
import streamlit as st
from indicators import precompute_signals
from config import B_NAMES, S_NAMES


# ══════════════════════════════════════════════════════════════════
# 🟡-7 V18: 港股 lot size 表（每手股數）
# ══════════════════════════════════════════════════════════════════
# 來源：HKEX 公開資料。常見大型股先填，未列的退回 1（最保守）。
# 備註：lot size 偶會因供股/拆股變動，需要時可在 config.py 維護。
# ══════════════════════════════════════════════════════════════════
LOT_SIZE_MAP = {
    "0700.HK": 100,    # 騰訊
    "9988.HK": 100,    # 阿里巴巴
    "3690.HK": 100,    # 美團
    "1810.HK": 100,    # 小米
    "9618.HK": 100,    # 京東
    "0981.HK": 500,    # 中芯國際
    "0005.HK": 400,    # 匯豐
    "2318.HK": 500,    # 平安
    "1299.HK": 200,    # 友邦
    "0388.HK": 100,    # 港交所
    "0001.HK": 500,    # 長和
    "0939.HK": 1000,   # 建行
    "1398.HK": 1000,   # 工行
    "3988.HK": 1000,   # 中行
    "0857.HK": 2000,   # 中石油
    "0386.HK": 2000,   # 中石化
    "0883.HK": 500,    # 中海油
    "1088.HK": 500,    # 神華
    "0941.HK": 500,    # 中移動
    "0027.HK": 500,    # 銀河
    "1928.HK": 400,    # 金沙
    "2020.HK": 100,    # 安踏
    "1211.HK": 500,    # 比亞迪
    "0175.HK": 500,    # 吉利
    "2333.HK": 500,    # 長城
}


def _floor_to_lot(shares: float, ticker: str = None) -> int:
    """向下取整到整手；未知 ticker 退回 int(shares)（保留舊行為）"""
    s = int(shares)
    if not ticker or ticker not in LOT_SIZE_MAP:
        return s
    lot = LOT_SIZE_MAP[ticker]
    return (s // lot) * lot


# ══════════════════════════════════════════════════════════════════
# 主回測引擎
# ══════════════════════════════════════════════════════════════════

def run_backtest(
    df: pd.DataFrame,
    buy_sigs: tuple, sell_sigs: tuple,
    trade_size: float = 100_000,
    slippage: float = 0.002,
    # 拆分交易成本（向後相容 v17）
    slippage_pct: float = None,
    commission_pct: float = None,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    max_hold_days: int = None,
    min_hold_days: int = None,
    # 🔴-2 V18：cooldown 變獨立參數
    cooldown_days: int = None,
    _precomputed: dict = None,
    market_filter_series: pd.Series = None,
    # 🟡-7 V18：lot size 用
    ticker: str = None,
) -> tuple:
    """
    參數說明（V18）：
      min_hold_days  : 策略 sell 凍結期（進場後 N bar 內忽略策略 sell；止損/止盈仍生效）
      cooldown_days  : 同股加倉冷卻期
                       - 顯式傳值 → 用該值
                       - None + min_hold_days 有設 → 沿用 min_hold_days（v17 行為）
                       - None + min_hold_days 也 None → 0（不冷卻）
      ticker         : 股票代碼，用於 lot size 取整（可選）
    """
    # ── 🟡-4 V18: assert → ValueError ─────────────────────────────
    if min_hold_days and max_hold_days and min_hold_days >= max_hold_days:
        raise ValueError(
            f"min_hold_days ({min_hold_days}) 必須小於 max_hold_days ({max_hold_days})"
        )

    # ── 計算單邊交易成本 ──────────────────────────────────────────
    if slippage_pct is not None:
        one_side_cost = slippage_pct + (commission_pct if commission_pct is not None else 0.0013)
    elif commission_pct is not None:
        one_side_cost = slippage + commission_pct
    else:
        one_side_cost = slippage + 0.0013

    # ── 🔴-2 V18: cooldown 獨立解析 ──────────────────────────────
    if cooldown_days is None:
        # 沒顯式設 → 沿用 min_hold_days（向後相容 v17 預設）
        # 兩者都沒設 → 0（不冷卻，恢復「對照組」原語意）
        effective_cooldown = min_hold_days if min_hold_days is not None else 0
    else:
        effective_cooldown = cooldown_days

    sigs = _precomputed if _precomputed is not None else precompute_signals(df)

    buy_active  = [B_NAMES[k] for k, v in enumerate(buy_sigs)  if v]
    sell_active = [S_NAMES[k] for k, v in enumerate(sell_sigs) if v]

    if buy_active:
        buy_signal = sigs[buy_active[0]].copy()
        for nm in buy_active[1:]:
            buy_signal &= sigs[nm]
    else:
        buy_signal = pd.Series(False, index=df.index)

    if market_filter_series is not None and not market_filter_series.empty:
        hsi_aligned = (
            market_filter_series
            .reindex(df.index, method="ffill")
            .fillna(True)
        )
        buy_signal = buy_signal & hsi_aligned

    if sell_active:
        sell_signal = sigs[sell_active[0]].copy()
        for nm in sell_active[1:]:
            sell_signal |= sigs[nm]
    else:
        sell_signal = pd.Series(False, index=df.index)

    buy_arr   = buy_signal.values
    sell_arr  = sell_signal.values
    close_arr = df["Close"].values.astype(float)
    low_arr   = df["Low"].values.astype(float)
    high_arr  = df["High"].values.astype(float)
    idx_arr   = df.index
    n         = len(df)

    positions = []
    trades    = []
    running_capital = trade_size
    daily_equity    = []

    # ── Pyramiding 追蹤 ──────────────────────────────────────────
    last_entry_idx = -10000

    for i in range(61, n):
        close  = close_arr[i]
        low_i  = low_arr[i]
        high_i = high_arr[i]
        date   = idx_arr[i]

        # ── 嘗試開新倉 ────────────────────────────────────────
        if buy_arr[i] and i + 1 < n:
            days_since_last = i - last_entry_idx
            if days_since_last < effective_cooldown:
                pass  # 冷卻期內，忽略此買訊
            else:
                entry_px   = close_arr[i + 1] * (1 + one_side_cost)
                entry_date = idx_arr[i + 1]
                entry_idx  = i + 1
                # 🟡-7 V18：lot size 取整
                shares = _floor_to_lot(trade_size / entry_px, ticker=ticker)
                if shares > 0:
                    positions.append({
                        "shares": shares, "entry_px": entry_px,
                        "entry_date": entry_date, "entry_idx": entry_idx,
                        "cost": shares * entry_px,
                    })
                    last_entry_idx = entry_idx

        keep = []
        # 記錄當天有沒有 T+1 出場（用於 🟡-10 equity 時序校正）
        any_t1_exit = False

        for pos in positions:
            # race condition guard（entry_idx >= i 跳過，不算當天）
            if pos["entry_idx"] >= i:
                keep.append(pos)
                continue

            days_held = i - pos["entry_idx"]
            ep        = pos["entry_px"]
            reason    = None
            exit_px   = close
            exit_date = date

            strategy_sell_allowed = True
            if min_hold_days and days_held < min_hold_days:
                strategy_sell_allowed = False

            if stop_loss_pct and low_i <= ep * (1 - stop_loss_pct / 100):
                exit_px = ep * (1 - stop_loss_pct / 100)
                reason  = f"止損 -{stop_loss_pct:.0f}%"
            elif take_profit_pct and high_i >= ep * (1 + take_profit_pct / 100):
                exit_px = ep * (1 + take_profit_pct / 100)
                reason  = f"止盈 +{take_profit_pct:.0f}%"
            elif max_hold_days and days_held >= max_hold_days:
                # T+1 出場
                if i + 1 < n:
                    exit_px = close_arr[i + 1] * (1 - one_side_cost)
                    exit_date = idx_arr[i + 1]
                else:
                    exit_px = close * (1 - one_side_cost)
                    exit_date = date
                reason  = f"超時 {max_hold_days}日"
            elif sell_arr[i] and strategy_sell_allowed:
                # T+1 出場
                if i + 1 < n:
                    exit_px = close_arr[i + 1] * (1 - one_side_cost)
                    exit_date = idx_arr[i + 1]
                else:
                    keep.append(pos)
                    continue
                reason  = "策略訊號"

            if reason:
                # ── 🟡-2 V18: T+1 sell 持倉天數 +1 ─────────────────
                # 策略 sell / 超時 都在 i+1 出場，days_held 應該 +1
                # 止損/止盈在 i 當日盤中觸價，days_held 不變
                if reason in ("策略訊號",) or reason.startswith("超時"):
                    actual_days_held = days_held + 1
                else:
                    actual_days_held = days_held

                # sell_date 邏輯
                if reason in ("策略訊號",) or reason.startswith("超時"):
                    sell_date_obj = exit_date if i + 1 < n else date
                    sell_date_str = sell_date_obj.strftime("%Y-%m-%d")
                    any_t1_exit = True
                else:
                    sell_date_obj = date
                    sell_date_str = date.strftime("%Y-%m-%d")

                proceeds = pos["shares"] * exit_px
                pnl_pct  = (exit_px - ep) / ep * 100
                pnl_hkd  = proceeds - pos["cost"]
                running_capital *= (1 + pnl_pct / 100)
                trades.append({
                    "買入日期": pos["entry_date"].strftime("%Y-%m-%d"),
                    "賣出日期": sell_date_str,
                    "買入價": round(ep, 3), "賣出價": round(exit_px, 3),
                    "回報%": round(pnl_pct, 2), "盈虧(HKD)": round(pnl_hkd, 0),
                    "持倉天數": actual_days_held, "賣出原因": reason,
                    "_buy_date": pos["entry_date"], "_sell_date": sell_date_obj,
                    "_win": pnl_pct > 0,
                })

                # ── 🟡-3 V18: 平倉後重置 cooldown ──────────────────
                # 如果這個部位是「最近一次進場」，把 last_entry_idx 改為平倉日，
                # 讓冷卻期從平倉日重算（避免「30 天前買、5 天止損 → 仍冷卻 25 天」）
                if pos["entry_idx"] == last_entry_idx:
                    # 平倉日 = i（止損/止盈）或 i+1（策略 sell / 超時）
                    if reason in ("策略訊號",) or reason.startswith("超時"):
                        last_entry_idx = i + 1 if i + 1 < n else i
                    else:
                        last_entry_idx = i
            else:
                keep.append(pos)
        positions = keep

        # ── 🟡-10 V18: equity 在 T+1 sell 時記在次日 ───────────────
        # 舊版所有 sell 都記在 date(i)，但策略 sell / 超時的 cash flow 實際在 i+1
        # 為了讓 equity curve 與 cash flow 一致，這類 sell 記在 idx_arr[i+1]
        if any_t1_exit and i + 1 < n:
            daily_equity.append({"date": idx_arr[i + 1], "equity": running_capital})
        else:
            daily_equity.append({"date": date, "equity": running_capital})

    # 期末持倉強制平倉
    for pos in positions:
        last_close = close_arr[-1] * (1 - one_side_cost)
        proceeds   = pos["shares"] * last_close
        pnl_pct    = (last_close - pos["entry_px"]) / pos["entry_px"] * 100
        pnl_hkd    = proceeds - pos["cost"]
        running_capital *= (1 + pnl_pct / 100)
        trades.append({
            "買入日期": pos["entry_date"].strftime("%Y-%m-%d"),
            "賣出日期": idx_arr[-1].strftime("%Y-%m-%d") + "（持倉中）",
            "買入價": round(pos["entry_px"], 3), "賣出價": round(last_close, 3),
            "回報%": round(pnl_pct, 2), "盈虧(HKD)": round(pnl_hkd, 0),
            "持倉天數": len(df) - 1 - pos["entry_idx"], "賣出原因": "期末持倉",
            "_buy_date": pos["entry_date"], "_sell_date": idx_arr[-1],
            "_win": pnl_pct > 0,
        })

    if daily_equity:
        equity_df = pd.DataFrame(daily_equity)
        # 🟡-10 V18：可能在同一天有兩筆 record（i 的常規 + i-1 的 T+1 寫到 i），
        # 用 last 保留最後寫入的（最終資金狀態）
        equity_df = equity_df.drop_duplicates(subset=["date"], keep="last").set_index("date")[["equity"]]
    else:
        equity_df = pd.DataFrame()

    return trades, equity_df, trade_size


def calc_bt_metrics(trades, equity_df, trade_size=100_000):
    if not trades:
        return {}
    closed = [t for t in trades if "（持倉中）" not in t["賣出日期"]]
    total  = len(closed)
    if total == 0:
        return {}
    wins   = sum(1 for t in closed if t["_win"])
    losses = total - wins
    win_rate = wins / total * 100

    rets     = [t["回報%"]    for t in closed]
    days_arr = [t["持倉天數"] for t in closed]
    wins_arr = [t["回報%"] for t in closed if t["_win"]]
    loss_arr = [t["回報%"] for t in closed if not t["_win"]]

    avg_ret     = sum(rets)  / total
    avg_win     = sum(wins_arr) / wins   if wins   else 0.0
    avg_loss    = sum(loss_arr) / losses if losses else 0.0
    avg_days    = sum(days_arr) / total
    best_trade  = max(rets)
    worst_trade = min(rets)

    gross_win  = sum(wins_arr)
    gross_loss = abs(sum(loss_arr))
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else (
        float("inf") if gross_win > 0 else 0.0)

    max_consec_loss = cur_consec = 0
    for t in closed:
        cur_consec = cur_consec + 1 if not t["_win"] else 0
        max_consec_loss = max(max_consec_loss, cur_consec)

    max_dd = 0.0
    if not equity_df.empty:
        eq = equity_df["equity"]
        roll_max = eq.cummax()
        dd = (eq - roll_max) / roll_max * 100
        max_dd = float(dd.min()) if not eq.empty and roll_max.max() > 0 else 0.0

    if not equity_df.empty:
        final_equity  = float(equity_df["equity"].iloc[-1])
        total_ret_pct = (final_equity - trade_size) / trade_size * 100
    else:
        final_equity  = trade_size * (1 + avg_ret / 100) ** total
        total_ret_pct = (final_equity - trade_size) / trade_size * 100

    return {
        "平均每筆回報%":  round(avg_ret, 2),
        "交易次數":       total,
        "勝率%":          round(win_rate, 1),
        "平均盈利%":      round(avg_win, 2),
        "平均虧損%":      round(avg_loss, 2),
        "最佳一筆%":      round(best_trade, 2),
        "最差一筆%":      round(worst_trade, 2),
        "平均持倉天數":   round(avg_days, 1),
        "Profit Factor":  profit_factor,
        "最大連輸":       max_consec_loss,
        "最大回撤%":      round(max_dd, 2),
        "累計回報%":      round(total_ret_pct, 2),
        "總回報%":        round(total_ret_pct, 2),
        "最終資金":       round(final_equity, 0),
    }


def run_grid_search(
    df: pd.DataFrame,
    buy_sigs: tuple, sell_sigs: tuple,
    trade_size: float,
    slippage: float,
    sort_metric: str = "平均每筆%",
    market_filter_series: pd.Series = None,
):
    sl_grid = [0, 5, 10, 15, 20]
    tp_grid = [0, 15, 30, 50]
    md_grid = [0, 20, 40, 60]

    combos  = [(sl, tp, md) for sl in sl_grid for tp in tp_grid for md in md_grid]
    total_c = len(combos)
    results = []

    pre_s = precompute_signals(df)

    pbar = st.progress(0, text="網格搜索中...")
    for ci, (sl, tp, md) in enumerate(combos):
        pbar.progress((ci + 1) / total_c, text=f"網格搜索 {ci+1}/{total_c}...")
        t, eq, _ = run_backtest(
            df, buy_sigs, sell_sigs,
            trade_size=trade_size, slippage=slippage,
            stop_loss_pct=sl  if sl  > 0 else None,
            take_profit_pct=tp if tp > 0 else None,
            max_hold_days=md   if md  > 0 else None,
            _precomputed=pre_s,
            market_filter_series=market_filter_series,
        )
        m = calc_bt_metrics(t, eq, trade_size)
        if m and m["交易次數"] >= 2:
            results.append({
                "止損%":     f"{sl}%" if sl > 0 else "不限",
                "止盈%":     f"{tp}%" if tp > 0 else "不限",
                "最長持倉":  f"{md}日" if md > 0 else "不限",
                "平均每筆%": m["平均每筆回報%"],
                "勝率%":     m["勝率%"],
                "Profit F":  m["Profit Factor"],
                "最大回撤%": m["最大回撤%"],
                "交易次數":  m["交易次數"],
                "最大連輸":  m["最大連輸"],
            })
    pbar.empty()

    if not results:
        return pd.DataFrame()

    df_gs = pd.DataFrame(results)
    asc   = (sort_metric == "最大回撤%")
    return df_gs.sort_values(sort_metric, ascending=asc).reset_index(drop=True)


def build_hsi_filter(hsi_df: pd.DataFrame) -> pd.Series:
    """
    輸入：已含 MA20 / MA60 的恒指 DataFrame
    輸出：pd.Series[bool]，True = 恒指 MA20 > MA60（允許入場）
    """
    if hsi_df.empty or "MA20" not in hsi_df.columns or "MA60" not in hsi_df.columns:
        return pd.Series(dtype=bool)
    return (hsi_df["MA20"] > hsi_df["MA60"]).rename("hsi_bullish")

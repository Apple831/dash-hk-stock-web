# ══════════════════════════════════════════════════════════════════
# walk_forward.py -- Walk-Forward 驗證引擎 & 報告渲染
# ══════════════════════════════════════════════════════════════════
#
# V18 修復（2026-04-27）-- 來自 V17.0 策略複審報告 🔴-1：
#   • _merge_buy_sigs 改為「自動對齊長度」（短的補 False），
#     不再依賴呼叫端傳入正確的元素數。
#   • run_walk_forward / run_portfolio_walk_forward 兩處 (False,)*10 → 不再硬編碼，
#     用新版 _merge_buy_sigs 統一處理。
#   • 兩個入口新增 cooldown_days 參數並透傳到 run_backtest。
#
# v17 行為沿用：方案 A 延伸追蹤、退化率 N/A 處理、強制平倉拆分。
# ══════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from indicators import calculate_indicators, precompute_signals
from backtest import run_backtest, calc_bt_metrics, build_hsi_filter


# ══════════════════════════════════════════════════════════════════
# 🔴-1 V18: _merge_buy_sigs 自動對齊長度
# ══════════════════════════════════════════════════════════════════
def _merge_buy_sigs(buy_sigs: tuple, extra_buy: tuple) -> tuple:
    """
    把 buy_sigs 與 extra_buy 用 OR 合併。
    自動對齊長度 -- 短的那個補 False，避免「11 zip 10 → b11 被靜默丟」的潛伏 bug。
    """
    if not extra_buy or not any(extra_buy):
        return buy_sigs
    n = max(len(buy_sigs), len(extra_buy))
    a = tuple(buy_sigs)  + (False,) * (n - len(buy_sigs))
    b = tuple(extra_buy) + (False,) * (n - len(extra_buy))
    return tuple(x or y for x, y in zip(a, b))


# ── helper：把 OOS 交易分成策略出場 vs 期末強制平倉 ─────────────────
def _split_oos_trades(trades: list) -> tuple:
    """
    strategy_trades：賣出原因為策略訊號 / 止損 / 止盈 / 超時
    forced_trades：Fold 結束強制平倉（賣出日期含「持倉中」）
    """
    strategy = [t for t in trades if "（持倉中）" not in t.get("賣出日期", "")]
    forced   = [t for t in trades if "（持倉中）"     in t.get("賣出日期", "")]
    return strategy, forced


# ══════════════════════════════════════════════════════════════════
# 方案 A：延伸追蹤強制平倉交易（純診斷，不計入 WF metrics）
# ══════════════════════════════════════════════════════════════════
def _get_extended_trades(
    full_df: pd.DataFrame,
    effective_buy: tuple,
    sell_sigs: tuple,
    oos_start_date, oos_end_date,
    trade_size: float, slippage: float,
    stop_loss_pct, take_profit_pct, max_hold_days,
    hsi_filter: pd.Series,
    min_hold_days=None,
    cooldown_days=None,
    max_extension_days: int = 365,
) -> list:
    if full_df is None or full_df.empty:
        return []

    oos_end_idx = full_df.index.searchsorted(oos_end_date, side="right")
    if oos_end_idx >= len(full_df):
        return []  # 無數據可延伸

    extended_end_idx = min(oos_end_idx + max_extension_days, len(full_df))
    warmup_start     = max(0, full_df.index.searchsorted(oos_start_date) - 61)
    extended_slice   = full_df.iloc[warmup_start:extended_end_idx].copy()
    extended_slice   = calculate_indicators(extended_slice)

    if len(extended_slice) < 62:
        return []

    try:
        bt_kw = {}
        if min_hold_days is not None:
            bt_kw["min_hold_days"] = min_hold_days
        if cooldown_days is not None:
            bt_kw["cooldown_days"] = cooldown_days

        extended_trades, _, _ = run_backtest(
            extended_slice, effective_buy, sell_sigs,
            trade_size=trade_size, slippage=slippage,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            max_hold_days=max_hold_days,
            _precomputed=None,
            market_filter_series=hsi_filter,
            **bt_kw,
        )
    except Exception:
        return []

    # 保留「OOS 內進場，OOS 結束後才出場」的交易
    result = []
    for t in extended_trades:
        buy_d  = t["_buy_date"]
        sell_d = t["_sell_date"]
        if buy_d < oos_start_date or buy_d > oos_end_date:
            continue
        if sell_d <= oos_end_date:
            continue
        t_copy = {**t}
        t_copy["_is_extended"] = True
        t_copy["_still_held_at_end"] = "（持倉中）" in t.get("賣出日期", "")
        result.append(t_copy)

    return result


# ══════════════════════════════════════════════════════════════════
# 單股 Walk-Forward
# ══════════════════════════════════════════════════════════════════

def run_walk_forward(
    df: pd.DataFrame,
    buy_sigs: tuple, sell_sigs: tuple,
    is_months: int = 12,
    oos_months: int = 3,
    trade_size: float = 100_000,
    slippage: float = 0.002,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    max_hold_days: int = None,
    min_hold_days: int = None,
    cooldown_days: int = None,   # 🔴-2 V18 透傳
    min_oos_trades: int = 3,
    hsi_filter: pd.Series = None,
    extra_buy_sigs: tuple = None,
    track_extended: bool = True,
) -> list:
    if df.empty or len(df) < 60:
        return []

    # 🔴-1 V18：_merge_buy_sigs 自己對齊長度，extra_buy_sigs 不必硬編碼長度
    effective_buy = _merge_buy_sigs(buy_sigs, extra_buy_sigs or ())

    # backtest kwargs（避免重複傳 None）
    def _bt_kw():
        kw = {}
        if min_hold_days is not None:
            kw["min_hold_days"] = min_hold_days
        if cooldown_days is not None:
            kw["cooldown_days"] = cooldown_days
        return kw

    results    = []
    total_days = len(df)
    is_days    = int(is_months  * 21)
    oos_days   = int(oos_months * 21)
    step       = oos_days
    fold       = 1
    start      = 0

    while start + is_days + oos_days <= total_days:
        is_df  = df.iloc[start : start + is_days].copy()
        oos_df = df.iloc[start + is_days : start + is_days + oos_days].copy()

        if len(is_df) < 62 or len(oos_df) < 10:
            break

        # ── IS ───────────────────────────────────────────────────
        pre_is = precompute_signals(is_df)
        is_trades, is_equity, _ = run_backtest(
            is_df, effective_buy, sell_sigs,
            trade_size=trade_size, slippage=slippage,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            max_hold_days=max_hold_days,
            _precomputed=pre_is,
            market_filter_series=hsi_filter,
            **_bt_kw(),
        )
        is_metrics = calc_bt_metrics(is_trades, is_equity, trade_size)

        # ── OOS（含 61 日 warmup）─────────────────────────────────
        warmup_start = max(0, start + is_days - 61)
        oos_full     = df.iloc[warmup_start : start + is_days + oos_days].copy()
        oos_full     = calculate_indicators(oos_full)

        oos_trades_all, _, _ = run_backtest(
            oos_full, effective_buy, sell_sigs,
            trade_size=trade_size, slippage=slippage,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            max_hold_days=max_hold_days,
            _precomputed=None,
            market_filter_series=hsi_filter,
            **_bt_kw(),
        )

        oos_start_date = oos_df.index[0]
        oos_end_date   = oos_df.index[-1]
        oos_trades     = [t for t in oos_trades_all if t["_buy_date"] >= oos_start_date]

        oos_strategy_trades, oos_forced_trades = _split_oos_trades(oos_trades)

        # equity curve 只用策略出場
        if oos_strategy_trades:
            sell_map: dict = {}
            for t in oos_strategy_trades:
                sell_map.setdefault(t["_sell_date"], []).append(t["回報%"])
            running_capital = trade_size
            eq_rows = []
            for date in oos_df.index:
                if date in sell_map:
                    for pnl_pct in sell_map[date]:
                        running_capital *= (1 + pnl_pct / 100)
                eq_rows.append({"date": date, "equity": running_capital})
            oos_equity = pd.DataFrame(eq_rows).set_index("date")
        else:
            oos_equity = pd.DataFrame(
                {"equity": [trade_size] * len(oos_df)}, index=oos_df.index,
            )

        oos_metrics = calc_bt_metrics(oos_strategy_trades, oos_equity, trade_size)
        valid_oos   = len(oos_strategy_trades) >= min_oos_trades

        # ── 方案 A：延伸追蹤 ──────────────────────────────────────
        oos_extended_trades = []
        if track_extended and oos_forced_trades:
            oos_extended_trades = _get_extended_trades(
                df, effective_buy, sell_sigs,
                oos_start_date, oos_end_date,
                trade_size, slippage,
                stop_loss_pct, take_profit_pct, max_hold_days,
                hsi_filter,
                min_hold_days=min_hold_days,
                cooldown_days=cooldown_days,
            )

        results.append({
            "fold":                fold,
            "is_start":            is_df.index[0],  "is_end":   is_df.index[-1],
            "oos_start":           oos_df.index[0], "oos_end":  oos_df.index[-1],
            "is_metrics":          is_metrics  or {},
            "oos_metrics":         oos_metrics or {},
            "is_trades":           is_trades,
            "oos_trades":          oos_strategy_trades,
            "oos_forced_trades":   oos_forced_trades,
            "oos_extended_trades": oos_extended_trades,
            "is_equity":           is_equity,
            "oos_equity":          oos_equity,
            "valid_oos":           valid_oos,
            "oos_trade_count":     len(oos_strategy_trades),
            "forced_exit_count":   len(oos_forced_trades),
            "extended_count":      len(oos_extended_trades),
            "n_stocks":            1,
        })

        start += step
        fold  += 1

    return results


# ══════════════════════════════════════════════════════════════════
# 投資組合 Walk-Forward
# ══════════════════════════════════════════════════════════════════

def _build_portfolio_equity(
    trades: list, date_range: pd.DatetimeIndex, trade_size: float,
) -> pd.DataFrame:
    if len(date_range) == 0:
        return pd.DataFrame()
    sell_map: dict = {}
    for t in trades:
        if "（持倉中）" not in t.get("賣出日期", ""):
            pnl_hkd = trade_size * t["回報%"] / 100
            sell_map.setdefault(t["_sell_date"], []).append(pnl_hkd)
    running_pnl = 0.0
    eq_rows = []
    for date in date_range:
        if date in sell_map:
            running_pnl += sum(sell_map[date])
        eq_rows.append({"date": date, "equity": trade_size + running_pnl})
    return pd.DataFrame(eq_rows).set_index("date")


def run_portfolio_walk_forward(
    stock_data: dict,
    buy_sigs: tuple,
    sell_sigs: tuple,
    is_months: int = 12,
    oos_months: int = 6,
    trade_size: float = 100_000,
    slippage: float = 0.002,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    max_hold_days: int = None,
    min_hold_days: int = None,
    cooldown_days: int = None,   # 🔴-2 V18 透傳
    min_oos_trades: int = 5,
    hsi_filter: pd.Series = None,
    extra_buy_sigs: tuple = None,
    track_extended: bool = True,
) -> list:
    if not stock_data:
        return []

    # 🔴-1 V18：_merge_buy_sigs 自己對齊長度
    effective_buy = _merge_buy_sigs(buy_sigs, extra_buy_sigs or ())

    def _bt_kw():
        kw = {}
        if min_hold_days is not None:
            kw["min_hold_days"] = min_hold_days
        if cooldown_days is not None:
            kw["cooldown_days"] = cooldown_days
        return kw

    ref_df     = max(stock_data.values(), key=len)
    all_dates  = ref_df.index
    total_days = len(all_dates)
    is_days    = int(is_months  * 21)
    oos_days   = int(oos_months * 21)

    if total_days < is_days + oos_days:
        return []

    results       = []
    fold          = 1
    start         = 0
    n_total_folds = max(1, (total_days - is_days) // oos_days)

    pbar   = st.progress(0, text="投資組合 Walk-Forward 啟動...")
    status = st.empty()

    while start + is_days + oos_days <= total_days:
        pbar.progress(
            min((fold - 1) / n_total_folds, 0.99),
            text=f"Fold {fold}／約 {n_total_folds} -- 正在跑 {len(stock_data)} 隻股票...",
        )

        is_start_date  = all_dates[start]
        is_end_date    = all_dates[start + is_days - 1]
        oos_start_date = all_dates[start + is_days]
        oos_end_idx    = min(start + is_days + oos_days - 1, total_days - 1)
        oos_end_date   = all_dates[oos_end_idx]

        all_is_trades       = []
        all_oos_trades      = []
        all_extended_trades = []
        n_stocks_run        = 0

        for ticker, full_df in stock_data.items():
            if full_df is None or full_df.empty or len(full_df) < 62:
                continue
            status.text(f"Fold {fold} -- {ticker}")

            is_mask = (full_df.index >= is_start_date) & (full_df.index <= is_end_date)
            is_df   = full_df[is_mask].copy()
            if len(is_df) < 62:
                continue

            pre_is = precompute_signals(is_df)
            # 🟡-7 V18：透傳 ticker 給 lot size 邏輯
            is_t, _, _ = run_backtest(
                is_df, effective_buy, sell_sigs,
                trade_size=trade_size, slippage=slippage,
                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                max_hold_days=max_hold_days,
                _precomputed=pre_is,
                market_filter_series=hsi_filter,
                ticker=ticker,
                **_bt_kw(),
            )
            for t in is_t:
                t["ticker"] = ticker
            all_is_trades.extend(is_t)

            oos_start_pos = full_df.index.searchsorted(oos_start_date)
            warmup_pos    = max(0, oos_start_pos - 61)
            oos_full_df   = full_df.iloc[warmup_pos:].copy()
            oos_full_df   = oos_full_df[oos_full_df.index <= oos_end_date].copy()
            oos_full_df   = calculate_indicators(oos_full_df)

            if len(oos_full_df) < 10:
                continue

            oos_t_all, _, _ = run_backtest(
                oos_full_df, effective_buy, sell_sigs,
                trade_size=trade_size, slippage=slippage,
                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                max_hold_days=max_hold_days,
                _precomputed=None,
                market_filter_series=hsi_filter,
                ticker=ticker,
                **_bt_kw(),
            )
            oos_t = [t for t in oos_t_all if t["_buy_date"] >= oos_start_date]
            for t in oos_t:
                t["ticker"] = ticker
            all_oos_trades.extend(oos_t)

            # ── 方案 A：per-ticker 延伸追蹤 ──────────────────────
            if track_extended:
                has_forced = any("（持倉中）" in t.get("賣出日期", "") for t in oos_t)
                if has_forced:
                    ticker_extended = _get_extended_trades(
                        full_df, effective_buy, sell_sigs,
                        oos_start_date, oos_end_date,
                        trade_size, slippage,
                        stop_loss_pct, take_profit_pct, max_hold_days,
                        hsi_filter,
                        min_hold_days=min_hold_days,
                        cooldown_days=cooldown_days,
                    )
                    for t in ticker_extended:
                        t["ticker"] = ticker
                    all_extended_trades.extend(ticker_extended)

            n_stocks_run += 1

        is_date_range  = ref_df.index[(ref_df.index >= is_start_date)  & (ref_df.index <= is_end_date)]
        oos_date_range = ref_df.index[(ref_df.index >= oos_start_date) & (ref_df.index <= oos_end_date)]

        oos_strategy_trades, oos_forced_trades = _split_oos_trades(all_oos_trades)

        is_equity  = _build_portfolio_equity(all_is_trades,       is_date_range,  trade_size)
        oos_equity = _build_portfolio_equity(oos_strategy_trades, oos_date_range, trade_size)

        if oos_equity.empty:
            oos_equity = pd.DataFrame(
                {"equity": [trade_size] * len(oos_date_range)}, index=oos_date_range,
            )

        is_metrics  = calc_bt_metrics(all_is_trades,       is_equity,  trade_size)
        oos_metrics = calc_bt_metrics(oos_strategy_trades, oos_equity, trade_size)

        valid_oos = len(oos_strategy_trades) >= min_oos_trades

        results.append({
            "fold":                fold,
            "is_start":            is_start_date,  "is_end":   is_end_date,
            "oos_start":           oos_start_date, "oos_end":  oos_end_date,
            "is_metrics":          is_metrics  or {},
            "oos_metrics":         oos_metrics or {},
            "is_trades":           all_is_trades,
            "oos_trades":          oos_strategy_trades,
            "oos_forced_trades":   oos_forced_trades,
            "oos_extended_trades": all_extended_trades,
            "is_equity":           is_equity,
            "oos_equity":          oos_equity,
            "valid_oos":           valid_oos,
            "oos_trade_count":     len(oos_strategy_trades),
            "forced_exit_count":   len(oos_forced_trades),
            "extended_count":      len(all_extended_trades),
            "n_stocks":            n_stocks_run,
        })

        start += oos_days
        fold  += 1

    pbar.empty()
    status.empty()
    return results


# ══════════════════════════════════════════════════════════════════
# 共用：退化率 & 延伸追蹤摘要
# ══════════════════════════════════════════════════════════════════

def _wf_degradation(is_ret: float, oos_ret: float) -> float:
    if abs(is_ret) < 0.5:
        return None
    return (is_ret - oos_ret) / abs(is_ret) * 100


def _extended_summary(extended_trades: list) -> dict:
    if not extended_trades:
        return {}
    closed = [t for t in extended_trades if not t.get("_still_held_at_end", False)]
    still  = [t for t in extended_trades if     t.get("_still_held_at_end", False)]
    if not closed:
        return {"total": len(extended_trades), "closed": 0, "still_held": len(still)}
    rets    = [t["回報%"] for t in closed]
    wins    = sum(1 for r in rets if r > 0)
    avg_ret = sum(rets) / len(rets)
    avg_day = sum(t["持倉天數"] for t in closed) / len(closed)
    return {
        "total":      len(extended_trades),
        "closed":     len(closed),
        "still_held": len(still),
        "avg_return": round(avg_ret, 2),
        "win_rate":   round(wins / len(closed) * 100, 1),
        "avg_days":   round(avg_day, 1),
        "best":       round(max(rets), 2),
        "worst":      round(min(rets), 2),
    }


# ══════════════════════════════════════════════════════════════════
# 結果展示（與 v17 同，只是依新的 metrics 顯示）
# ══════════════════════════════════════════════════════════════════

def show_walk_forward_results(wf_results: list, trade_size: float, is_portfolio: bool = False):
    if not wf_results:
        st.warning("⚠️ 沒有足夠數據完成 Walk-Forward，請拉長回測週期或縮短 IS/OOS 窗口。")
        return

    rows = []
    for r in wf_results:
        im  = r["is_metrics"]
        om  = r["oos_metrics"]
        is_ret  = im.get("平均每筆回報%", 0.0)
        oos_ret = om.get("平均每筆回報%", 0.0)
        deg     = _wf_degradation(is_ret, oos_ret)
        deg_display = f"{deg:.1f}%" if deg is not None else "N/A (IS≈0)"
        forced_n   = r.get("forced_exit_count", 0)
        extended_n = r.get("extended_count", 0)
        row = {
            "Fold":          r["fold"],
            "IS 期間":       f"{r['is_start'].strftime('%Y-%m')} → {r['is_end'].strftime('%Y-%m')}",
            "OOS 期間":      f"{r['oos_start'].strftime('%Y-%m')} → {r['oos_end'].strftime('%Y-%m')}",
            "IS 均回報%":    round(is_ret, 2),
            "OOS 均回報%":   round(oos_ret, 2),
            "退化率%":       deg_display,
            "IS 勝率%":      round(im.get("勝率%", 0.0), 1),
            "OOS 勝率%":     round(om.get("勝率%", 0.0), 1),
            "IS 交易數":     im.get("交易次數", 0),
            "OOS 交易數":    r["oos_trade_count"],
            "強制平倉數":    forced_n,
            "延伸追蹤數":    extended_n,
            "有效":          "✅" if r["valid_oos"] else f"⚠️ 僅{r['oos_trade_count']}筆",
            "_deg_raw":      deg,
        }
        if is_portfolio:
            row["股票數"] = r.get("n_stocks", "-")
        rows.append(row)

    df_summary = pd.DataFrame(rows)

    valid_rows    = [r for r in rows if "✅" in r["有效"] and r["_deg_raw"] is not None]
    invalid_count = len(rows) - len(valid_rows)

    if invalid_count > 0:
        hint = "建議改用投資組合模式或拉長 OOS 窗口。" if not is_portfolio \
               else "建議增加股票數量或減少入場條件。"
        st.warning(f"⚠️ **{invalid_count} 個 Fold** OOS 交易不足或 IS≈0，已排除在評分之外。{hint}")

    # 全程強制平倉 + 延伸追蹤總覽
    total_forced    = sum(r.get("forced_exit_count", 0) for r in wf_results)
    all_extended    = [t for r in wf_results for t in r.get("oos_extended_trades", [])]
    ext_summary_all = _extended_summary(all_extended)

    if total_forced > 0:
        ext_text = ""
        if ext_summary_all and ext_summary_all.get("closed", 0) > 0:
            closed    = ext_summary_all["closed"]
            still     = ext_summary_all["still_held"]
            avg       = ext_summary_all.get("avg_return", 0)
            wr        = ext_summary_all.get("win_rate", 0)
            avg_days  = ext_summary_all.get("avg_days", 0)
            sign      = "+" if avg >= 0 else ""
            ext_text = (
                f"  \n🔍 **延伸追蹤**：{closed} 筆已觸發真實出場"
                f"（平均 {sign}{avg:.2f}%，勝率 {wr:.1f}%，平均持倉 {avg_days:.0f} 天）"
            )
            if still > 0:
                ext_text += f"；{still} 筆延伸後仍持倉未出（超長持有）"

        st.info(
            f"ℹ️ 全程 **{total_forced} 筆期末強制平倉**（Fold 邊界截斷，"
            f"已從指標及 equity curve 排除）。{ext_text}",
        )

    if not valid_rows:
        st.error("❌ 所有 Fold 均未達標，無法評估策略。")
        _show_summary_table(df_summary, is_portfolio)
        return

    avg_is       = sum(r["IS 均回報%"]  for r in valid_rows) / len(valid_rows)
    avg_oos      = sum(r["OOS 均回報%"] for r in valid_rows) / len(valid_rows)
    avg_deg      = sum(r["_deg_raw"]    for r in valid_rows) / len(valid_rows)
    oos_positive = sum(1 for r in valid_rows if r["OOS 均回報%"] > 0)
    oos_rate     = oos_positive / len(valid_rows) * 100

    if avg_oos > 0 and avg_deg < 40 and oos_rate >= 60:
        verdict, verdict_color = "🟢 策略穩健（具備真實 Alpha）", "#26a69a"
        verdict_detail = f"OOS 正回報比率 {oos_rate:.0f}%，退化率 {avg_deg:.1f}% < 40%，策略很可能在實盤有效。"
    elif avg_oos > 0 and avg_deg < 65 and oos_rate >= 50:
        verdict, verdict_color = "🟡 策略尚可（輕度過擬合）", "#f9a825"
        verdict_detail = f"OOS 仍有正回報但退化率 {avg_deg:.1f}% 偏高。建議加入更嚴格條件或延長驗證期。"
    elif avg_oos <= 0:
        verdict, verdict_color = "🔴 策略危險（OOS 虧損）", "#ef5350"
        verdict_detail = f"OOS 平均回報 {avg_oos:.2f}%，策略在未見過的數據上虧損，不應實盤使用。"
    else:
        verdict, verdict_color = "🔴 策略過擬合（嚴重退化）", "#ef5350"
        verdict_detail = f"退化率 {avg_deg:.1f}% 過高，IS 回報無法在 OOS 重現。"

    mode_label = "（投資組合）" if is_portfolio else "（單股）"
    st.markdown(
        f"<div style='background:rgba(255,255,255,0.05);"
        f"border-left:4px solid {verdict_color};"
        f"padding:12px 18px;border-radius:6px;margin-bottom:12px'>"
        f"<div style='font-size:20px;font-weight:bold'>{verdict} {mode_label}</div>"
        f"<div style='font-size:13px;margin-top:4px;opacity:0.85'>{verdict_detail}</div>"
        f"<div style='font-size:12px;margin-top:6px;opacity:0.6'>"
        f"有效 Fold：{len(valid_rows)}/{len(rows)}　｜　無效：{invalid_count}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("IS 平均每筆%",    f"{avg_is:+.2f}%")
    c2.metric("OOS 平均每筆%",   f"{avg_oos:+.2f}%",
              delta=f"{avg_oos - avg_is:+.2f}%", delta_color="normal")
    c3.metric("平均退化率",      f"{avg_deg:.1f}%",
              delta="優" if avg_deg < 40 else ("可接受" if avg_deg < 65 else "過高"),
              delta_color="off")
    c4.metric("OOS 正回報 Fold", f"{oos_positive}/{len(valid_rows)}")
    c5.metric("有效 Fold 數",    f"{len(valid_rows)}/{len(rows)}")

    # ── 延伸追蹤對比 ─────────────────────────────────────────────
    if ext_summary_all and ext_summary_all.get("closed", 0) > 0:
        st.divider()
        st.markdown("### 🔍 延伸追蹤：強制平倉交易的真實結果")
        st.caption(
            "把原本在 Fold 邊界被強制平倉的交易保留，用全期數據繼續持有到真實 sell 信號觸發"
            "（或 365 日上限）。純診斷用途，**不計入上方 WF 指標**。"
        )

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("真實出場交易數",
                  f"{ext_summary_all['closed']} 筆",
                  delta=f"共 {ext_summary_all['total']} 筆中",
                  delta_color="off")
        ext_avg = ext_summary_all["avg_return"]
        e2.metric("真實出場均回報%",
                  f"{'+' if ext_avg >= 0 else ''}{ext_avg:.2f}%",
                  delta=f"vs OOS {avg_oos:+.2f}%",
                  delta_color="normal")
        e3.metric("真實出場勝率", f"{ext_summary_all['win_rate']:.1f}%")
        e4.metric("平均持倉天數", f"{ext_summary_all['avg_days']:.0f} 天")

        if ext_avg < avg_oos - 3:
            st.error(
                f"⚠️ **警示：疑似 survivorship bias**　"
                f"WF 指標 OOS {avg_oos:+.2f}%，但加入原本被強制平倉的交易後真實均回報只有 "
                f"{ext_avg:+.2f}%。原本的高 OOS 數字可能是只統計「跑完全程」的贏家所致。"
            )
        elif ext_avg > avg_oos:
            st.success(
                f"✅ 強制平倉交易的真實結果（{ext_avg:+.2f}%）比 WF OOS 指標"
                f"（{avg_oos:+.2f}%）**更好**，說明原本 WF 數字沒有高估策略，策略紮實。"
            )

        if ext_summary_all.get("still_held", 0) > 0:
            st.caption(
                f"ℹ️ {ext_summary_all['still_held']} 筆即使延伸 365 日仍未觸發 sell 信號，"
                f"按延伸期末收盤出場計算。這類交易的真實結果仍不可知。"
            )

    st.divider()

    st.markdown("### 📊 逐 Fold IS vs OOS 平均每筆回報%")
    fold_labels = [
        f"Fold {r['Fold']}\n{r['OOS 期間'].split(' → ')[0]}"
        + ("" if r["有效"] == "✅" else " ⚠️")
        for r in rows
    ]
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        name="In-Sample", x=fold_labels,
        y=[r["IS 均回報%"] for r in rows],
        marker_color=["rgba(100,180,255,0.7)" if r["有效"] == "✅" else "rgba(100,180,255,0.25)" for r in rows],
        text=[f"{v:+.1f}%" for v in [r["IS 均回報%"] for r in rows]],
        textposition="outside",
    ))
    fig_bar.add_trace(go.Bar(
        name="Out-of-Sample", x=fold_labels,
        y=[r["OOS 均回報%"] for r in rows],
        marker_color=[
            ("#26a69a" if r["OOS 均回報%"] >= 0 else "#ef5350") if r["有效"] == "✅"
            else "rgba(128,128,128,0.3)"
            for r in rows
        ],
        text=[f"{v:+.1f}%" for v in [r["OOS 均回報%"] for r in rows]],
        textposition="outside",
    ))
    fig_bar.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
    fig_bar.update_layout(
        barmode="group", height=380, margin=dict(t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("### 📉 退化率趨勢（灰色 = 無效 Fold 或 IS≈0）")
    deg_vals  = [r["_deg_raw"] if r["_deg_raw"] is not None else 0 for r in rows]
    deg_texts = [f"{r['退化率%']}" for r in rows]
    fig_deg = go.Figure()
    fig_deg.add_trace(go.Scatter(
        x=[f"Fold {r['Fold']}" for r in rows],
        y=deg_vals,
        mode="lines+markers+text",
        text=deg_texts,
        textposition="top center",
        line=dict(color="#f9a825", width=2),
        marker=dict(
            size=10,
            color=[
                "rgba(150,150,150,0.4)" if (not wf_r["valid_oos"] or r["_deg_raw"] is None)
                else ("#26a69a" if d < 40 else ("#f9a825" if d < 65 else "#ef5350"))
                for r, wf_r, d in zip(rows, wf_results, deg_vals)
            ],
        ),
    ))
    fig_deg.add_hline(y=40, line_dash="dot", line_color="rgba(38,166,154,0.6)",
                      annotation_text="40% 健康線", annotation_position="right")
    fig_deg.add_hline(y=65, line_dash="dot", line_color="rgba(239,83,80,0.6)",
                      annotation_text="65% 警戒線", annotation_position="right")
    fig_deg.update_layout(
        height=280, margin=dict(t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%", yaxis_title="退化率%",
    )
    st.plotly_chart(fig_deg, use_container_width=True)

    st.markdown("### 📈 OOS 拼接資金曲線（只含有效 Fold）")
    oos_pieces      = []
    running_capital = trade_size
    for r in wf_results:
        if not r["valid_oos"]:
            continue
        eq = r["oos_equity"]
        if eq.empty:
            continue
        scale = running_capital / trade_size
        piece = eq["equity"] * scale
        oos_pieces.append(piece)
        running_capital = float(piece.iloc[-1])

    if oos_pieces:
        oos_combined = pd.concat(oos_pieces)
        oos_combined = oos_combined[~oos_combined.index.duplicated(keep="last")].sort_index()
        oos_norm     = oos_combined / trade_size * 100 - 100
        final_ret    = float(oos_norm.iloc[-1])

        fig_oos = go.Figure()
        fig_oos.add_trace(go.Scatter(
            x=oos_norm.index, y=oos_norm,
            fill="tozeroy",
            line=dict(color="#26a69a" if final_ret >= 0 else "#ef5350", width=2),
            fillcolor="rgba(38,166,154,0.12)" if final_ret >= 0 else "rgba(239,83,80,0.12)",
        ))
        fig_oos.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
        fig_oos.add_annotation(
            text=f"OOS 總回報：{final_ret:+.1f}%",
            xref="paper", yref="paper", x=0.02, y=0.95, showarrow=False,
            font=dict(size=14, color="#26a69a" if final_ret >= 0 else "#ef5350"),
        )
        fig_oos.update_layout(
            height=300, margin=dict(t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis_ticksuffix="%",
        )
        st.plotly_chart(fig_oos, use_container_width=True)
    else:
        st.info("沒有有效 Fold，無法繪製 OOS 拼接曲線。")

    st.divider()
    st.markdown("### 📑 逐 Fold 詳細數據")
    _show_summary_table(df_summary, is_portfolio)

    st.divider()
    st.markdown("### 🔬 逐 Fold 交易記錄")
    for r, row in zip(wf_results, rows):
        fold_n     = r["fold"]
        im         = r["is_metrics"]
        om         = r["oos_metrics"]
        valid      = r["valid_oos"]
        forced_n   = r.get("forced_exit_count", 0)
        extended_n = r.get("extended_count", 0)

        label = (
            f"{'✅' if valid else '⚠️'} Fold {fold_n}  ｜  "
            f"OOS: {r['oos_start'].strftime('%Y-%m-%d')} → {r['oos_end'].strftime('%Y-%m-%d')}  ｜  "
            f"IS {im.get('平均每筆回報%', 0):+.2f}%  →  OOS {om.get('平均每筆回報%', 0):+.2f}%"
            + (f"  ｜  策略出場 {r['oos_trade_count']} 筆" if valid else f"  ｜  ⚠️ 僅 {r['oos_trade_count']} 筆OOS")
            + (f"  ｜  強制 {forced_n} 延伸 {extended_n}" if forced_n > 0 else "")
        )
        with st.expander(label):
            if not valid:
                st.warning(f"⚠️ 此 Fold OOS 僅 **{r['oos_trade_count']} 筆**策略出場，排除在評分之外。")
            if forced_n > 0:
                st.caption(
                    f"ℹ️ 本 Fold 有 **{forced_n} 筆期末強制平倉**（不計入指標）"
                    + (f"，其中 **{extended_n} 筆**已延伸追蹤到真實結果" if extended_n else "")
                    + "。"
                )
            if is_portfolio and r.get("n_stocks"):
                st.caption(f"本 Fold 實際跑 {r['n_stocks']} 隻股票")

            col_is, col_oos = st.columns(2)
            with col_is:
                st.markdown("**📘 In-Sample**")
                if im:
                    st.metric("均回報%",  f"{im.get('平均每筆回報%', 0):+.2f}%")
                    st.metric("勝率",     f"{im.get('勝率%', 0):.1f}%")
                    st.metric("交易次數", f"{im.get('交易次數', 0)}")
                    pf = im.get("Profit Factor", 0)
                    st.metric("Profit F", "∞" if pf == float("inf") else f"{pf:.2f}")
                    st.metric("最大回撤", f"{im.get('最大回撤%', 0):.2f}%")
                else:
                    st.info("無交易")
            with col_oos:
                st.markdown("**📗 Out-of-Sample（策略出場）**")
                if om:
                    oos_ret  = om.get("平均每筆回報%", 0)
                    is_ret_v = im.get("平均每筆回報%", 0)
                    deg_v    = _wf_degradation(is_ret_v, oos_ret)
                    deg_str  = f"退化 {deg_v:.1f}%" if deg_v is not None else "IS≈0，退化率無效"
                    st.metric("均回報%",  f"{oos_ret:+.2f}%", delta=deg_str, delta_color="off")
                    st.metric("勝率",     f"{om.get('勝率%', 0):.1f}%")
                    st.metric("交易次數", f"{om.get('交易次數', 0)}")
                    pf = om.get("Profit Factor", 0)
                    st.metric("Profit F", "∞" if pf == float("inf") else f"{pf:.2f}")
                    st.metric("最大回撤", f"{om.get('最大回撤%', 0):.2f}%")
                else:
                    st.info("無交易（OOS 期間無訊號）")

            display_cols = ["買入日期", "賣出日期", "買入價", "賣出價",
                            "回報%", "盈虧(HKD)", "持倉天數", "賣出原因"]
            if is_portfolio:
                display_cols = ["ticker"] + display_cols

            def _cr(val):
                try:
                    v = float(val)
                    return "color:#26a69a" if v > 0 else ("color:#ef5350" if v < 0 else "")
                except Exception:
                    return ""

            if r["oos_trades"]:
                avail = [c for c in display_cols if c in r["oos_trades"][0]]
                df_t  = pd.DataFrame(r["oos_trades"])[avail]
                scols = [c for c in ["回報%", "盈虧(HKD)"] if c in df_t.columns]
                st.dataframe(df_t.style.map(_cr, subset=scols),
                             use_container_width=True, hide_index=True)
            else:
                st.info("本 Fold 無策略出場交易")

            forced_list = r.get("oos_forced_trades", [])
            if forced_list:
                with st.expander(f"📋 期末強制平倉明細（{len(forced_list)} 筆，未計入指標）"):
                    st.caption("以下交易因 Fold 邊界強制平倉，不代表策略出場訊號。")
                    avail_f = [c for c in display_cols if c in forced_list[0]]
                    df_f    = pd.DataFrame(forced_list)[avail_f]
                    scols_f = [c for c in ["回報%", "盈虧(HKD)"] if c in df_f.columns]
                    st.dataframe(df_f.style.map(_cr, subset=scols_f),
                                 use_container_width=True, hide_index=True)

            ext_list = r.get("oos_extended_trades", [])
            if ext_list:
                ext_sum  = _extended_summary(ext_list)
                closed_n = ext_sum.get("closed", 0)
                still_n  = ext_sum.get("still_held", 0)
                avg_r    = ext_sum.get("avg_return", 0)

                with st.expander(
                    f"🔍 延伸追蹤明細（{len(ext_list)} 筆；真實出場 {closed_n} 筆，"
                    f"均 {'+' if avg_r >= 0 else ''}{avg_r:.2f}%；仍持倉 {still_n} 筆）"
                ):
                    st.caption(
                        "以下是原本在 Fold 邊界被強制平倉的交易，用全期數據繼續持有到真實 sell 信號或 365 日上限。"
                        "純診斷用途，不計入上方 WF 指標。"
                    )

                    ext_rows = []
                    for t in ext_list:
                        row_e = {}
                        for col in display_cols:
                            if col in t:
                                row_e[col] = t[col]
                        row_e["狀態"] = "⏳ 延伸後仍持倉" if t.get("_still_held_at_end") else "✅ 真實出場"
                        ext_rows.append(row_e)
                    if ext_rows:
                        df_e    = pd.DataFrame(ext_rows)
                        scols_e = [c for c in ["回報%", "盈虧(HKD)"] if c in df_e.columns]
                        st.dataframe(df_e.style.map(_cr, subset=scols_e),
                                     use_container_width=True, hide_index=True)


def _show_summary_table(df_summary: pd.DataFrame, is_portfolio: bool):
    display_df = df_summary.drop(columns=["_deg_raw"], errors="ignore")

    def _color_ret(val):
        try:
            v = float(val)
            if v > 0: return "color:#26a69a;font-weight:bold"
            if v < 0: return "color:#ef5350;font-weight:bold"
        except Exception:
            pass
        return ""

    def _color_deg(val):
        s = str(val)
        if "N/A" in s: return "color:#888"
        try:
            v = float(s.replace("%", ""))
            if v < 40:  return "color:#26a69a"
            if v < 65:  return "color:#f9a825"
            return "color:#ef5350;font-weight:bold"
        except Exception:
            pass
        return ""

    def _color_valid(val):
        if "✅" in str(val): return "color:#26a69a;font-weight:bold"
        if "⚠️" in str(val): return "color:#f9a825"
        return ""

    st.dataframe(
        display_df.style
        .map(_color_ret,   subset=["IS 均回報%", "OOS 均回報%"])
        .map(_color_deg,   subset=["退化率%"])
        .map(_color_valid, subset=["有效"])
        .format({"IS 均回報%": "{:+.2f}%", "OOS 均回報%": "{:+.2f}%",
                 "IS 勝率%": "{:.1f}%",   "OOS 勝率%":  "{:.1f}%"}),
        use_container_width=True, hide_index=True,
    )

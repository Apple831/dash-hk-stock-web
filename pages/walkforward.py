import uuid
import threading
import time

import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import cache_store as _cs

def _job_get(job_id: str) -> dict | None:
    try:
        return _cs.dc.get("wf_job_" + job_id)
    except Exception:
        return None

def _job_set(job_id: str, data: dict) -> None:
    try:
        _cs.dc.set("wf_job_" + job_id, data, expire=3600)
    except Exception:
        pass

def _job_delete(job_id: str) -> None:
    try:
        _cs.dc.delete("wf_job_" + job_id)
    except Exception:
        pass

def _job_count() -> int:
    try:
        return len([k for k in _cs.dc if str(k).startswith("wf_job_")])
    except Exception:
        return 0

from data import get_cached, load_stocks
from indicators import calculate_indicators
from walk_forward import run_walk_forward, run_portfolio_walk_forward
from config import (
    STRATEGY_PRESETS,
    BUY_LABELS, SELL_LABELS,
    MIN_BARS_FOR_INDICATORS,
    WF_ROBUST_MAX_DEGRADATION, WF_ROBUST_MIN_OOS_POS_RATE,
    WF_WARNING_MAX_DEGRADATION, WF_WARNING_MIN_OOS_POS_RATE,
    WF_MIN_IS_RETURN_FOR_CALC,
)

dash.register_page(__name__, path="/walkforward", name="Walk-Forward")

CUSTOM_KEY = "🔧 自訂策略"

STRATEGY_OPTIONS = (
    [{"label": n, "value": n} for n in STRATEGY_PRESETS]
    + [{"label": CUSTOM_KEY, "value": CUSTOM_KEY}]
)
DEFAULT_STRATEGY  = list(STRATEGY_PRESETS.keys())[0]

PERIOD_OPTIONS = [
    {"label": "2年", "value": "2y"},
    {"label": "3年", "value": "3y"},
    {"label": "5年", "value": "5y"},
]

# ── Table 樣式 ────────────────────────────────────────────────────────
_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_CELL = {"textAlign": "left", "padding": "5px 12px",
         "fontFamily": "monospace", "fontSize": "0.83rem"}

FOLD_COLS = [
    {"name": "Fold",       "id": "Fold"},
    {"name": "IS 期間",    "id": "IS 期間"},
    {"name": "OOS 期間",   "id": "OOS 期間"},
    {"name": "IS 均回報%", "id": "IS 均回報%"},
    {"name": "OOS均回報%", "id": "OOS 均回報%"},
    {"name": "退化率%",    "id": "退化率%"},
    {"name": "IS 勝率%",   "id": "IS 勝率%"},
    {"name": "OOS勝率%",   "id": "OOS 勝率%"},
    {"name": "IS 交易數",  "id": "IS 交易數"},
    {"name": "OOS交易數",  "id": "OOS 交易數"},
    {"name": "有效",       "id": "有效"},
    {"name": "股票數",     "id": "股票數"},
    {"name": "過濾原因",   "id": "過濾原因"},
]



# ── 核心工具函式 ──────────────────────────────────────────────────────
def _degradation(is_ret: float, oos_ret: float):
    if abs(is_ret) < WF_MIN_IS_RETURN_FOR_CALC:
        return None
    return (is_ret - oos_ret) / abs(is_ret) * 100


def _build_rows(wf_results: list) -> list:
    rows = []
    for r in wf_results:
        if r.get("skipped_bear"):
            rows.append({
                "Fold":        r["fold"],
                "IS 期間":     f"{r['is_start'].strftime('%Y-%m')} → {r['is_end'].strftime('%Y-%m')}",
                "OOS 期間":    f"{r['oos_start'].strftime('%Y-%m')} → {r['oos_end'].strftime('%Y-%m')}",
                "IS 均回報%":  "—",
                "OOS 均回報%": "—",
                "退化率%":     "—",
                "IS 勝率%":    "—",
                "OOS 勝率%":   "—",
                "IS 交易數":   "—",
                "OOS 交易數":  "—",
                "有效":        "⏭️ 跳過",
                "股票數":      "—",
                "過濾原因":    r.get("filter_reason", "⛔ 熊市"),
                "_deg_raw":    None,
                "_valid_oos":  False,
            })
            continue
        im      = r["is_metrics"]  or {}
        om      = r["oos_metrics"] or {}
        is_ret  = im.get("平均每筆回報%", 0.0)
        oos_ret = om.get("平均每筆回報%", 0.0)
        deg     = _degradation(is_ret, oos_ret)
        rows.append({
            "Fold":        r["fold"],
            "IS 期間":     f"{r['is_start'].strftime('%Y-%m')} → {r['is_end'].strftime('%Y-%m')}",
            "OOS 期間":    f"{r['oos_start'].strftime('%Y-%m')} → {r['oos_end'].strftime('%Y-%m')}",
            "IS 均回報%":  round(is_ret, 2),
            "OOS 均回報%": round(oos_ret, 2),
            "退化率%":     f"{deg:.1f}%" if deg is not None else "—",
            "IS 勝率%":    round(im.get("勝率%", 0.0), 1),
            "OOS 勝率%":   round(om.get("勝率%", 0.0), 1),
            "IS 交易數":   im.get("交易次數", 0),
            "OOS 交易數":  r["oos_trade_count"],
            "有效":        "✅" if r["valid_oos"] else f"⚠️ {r['oos_trade_count']}筆",
            "股票數":      r.get("pit_stock_count", r.get("n_stocks", 0)),
            "過濾原因":    "",
            # 內部欄位（不直接顯示）
            "_deg_raw":    deg,
            "_valid_oos":  r["valid_oos"],
        })
    return rows


# ── 評估 & 元件建構 ───────────────────────────────────────────────────
def _verdict_section(rows: list, is_portfolio: bool, max_pos: int = 0, use_pit: bool = False) -> list:
    valid_rows = [r for r in rows if r["_valid_oos"] and r["_deg_raw"] is not None]
    if not valid_rows:
        return [dbc.Alert("❌ 所有 Fold 均未達標，無法評估策略。", color="danger")]

    avg_is  = sum(r["IS 均回報%"]  for r in valid_rows) / len(valid_rows)
    avg_oos = sum(r["OOS 均回報%"] for r in valid_rows) / len(valid_rows)
    degs    = [r["_deg_raw"] for r in valid_rows]
    avg_deg = sum(degs) / len(degs)
    oos_pos  = sum(1 for r in valid_rows if r["OOS 均回報%"] > 0)
    oos_rate = oos_pos / len(valid_rows) * 100

    if avg_oos > 0 and avg_deg < WF_ROBUST_MAX_DEGRADATION and oos_rate >= WF_ROBUST_MIN_OOS_POS_RATE:
        verdict, v_color = "🟢 策略穩健（具備真實 Alpha）", "success"
        detail = f"OOS 正回報比率 {oos_rate:.0f}%，退化率 {avg_deg:.1f}% < {WF_ROBUST_MAX_DEGRADATION:.0f}%，策略很可能在實盤有效"
    elif avg_oos > 0 and avg_deg < WF_WARNING_MAX_DEGRADATION and oos_rate >= WF_WARNING_MIN_OOS_POS_RATE:
        verdict, v_color = "🟡 輕度過擬合", "warning"
        detail = f"OOS 仍有正回報但退化率 {avg_deg:.1f}% 偏高，建議加入更嚴格條件或延長驗證期"
    elif avg_oos <= 0:
        verdict, v_color = "🔴 策略危險（OOS 虧損）", "danger"
        detail = f"OOS 平均回報 {avg_oos:.2f}%，策略在未見過的數據上虧損，不應實盤使用"
    else:
        verdict, v_color = "🔴 嚴重過擬合", "danger"
        detail = f"退化率 {avg_deg:.1f}% 過高，IS 回報無法在 OOS 重現"

    mode_lbl  = "（投資組合）" if is_portfolio else "（單股）"
    deg_color = "#26a69a" if avg_deg < WF_ROBUST_MAX_DEGRADATION else ("#f9a825" if avg_deg < WF_WARNING_MAX_DEGRADATION else "#ef5350")

    def _mc(label, value, color="white"):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, className="small text-muted mb-1"),
            html.Div(value, className="fw-bold",
                     style={"color": color, "fontSize": "1.0rem"}),
        ], className="py-2 px-3")), xs=6, md=2, className="mb-2")

    capital_note = html.Small(
        f"⚠️ 投資組合回測假設{'無限資金' if not max_pos else f'最多 {max_pos} 隻同時持倉'}",
        className="text-muted",
    ) if is_portfolio else None

    _pit_low_folds = sum(
        1 for r in rows
        if isinstance(r.get("股票數"), (int, float)) and r.get("股票數") < 20
    ) if (is_portfolio and use_pit) else 0

    return [
        *([
            dbc.Alert(
                "⚠️ PIT 股票池未啟用：當前 OOS 數字使用固定池（2026-05-14 的 183 隻），"
                "可能高估 7-10%。建議開啟「🧬 PIT 股票池」重跑以獲得可信數字。",
                color="warning",
                className="mb-2",
            )
        ] if is_portfolio and not use_pit else []),
        *([
            dbc.Alert(
                f"⚠️ 有 {_pit_low_folds} 個 Fold 的 PIT 股票池少於 20 隻，統計可靠度偏低。"
                "可能原因：EODHD 數據未覆蓋該時段，建議補充 data/eodhd_prices/ 資料。",
                color="warning",
                className="mb-2",
            )
        ] if _pit_low_folds > 0 else []),
        dbc.Alert([
            html.Strong(f"{verdict} {mode_lbl}",
                        style={"fontSize": "1.1rem"}),
            html.Br(),
            html.Small(detail),
        ], color=v_color, className="mb-2"),

        dbc.Row([
            _mc("IS 平均每筆%",    f"{avg_is:+.2f}%",
                "#26a69a" if avg_is  > 0 else "#ef5350"),
            _mc("OOS 平均每筆%",   f"{avg_oos:+.2f}%",
                "#26a69a" if avg_oos > 0 else "#ef5350"),
            _mc("平均退化率%",     f"{avg_deg:.1f}%", deg_color),
            _mc("OOS 正回報 Fold", f"{oos_pos}/{len(valid_rows)}"),
            _mc("有效 Fold",       f"{len(valid_rows)}/{len(rows)}"),
        ], className="g-2 mb-3"),
        *([capital_note] if capital_note else []),
        *([
            html.Div([
                dbc.Badge("🧬 PIT 股票池已啟用", color="info", className="me-2"),
                html.Small("每個 Fold 使用當時符合條件的股票池，已修正生存者偏差與前視偏差",
                           className="text-muted"),
            ], className="mb-3")
        ] if use_pit else []),
    ]


def _bar_chart(rows: list) -> go.Figure:
    def _safe_num(v):
        return v if isinstance(v, (int, float)) else None

    def _safe_fmt(v):
        return f"{v:+.1f}%" if isinstance(v, (int, float)) else str(v)

    labels = [
        f"Fold {r['Fold']}<br>{r['OOS 期間'].split(' → ')[0]}"
        + ("" if r["_valid_oos"] else " ⚠️")
        for r in rows
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="In-Sample", x=labels,
        y=[_safe_num(r["IS 均回報%"]) for r in rows],
        marker_color=["rgba(100,180,255,0.7)" if r["_valid_oos"]
                      else "rgba(100,180,255,0.25)" for r in rows],
        text=[_safe_fmt(r["IS 均回報%"]) for r in rows],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Out-of-Sample", x=labels,
        y=[_safe_num(r["OOS 均回報%"]) for r in rows],
        marker_color=[
            ("#26a69a" if r["OOS 均回報%"] >= 0 else "#ef5350") if r["_valid_oos"]
            else "rgba(128,128,128,0.3)"
            for r in rows
        ],
        text=[_safe_fmt(r["OOS 均回報%"]) for r in rows],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.25)")
    fig.update_layout(
        barmode="group", height=380, margin=dict(t=25, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _deg_chart(rows: list) -> go.Figure:
    deg_vals = [r["_deg_raw"] if r["_deg_raw"] is not None else 0 for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[f"Fold {r['Fold']}" for r in rows],
        y=deg_vals,
        mode="lines+markers+text",
        text=[r["退化率%"] for r in rows],
        textposition="top center",
        line=dict(color="#f9a825", width=2),
        marker=dict(
            size=10,
            color=[
                "rgba(150,150,150,0.4)" if (not r["_valid_oos"] or r["_deg_raw"] is None)
                else ("#26a69a" if d < 40 else ("#f9a825" if d < 65 else "#ef5350"))
                for r, d in zip(rows, deg_vals)
            ],
        ),
    ))
    fig.add_hline(y=WF_ROBUST_MAX_DEGRADATION, line_dash="dot",
                  line_color="rgba(38,166,154,0.5)",
                  annotation_text=f"{WF_ROBUST_MAX_DEGRADATION:.0f}% 健康線",
                  annotation_position="right")
    fig.add_hline(y=WF_WARNING_MAX_DEGRADATION, line_dash="dot",
                  line_color="rgba(239,83,80,0.5)",
                  annotation_text=f"{WF_WARNING_MAX_DEGRADATION:.0f}% 警戒線",
                  annotation_position="right")
    fig.update_layout(
        height=280, margin=dict(t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%", yaxis_title="退化率%",
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _oos_equity_chart(wf_results: list, trade_size: float) -> go.Figure:
    pieces, running = [], trade_size
    for r in wf_results:
        if not r["valid_oos"] or r["oos_equity"].empty:
            continue
        scale = running / trade_size
        piece = r["oos_equity"]["equity"] * scale
        pieces.append(piece)
        running = float(piece.iloc[-1])

    if not pieces:
        fig = go.Figure()
        fig.add_annotation(text="無有效 Fold，無法繪製 OOS 曲線",
                           x=0.5, y=0.5, xref="paper", yref="paper",
                           font=dict(size=14, color="#888"), showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", height=260)
        return fig

    combined = pd.concat(pieces)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    norm      = combined / trade_size * 100 - 100
    final_ret = float(norm.iloc[-1])
    line_c    = "#26a69a" if final_ret >= 0 else "#ef5350"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=norm.index, y=norm,
        fill="tozeroy",
        line=dict(color=line_c, width=2),
        fillcolor=f"rgba({'38,166,154' if final_ret >= 0 else '239,83,80'},0.08)",
        name="OOS 拼接曲線",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
    fig.add_annotation(
        text=f"OOS 總回報：{final_ret:+.1f}%",
        xref="paper", yref="paper", x=0.02, y=0.92, showarrow=False,
        font=dict(size=13, color=line_c),
    )
    fig.update_layout(
        height=300, margin=dict(t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%",
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _fold_table(rows: list) -> dash_table.DataTable:
    # 程式化條件樣式（per-row 退化率顏色）
    cond = [
        {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
        {"if": {"filter_query": "{IS 均回報%} > 0", "column_id": "IS 均回報%"},
         "color": "#26a69a"},
        {"if": {"filter_query": "{IS 均回報%} < 0", "column_id": "IS 均回報%"},
         "color": "#ef5350"},
        {"if": {"filter_query": "{OOS 均回報%} > 0", "column_id": "OOS 均回報%"},
         "color": "#26a69a", "fontWeight": "bold"},
        {"if": {"filter_query": "{OOS 均回報%} < 0", "column_id": "OOS 均回報%"},
         "color": "#ef5350", "fontWeight": "bold"},
    ]
    for i, r in enumerate(rows):
        d = r["_deg_raw"]
        if d is None:
            continue
        c = "#26a69a" if d < WF_ROBUST_MAX_DEGRADATION else ("#f9a825" if d < WF_WARNING_MAX_DEGRADATION else "#ef5350")
        cond.append({"if": {"row_index": i, "column_id": "退化率%"},
                     "color": c, "fontWeight": "bold"})

    table_data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    return dash_table.DataTable(
        columns=FOLD_COLS,
        data=table_data,
        sort_action="native",
        page_action="none",
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=cond,
        style_cell=_CELL,
        style_table={"overflowX": "auto"},
    )


# ── 數據載入 + WF 執行 ────────────────────────────────────────────────
def _run_wf(mode, strategy, ticker, total_period, is_mo, oos_mo, trade_size, slippage_ui,
            max_positions=0, progress_cb=None, commission_ui=None,
            custom_buy=None, custom_sell=None, use_pit=False, bear_filter=False):
    if strategy == CUSTOM_KEY:
        if not custom_buy:
            return None, False, "⚠️ 請至少勾選一個買入訊號"
        if not custom_sell:
            return None, False, "⚠️ 請至少勾選一個賣出訊號"
        buy_sigs        = tuple(f"b{i+1}" in (custom_buy  or []) for i in range(16))
        sell_sigs       = tuple(f"s{i+1}" in (custom_sell or []) for i in range(8))
        min_hold        = None
        cooldown        = None
        seasonal_filter = False
    else:
        preset = STRATEGY_PRESETS.get(strategy)
        if not preset:
            return None, False, "⚠️ 找不到策略"
        buy_sigs        = preset["buy"]
        sell_sigs       = preset["sell"]
        min_hold        = preset.get("min_hold_days")
        cooldown        = preset.get("cooldown_days")
        seasonal_filter = preset.get("seasonal_filter", False)
    ts        = float(trade_size or 100_000)
    slip            = float(slippage_ui or 0.10) / 100
    commission_pct  = float(commission_ui or 0.26) / 100
    is_mo           = int(is_mo  or 12)
    oos_mo          = int(oos_mo or 6)
    max_pos   = int(max_positions or 0)

    if mode == "single":
        ticker_clean = (ticker or "0700.HK").strip().upper()
        df = get_cached(ticker_clean, total_period)
        if df.empty:
            return None, False, f"❌ 無法獲取 {ticker_clean} 數據"
        min_bars = (is_mo + oos_mo) * 21 + MIN_BARS_FOR_INDICATORS
        if len(df) < min_bars:
            return None, False, (
                f"⚠️ {ticker_clean} 數據不足（{len(df)} 根K線，"
                f"需至少 {min_bars}）。請選擇更長週期。"
            )
        try:
            results = run_walk_forward(
                df, buy_sigs, sell_sigs,
                is_months=is_mo, oos_months=oos_mo,
                trade_size=ts, slippage=slip,
                commission_pct=commission_pct,
                min_hold_days=min_hold,
                cooldown_days=cooldown,
                progress_cb=progress_cb,
                seasonal_filter=seasonal_filter,
            )
        except Exception as e:
            return None, False, f"❌ WF 失敗：{str(e)[:80]}"
        return results, False, None

    else:  # portfolio
        stock_data = {}
        for t in load_stocks():
            df_t = get_cached(t, total_period)
            if not df_t.empty and len(df_t) >= MIN_BARS_FOR_INDICATORS:
                stock_data[t] = df_t
        if len(stock_data) < 5:
            return None, True, (
                f"⚠️ 投資組合模式需要至少 5 隻股票的緩存數據"
                f"（目前 {len(stock_data)} 隻，週期 {total_period}）。"
                f"請先用「⬇️ 下載數據」下載對應年期（{total_period}）數據。"
            )
        try:
            results = run_portfolio_walk_forward(
                stock_data, buy_sigs, sell_sigs,
                is_months=is_mo, oos_months=oos_mo,
                trade_size=ts, slippage=slip,
                commission_pct=commission_pct,
                min_hold_days=min_hold,
                cooldown_days=cooldown,
                max_concurrent_positions=max_pos if max_pos > 0 else None,
                progress_cb=progress_cb,
                seasonal_filter=seasonal_filter,
                use_pit_universe=use_pit,
                bear_filter=bear_filter,
            )
        except Exception as e:
            return None, True, f"❌ 投資組合 WF 失敗：{str(e)[:80]}"
        return results, True, None


def _run_wf_thread(job_id, mode, strategy, ticker, total_period, is_mo, oos_mo, trade_size, slippage, max_positions, commission=None, custom_buy=None, custom_sell=None, use_pit=False, bear_filter=False):
    import traceback
    short = job_id[:8]
    print(f"[WF] Thread start  job={short} mode={mode} ticker={ticker}")
    try:
        def progress_cb(fold, total_folds, current):
            existing = _job_get(job_id) or {}
            existing.update({
                "fold": fold,
                "total_folds": total_folds,
                "current": current or "",
            })
            _job_set(job_id, existing)
            print(f"[WF] Progress  job={short} fold={fold}/{total_folds} cur={current}")

        wf_results, is_portfolio, err = _run_wf(
            mode, strategy, ticker, total_period,
            is_mo, oos_mo, trade_size, slippage,
            max_positions=max_positions,
            commission_ui=commission,
            custom_buy=custom_buy,
            custom_sell=custom_sell,
            progress_cb=progress_cb,
            use_pit=use_pit,
            bear_filter=bear_filter,
        )
        n = len(wf_results) if wf_results else 0
        print(f"[WF] Thread done   job={short} results={n} err={err}")
        _job_set(job_id, {
            "status":       "done",
            "result":       wf_results,
            "is_portfolio": is_portfolio,
            "error":        err,
            "created_at":   (_job_get(job_id) or {}).get("created_at", time.time()),
            "params": {
                "strategy":      strategy,
                "ticker":        ticker or "0700.HK",
                "is_mo":         is_mo,
                "oos_mo":        oos_mo,
                "trade_size":    trade_size,
                "max_positions": max_positions,
                "use_pit":       use_pit,
                "bear_filter":   bear_filter,
            },
        })
    except Exception as e:
        print(f"[WF] Thread ERROR  job={short}: {e}\n{traceback.format_exc()}")
        _job_set(job_id, {
            "status": "done", "result": None,
            "is_portfolio": False,
            "error": f"❌ 執行失敗：{e}", "params": {},
            "created_at": (_job_get(job_id) or {}).get("created_at", time.time()),
        })


# ── Layout ───────────────────────────────────────────────────────────
def _param_col(label, input_id, **kwargs):
    return dbc.Col([
        html.Label(label, className="small text-muted mb-1 d-block"),
        dbc.Input(id=input_id, type="number", size="sm", **kwargs),
    ], xs=6, md=2, className="mb-2")


layout = html.Div([
    html.H4("🔬 Walk-Forward 驗證", className="mb-3"),

    # 策略
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id="wf-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
                style={"color": "#111"},
            ),
            md=8, className="mb-2",
        ),
    ], className="mb-1"),

    # 自訂策略面板（選擇 CUSTOM_KEY 才顯示）
    html.Div(
        id="wf-custom-panel",
        style={"display": "none"},
        children=[
            html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col([
                    html.Label(
                        "買入訊號（AND 邏輯：全部勾選條件須同時成立）",
                        className="small text-muted mb-1 d-block",
                    ),
                    dbc.Checklist(
                        id="wf-custom-buy",
                        options=[
                            {"label": f" {BUY_LABELS[i]}", "value": f"b{i+1}"}
                            for i in range(16)
                        ],
                        value=[],
                        className="small",
                        inputStyle={"cursor": "pointer"},
                        labelStyle={
                            "display": "block",
                            "marginBottom": "3px",
                            "cursor": "pointer",
                        },
                    ),
                ], md=6),
                dbc.Col([
                    html.Label(
                        "賣出訊號（OR 邏輯：任一觸發即賣出）",
                        className="small text-muted mb-1 d-block",
                    ),
                    dbc.Checklist(
                        id="wf-custom-sell",
                        options=[
                            {"label": f" {SELL_LABELS[i]}", "value": f"s{i+1}"}
                            for i in range(8)
                        ],
                        value=[],
                        className="small",
                        inputStyle={"cursor": "pointer"},
                        labelStyle={
                            "display": "block",
                            "marginBottom": "3px",
                            "cursor": "pointer",
                        },
                    ),
                ], md=6),
            ], className="mb-2"),
            html.Hr(className="my-2"),
        ],
    ),

    # 參數列
    dbc.Row([
        dbc.Col([
            html.Label("模式", className="small text-muted mb-1 d-block"),
            dbc.RadioItems(
                id="wf-mode",
                options=[
                    {"label": "單股", "value": "single"},
                    {"label": "投資組合", "value": "portfolio"},
                ],
                value="single",
                inline=True,
            ),
        ], xs=12, md=2, className="mb-2"),

        dbc.Col([
            html.Label("股票代碼（單股）", className="small text-muted mb-1 d-block"),
            dbc.Input(id="wf-ticker", value="0700.HK", type="text", size="sm"),
        ], id="wf-ticker-col", xs=6, md=2, className="mb-2"),

        dbc.Col([
            html.Label("總數據週期", className="small text-muted mb-1 d-block"),
            dbc.RadioItems(
                id="wf-total-period",
                options=PERIOD_OPTIONS,
                value="3y",
                inline=True,
            ),
            html.Small(
                "💡 建議先批量下載對應年期數據",
                id="wf-portfolio-hint",
                className="text-warning mt-1 d-block",
                style={"display": "none"},
            ),
        ], xs=12, md=2, className="mb-2"),

        _param_col("IS 窗口（月）", "wf-is-mo",  value=12, min=3,  step=3),
        _param_col("OOS 窗口（月）","wf-oos-mo", value=6,  min=1,  step=1),
    ], className="mb-1"),

    dbc.Row([
        _param_col("每筆金額 (HKD)", "wf-trade-size",  value=100000, step=10000),
        _param_col("純滑點%",        "wf-slippage",    value=0.10,   step=0.01, min=0),
        _param_col("手續費%（雙邊）",  "wf-commission",  value=0.26,   step=0.01, min=0),
        dbc.Col([
            html.Label("每日新進場上限 (0=不限)", className="small text-muted mb-1 d-block"),
            dbc.Input(id="wf-max-positions", type="number", size="sm",
                      value=0, min=0, step=1),
            html.Small(
                "⚠️ 此參數限制每日新進場數量，非同時持倉總數上限",
                className="text-warning",
                style={"fontSize": "0.75rem"},
            ),
        ], id="wf-max-pos-col", xs=6, md=2, className="mb-2",
           style={"display": "none"}),
        dbc.Col([
            html.Label(" ", className="small text-muted mb-1 d-block"),
            dbc.Switch(
                id="wf-use-pit",
                label="🧬 PIT 股票池（修正生存者偏差）",
                value=True,
            ),
        ], id="wf-pit-col", xs=12, md=3, className="mb-2",
           style={"display": "none"}),
        dbc.Col([
            html.Label(" ", className="small text-muted mb-1 d-block"),
            dbc.Switch(
                id="wf-bear-filter",
                label="🛡️ 熊市過濾（跳過熊市 Fold）",
                value=False,
            ),
        ], id="wf-bear-filter-col", xs=12, md=3, className="mb-2",
           style={"display": "none"}),
        dbc.Col(
            dbc.Button("🔬 開始驗證", id="wf-btn",
                       color="primary", size="sm", className="w-100 mt-4"),
            xs=6, md=2, className="mb-2",
        ),
    ], className="mb-3"),

    html.Small(id="wf-status", className="text-muted d-block mb-2"),

    dcc.Store(id="wf-job-store", data=None),
    dcc.Interval(id="wf-progress-interval", interval=800, n_intervals=0, disabled=True),
    html.Div(id="wf-progress-section", className="mb-3"),

    html.Div(id="wf-result"),
], className="p-3")


# ── Callback：策略切換 → 顯示/隱藏自訂面板 ───────────────────────────
@callback(
    Output("wf-custom-panel", "style"),
    Input("wf-strategy",      "value"),
)
def cb_toggle_custom_panel(strategy):
    return {"display": "block"} if strategy == CUSTOM_KEY else {"display": "none"}


# ── Callback：模式切換 → 股票輸入框 ──────────────────────────────────
@callback(
    Output("wf-ticker-col",       "style"),
    Output("wf-total-period",     "options"),
    Output("wf-portfolio-hint",   "style"),
    Output("wf-max-pos-col",      "style"),
    Output("wf-pit-col",          "style"),
    Output("wf-bear-filter-col",  "style"),
    Input("wf-mode",              "value"),
)
def cb_mode_change(mode):
    if mode == "portfolio":
        portfolio_opts = [
            {"label": "2年（緩存）", "value": "2y"},
            {"label": "3年（緩存）", "value": "3y"},
            {"label": "5年（緩存）", "value": "5y"},
        ]
        return {"display": "none"}, portfolio_opts, {}, {}, {}, {}
    return {}, PERIOD_OPTIONS, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}


# ── Callback：開始驗證（啟動 thread）────────────────────────────────
@callback(
    Output("wf-status",            "children"),
    Output("wf-result",            "children"),
    Output("wf-job-store",         "data"),
    Output("wf-progress-interval", "disabled"),
    Output("wf-progress-section",  "children"),
    Input("wf-btn",                "n_clicks"),
    State("wf-strategy",           "value"),
    State("wf-mode",               "value"),
    State("wf-ticker",             "value"),
    State("wf-total-period",       "value"),
    State("wf-is-mo",              "value"),
    State("wf-oos-mo",             "value"),
    State("wf-trade-size",         "value"),
    State("wf-slippage",           "value"),
    State("wf-commission",         "value"),
    State("wf-max-positions",      "value"),
    State("wf-custom-buy",         "value"),
    State("wf-custom-sell",        "value"),
    State("wf-use-pit",            "value"),
    State("wf-bear-filter",       "value"),
    prevent_initial_call=True,
)
def cb_run_wf(n_clicks, strategy, mode, ticker, total_period,
              is_mo, oos_mo, trade_size, slippage, commission, max_positions,
              custom_buy, custom_sell, use_pit, bear_filter):
    job_id = str(uuid.uuid4())
    _job_set(job_id, {
        "status": "running", "fold": 0, "total_folds": 0,
        "current": "初始化...", "created_at": time.time(),
    })
    print(f"[WF] cb_run_wf    job={job_id[:8]} mode={mode} ticker={ticker} strategy={strategy}")

    threading.Thread(
        target=_run_wf_thread,
        args=(job_id, mode, strategy, ticker, total_period, is_mo, oos_mo, trade_size, slippage,
              int(max_positions or 0), commission),
        kwargs={"custom_buy": custom_buy, "custom_sell": custom_sell,
                "use_pit": bool(use_pit or False), "bear_filter": bool(bear_filter or False)},
        daemon=True,
    ).start()

    init_bar = html.Div([
        html.Small("🔬 初始化資料中...", className="text-muted mb-1 d-block"),
        dbc.Progress(value=2, striped=True, animated=True,
                     color="info", style={"height": "22px"}),
    ])
    return "⏳ 驗證進行中...", [], job_id, False, init_bar


# ── Callback：輪詢進度 ────────────────────────────────────────────────
@callback(
    Output("wf-progress-section",  "children",  allow_duplicate=True),
    Output("wf-progress-interval", "disabled",  allow_duplicate=True),
    Output("wf-status",            "children",  allow_duplicate=True),
    Output("wf-result",            "children",  allow_duplicate=True),
    Input("wf-progress-interval",  "n_intervals"),
    State("wf-job-store",          "data"),
    prevent_initial_call=True,
)
def cb_poll_progress(n_intervals, job_id):
    short = (job_id[:8] + "...") if job_id else "None"
    in_jobs = _job_get(job_id) is not None if job_id else False
    print(f"[WF] cb_poll       n={n_intervals} job={short} in_jobs={in_jobs} total_jobs={_job_count()}")

    if not job_id:
        # no active job at all → stop interval
        return no_update, True, no_update, no_update

    if _job_get(job_id) is None:
        # job not registered yet (race condition) → keep polling, do NOT stop
        print(f"[WF] cb_poll       job={short} not found yet, keep polling")
        return no_update, False, no_update, no_update

    job = _job_get(job_id)

    if job["status"] == "running":
        fold    = job.get("fold", 0)
        total   = job.get("total_folds", 0)
        current = job.get("current", "初始化...")
        pct     = max(2, int(fold / total * 100)) if total > 0 else 2

        if total > 0 and fold > 0:
            label_text = f"正在跑 Fold {fold}/{total}" + (f"，處理 {current}..." if current else "...")
        else:
            label_text = f"初始化資料中... {current}" if current else "初始化資料中..."

        progress_ui = html.Div([
            html.Small(label_text, className="text-muted mb-1 d-block"),
            dbc.Progress(value=pct, label=f"{pct}%" if pct > 5 else "",
                         striped=True, animated=True,
                         color="info", style={"height": "22px"}),
        ])
        return progress_ui, False, "⏳ 驗證進行中...", no_update

    # ── 完成 ──────────────────────────────────────────────────────────
    print(f"[WF] cb_poll DONE  job={short}, rendering results")
    job_data = _job_get(job_id) or {}
    _job_delete(job_id)
    wf_results   = job_data.get("result")
    is_portfolio = job_data.get("is_portfolio", False)
    err          = job_data.get("error")
    params       = job_data.get("params", {})
    strategy     = params.get("strategy", "")
    ticker       = params.get("ticker", "0700.HK")
    is_mo        = params.get("is_mo", 12)
    oos_mo       = params.get("oos_mo", 6)
    trade_size   = params.get("trade_size", 100_000)
    max_pos      = params.get("max_positions", 0)
    use_pit      = params.get("use_pit", False)

    if err:
        return [], True, err, dbc.Alert(err, color="warning", className="mt-2")
    if not wf_results:
        msg = "⚠️ 沒有產生任何 Fold，請檢查數據週期或策略設定"
        return [], True, msg, dbc.Alert(msg, color="warning", className="mt-2")

    try:
        rows     = _build_rows(wf_results)
        ts       = float(trade_size or 100_000)
        is_mo_v  = int(is_mo  or 12)
        oos_mo_v = int(oos_mo or 6)
        n_folds  = len(rows)
        mode_lbl = "投資組合" if is_portfolio else (ticker or "0700.HK").strip().upper()

        if not rows:
            msg = "⚠️ 沒有產生任何 Fold，請檢查數據週期或策略設定"
            return [], True, msg, dbc.Alert(msg, color="warning", className="mt-2")

        verdict    = _verdict_section(rows, is_portfolio, max_pos=max_pos, use_pit=use_pit)
        bar_section = html.Div([
            html.H6("📊 IS vs OOS 平均每筆回報%", className="mb-1"),
            dcc.Graph(figure=_bar_chart(rows), config={"displayModeBar": False}),
        ], className="mb-3")
        deg_section = html.Div([
            html.H6("📉 退化率趨勢（灰=無效 Fold／IS≈0）", className="mb-1"),
            dcc.Graph(figure=_deg_chart(rows), config={"displayModeBar": False}),
        ], className="mb-3")
        oos_section = html.Div([
            html.H6("📈 OOS 拼接資金曲線（僅有效 Fold）", className="mb-1"),
            dcc.Graph(figure=_oos_equity_chart(wf_results, ts),
                      config={"displayModeBar": False}),
        ], className="mb-3")
        fold_section = html.Div([
            html.H6(f"📑 逐 Fold 詳細數據（共 {n_folds} 個 Fold）", className="mb-1"),
            _fold_table(rows),
        ], className="mb-3")

        status_str = (
            f"✅ {mode_lbl} | {strategy} | "
            f"IS {is_mo_v}月 × OOS {oos_mo_v}月 | {n_folds} 個 Fold"
        )
        done_bar = html.Div([
            html.Small(f"✅ 驗證完成：{n_folds} 個 Fold", className="text-success mb-1 d-block"),
            dbc.Progress(value=100, color="success", style={"height": "22px"}),
        ])
        return done_bar, True, status_str, [*verdict, bar_section, deg_section, oos_section, fold_section]

    except Exception as e:
        import traceback
        print(f"[WF] cb_poll RENDER ERROR: {e}\n{traceback.format_exc()}")
        return [], True, str(e), dbc.Alert(
            [html.Strong("❌ 結果渲染失敗"), html.Br(), html.Code(str(e))],
            color="danger", className="mt-2",
        )

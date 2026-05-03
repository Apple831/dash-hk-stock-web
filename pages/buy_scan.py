import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_stock_data, get_cached, load_stocks
from indicators import calculate_indicators, precompute_signals
from signals import signal_strength_score
from regime import detect_regime
from config import STRATEGY_PRESETS, BUY_LABELS, PRESET_CUSTOM

dash.register_page(__name__, path="/buy-scan", name="買入掃描")

STRATEGY_OPTIONS = (
    [{"label": PRESET_CUSTOM, "value": PRESET_CUSTOM}]
    + [{"label": name, "value": name} for name in STRATEGY_PRESETS]
)
DEFAULT_STRATEGY = list(STRATEGY_PRESETS.keys())[0]

TOP_N_OPTIONS = [
    {"label": "全部",   "value": 0},
    {"label": "Top 5",  "value": 5},
    {"label": "Top 10", "value": 10},
    {"label": "Top 20", "value": 20},
    {"label": "Top 30", "value": 30},
]

# ── DataTable 欄位 ─────────────────────────────────────────────────
TABLE_COLS = [
    {"name": "代碼",    "id": "代碼"},
    {"name": "現價",    "id": "現價"},
    {"name": "漲跌%",   "id": "漲跌%"},
    {"name": "RSI",     "id": "RSI"},
    {"name": "J值",     "id": "J值"},
    {"name": "BB位置%", "id": "BB位置%"},
    {"name": "評分",    "id": "評分"},
    {"name": "命中信號", "id": "命中信號"},
]

_HDR = {"backgroundColor": "#1a1a1a", "color": "#fff",
        "fontWeight": "bold", "border": "1px solid #444"}
_DAT = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_COND = [
    {"if": {"row_index": "odd"},  "backgroundColor": "#1f1f1f"},
    {"if": {"state": "selected"}, "backgroundColor": "rgba(38,166,154,0.25)",
     "border": "1px solid #26a69a"},
    {"if": {"state": "active"},   "backgroundColor": "rgba(38,166,154,0.12)"},
    {"if": {"filter_query": "{漲跌%} > 0", "column_id": "漲跌%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{漲跌%} < 0", "column_id": "漲跌%"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{評分} >= 50", "column_id": "評分"},
     "color": "#f9a825", "fontWeight": "bold"},
    {"if": {"filter_query": "{J值} < 20", "column_id": "J值"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{J值} > 80", "column_id": "J值"},
     "color": "#ef5350"},
    {"if": {"filter_query": "{BB位置%} < 10", "column_id": "BB位置%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{BB位置%} > 90", "column_id": "BB位置%"},
     "color": "#ef5350"},
]


# ── 恒指趨勢 banner ──────────────────────────────────────────────────
def _hsi_trend_banner() -> dbc.Alert:
    """Fetch HSI regime and build a contextual banner with b5/b6 guidance."""
    try:
        raw = get_stock_data("^HSI", "3mo")
        df  = calculate_indicators(raw) if not raw.empty else raw
        r   = detect_regime(df)
    except Exception:
        return dbc.Alert("⚠️ 無法獲取恒指數據", color="secondary", className="py-2 mb-2")

    bucket = r.get("bucket", "")
    label  = r.get("label", "—")
    price  = r.get("price")
    pct    = r.get("pct", 0.0) or 0.0

    price_str = f"  |  {price:.0f}  ({pct:+.2f}%)" if price else ""

    if "牛市" in bucket:
        color    = "success"
        b56_note = "⚠️ 牛市環境：b5/b6（RSI超賣／BB破下軌）為逆勢訊號，請謹慎使用"
    elif "熊市" in bucket:
        color    = "danger"
        b56_note = "✅ 熊市環境：b5/b6 均值回歸歷史表現優異（弱熊 +8%／強熊 +12.5%）"
    else:
        color    = "warning"
        b56_note = "ℹ️ 震盪市環境：b5/b6 均值回歸為主力工具"

    return dbc.Alert(
        [
            html.Span("🌍 恒指制度：", className="fw-bold me-1"),
            dbc.Badge(label, color=color, className="me-2 fs-6"),
            html.Small(price_str, className="text-muted me-3"),
            html.Small(b56_note, className="text-muted"),
        ],
        color=color,
        className="py-2 mb-2",
    )


# ── 掃描核心 ──────────────────────────────────────────────────────────
def _scan(strategy_name: str, custom_buy: list = None) -> tuple[list, str]:
    """AND 邏輯：所有選中買入信號必須同時觸發。"""
    if strategy_name == PRESET_CUSTOM:
        if not custom_buy:
            return [], "⚠️ 自定義模式請至少選擇一個買入信號"
        buy_active = sorted(custom_buy, key=lambda x: int(x[1:]))
        hit_label  = " | ".join(BUY_LABELS[int(b[1:]) - 1] for b in buy_active)
    else:
        preset = STRATEGY_PRESETS.get(strategy_name)
        if not preset:
            return [], "⚠️ 找不到策略"
        buy_sigs   = preset.get("buy", ())
        buy_active = [f"b{i+1}" for i, v in enumerate(buy_sigs) if v]
        hit_label  = " | ".join(BUY_LABELS[i] for i, v in enumerate(buy_sigs) if v)

    if not buy_active:
        return [], "⚠️ 策略未設定任何買入信號"

    tickers = load_stocks()
    results, errors = [], 0

    for ticker in tickers:
        try:
            df = get_cached(ticker, "1y")
            if df.empty or len(df) < 62:
                continue
            sigs = precompute_signals(df)

            if not all(bool(sigs[b].iloc[-1]) for b in buy_active):
                continue

            c       = df.iloc[-1]
            p       = df.iloc[-2]
            vol_ma  = float(df["Volume"].rolling(20).mean().iloc[-1])
            score   = signal_strength_score(df, len(buy_active), vol_ma)
            pct     = (float(c["Close"]) / float(p["Close"]) - 1) * 100
            j_val   = round(float(c["J"]), 1)

            bb_upper = float(c["BB_upper"])
            bb_lower = float(c["BB_lower"])
            bb_range = bb_upper - bb_lower
            bb_pos   = round((float(c["Close"]) - bb_lower) / bb_range * 100, 1) if bb_range > 0 else 50.0

            results.append({
                "代碼":    ticker,
                "現價":    round(float(c["Close"]), 2),
                "漲跌%":   round(pct, 2),
                "RSI":     round(float(c["RSI"]), 1),
                "J值":     j_val,
                "BB位置%": bb_pos,
                "評分":    score,
                "命中信號": hit_label,
            })
        except Exception:
            errors += 1

    results.sort(key=lambda x: x["評分"], reverse=True)

    n, total = len(results), len(tickers)
    err_note = f"，{errors} 隻略過（下載失敗）" if errors else ""
    if n:
        status = f"✅ 完成：{total} 隻中命中 {n} 隻{err_note}"
    else:
        status = f"🔍 完成：{total} 隻中沒有命中「{strategy_name}」{err_note}"
    return results, status


# ── 掃描結果摘要 ──────────────────────────────────────────────────────
def _scan_metrics(results: list) -> html.Div:
    if not results:
        return html.Div()
    df       = pd.DataFrame(results)
    n        = len(df)
    avg_sc   = df["評分"].mean()
    avg_rsi  = df["RSI"].mean()
    avg_j    = df["J值"].mean()
    pos_pct  = (df["漲跌%"] > 0).mean() * 100
    low_bb   = (df["BB位置%"] < 20).sum()

    def _card(icon, label, val):
        return dbc.Col(
            dbc.Card(dbc.CardBody([
                html.Div(f"{icon} {label}", className="small text-muted mb-1"),
                html.Div(val, className="fw-bold", style={"fontSize": "1rem"}),
            ], className="py-2 px-3"), className="h-100"),
            xs=6, md=2,
        )

    return dbc.Row([
        _card("🎯", "命中",     str(n)),
        _card("⭐", "平均評分", f"{avg_sc:.1f}"),
        _card("📊", "平均RSI",  f"{avg_rsi:.1f}"),
        _card("📈", "正漲跌",   f"{pos_pct:.0f}%"),
        _card("📉", "平均J值",  f"{avg_j:.1f}"),
        _card("🔻", "BB下軌區", f"{low_bb} 隻"),
    ], className="g-2 mb-3")


# ── K 線圖（MACD + RSI）─────────────────────────────────────────────
def _chart(ticker: str) -> go.Figure:
    raw = get_stock_data(ticker, "1y")
    if raw.empty:
        fig = go.Figure()
        fig.add_annotation(text=f"{ticker} 無資料", x=0.5, y=0.5,
                           xref="paper", yref="paper",
                           font=dict(size=18, color="#888"), showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", height=480)
        return fig

    df = calculate_indicators(raw)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.58, 0.22, 0.20],
        vertical_spacing=0.02,
        subplot_titles=(f"{ticker} K線", "MACD", "RSI"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        showlegend=False,
    ), row=1, col=1)
    for col_, color_, lbl in [("MA20", "#f9a825", "MA20"), ("MA60", "#7c4dff", "MA60")]:
        fig.add_trace(go.Scatter(x=df.index, y=df[col_],
                                 line=dict(color=color_, width=1.3), name=lbl), row=1, col=1)

    bar_c = ["#26a69a" if v >= 0 else "#ef5350" for v in df["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"],
                         marker_color=bar_c, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["DIF"],
                             line=dict(color="#42a5f5", width=1), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["DEA"],
                             line=dict(color="#ff7043", width=1), showlegend=False), row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"],
                             line=dict(color="#ce93d8", width=1.5), showlegend=False), row=3, col=1)
    for lvl, clr in [(70, "rgba(239,83,80,0.4)"), (50, "rgba(255,255,255,0.15)"),
                     (30, "rgba(38,166,154,0.4)")]:
        fig.add_hline(y=lvl, line_dash="dash", line_color=clr, row=3, col=1)

    fig.update_layout(
        height=520,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,20,0.6)",
        margin=dict(t=30, b=15, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    return fig


# ── Layout ───────────────────────────────────────────────────────────
layout = html.Div([
    html.H4("🟢 買入掃描", className="mb-3"),

    # 控制列（策略下拉 + Top N + 按鈕）
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id="bscan-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
                style={"color": "#111"},
            ),
            md=6, sm=12, className="mb-2 mb-md-0",
        ),
        dbc.Col(
            dcc.Dropdown(
                id="bscan-topn",
                options=TOP_N_OPTIONS,
                value=0,
                clearable=False,
                style={"color": "#111"},
                placeholder="Top N",
            ),
            md=2, sm=4, className="mb-2 mb-md-0",
        ),
        dbc.Col(
            dbc.Button("🔍 開始掃描", id="bscan-btn",
                       color="success", className="w-100"),
            md=2, sm=8,
        ),
    ], align="center", className="mb-3"),

    # 自定義買入訊號面板
    html.Div(
        id="bscan-custom-panel",
        style={"display": "none"},
        children=[
            dbc.Card(dbc.CardBody([
                html.Small(
                    "📋 選擇買入信號（AND 邏輯：所有選中信號必須同時觸發）",
                    className="text-muted fw-bold d-block mb-2",
                ),
                dbc.Checklist(
                    id="bscan-custom-buy",
                    options=[
                        {"label": f" {BUY_LABELS[i]}", "value": f"b{i+1}"}
                        for i in range(11)
                    ],
                    value=[],
                    inline=True,
                    className="small",
                    inputStyle={"cursor": "pointer"},
                    labelStyle={"marginRight": "14px", "cursor": "pointer"},
                ),
            ], className="py-2 px-3"), className="border-success mb-2"),
        ],
    ),

    # 恒指趨勢提示（掃描後顯示）
    html.Div(id="bscan-hsi-banner"),

    # 狀態列
    html.Small(id="bscan-status", className="text-muted"),

    # Store（供 chart callback 讀取）
    dcc.Store(id="bscan-store"),

    # 掃描結果摘要
    html.Div(id="bscan-metrics", className="mt-2"),

    # 結果 DataTable
    dcc.Loading(type="circle", color="#26a69a", className="mt-2", children=[
        html.Div(
            dash_table.DataTable(
                id="bscan-table",
                columns=TABLE_COLS,
                data=[],
                sort_action="native",
                page_action="none",
                row_selectable="single",
                style_header=_HDR,
                style_data=_DAT,
                style_data_conditional=_COND,
                style_cell={
                    "textAlign": "left",
                    "padding": "6px 14px",
                    "fontFamily": "monospace",
                    "fontSize": "0.88rem",
                },
                style_table={"overflowX": "auto"},
                fixed_rows={"headers": True},
            ),
            className="mt-2",
        ),
    ]),

    # 個股圖表（點選後出現）
    html.Div(id="bscan-chart", className="mt-4"),
], className="p-3")


# ── CB 0：自定義面板顯示/隱藏 ───────────────────────────────────────
@callback(
    Output("bscan-custom-panel", "style"),
    Input("bscan-strategy",      "value"),
)
def cb_toggle_custom(strategy):
    return {} if strategy == PRESET_CUSTOM else {"display": "none"}


# ── CB 1：掃描 → Store + 狀態 + Table + 摘要 + 恒指 banner ──────────
@callback(
    Output("bscan-store",      "data"),
    Output("bscan-status",     "children"),
    Output("bscan-table",      "data"),
    Output("bscan-metrics",    "children"),
    Output("bscan-hsi-banner", "children"),
    Input("bscan-btn",         "n_clicks"),
    State("bscan-strategy",    "value"),
    State("bscan-custom-buy",  "value"),
    State("bscan-topn",        "value"),
    prevent_initial_call=True,
)
def cb_run_scan(n_clicks, strategy, custom_buy, top_n):
    rows, status = _scan(strategy, custom_buy)
    top_n = top_n or 0
    display_rows = rows[:top_n] if top_n > 0 else rows
    return (
        rows,
        status,
        display_rows,
        _scan_metrics(display_rows),
        _hsi_trend_banner(),
    )


# ── CB 2：點選行 → 個股圖 ────────────────────────────────────────────
@callback(
    Output("bscan-chart",                  "children"),
    Input("bscan-table",                   "derived_virtual_selected_rows"),
    State("bscan-table",                   "derived_virtual_data"),
    prevent_initial_call=True,
)
def cb_show_chart(sel_rows, vdata):
    if not sel_rows or not vdata:
        return no_update
    ticker = vdata[sel_rows[0]]["代碼"]
    return dcc.Graph(figure=_chart(ticker), config={"displayModeBar": False})

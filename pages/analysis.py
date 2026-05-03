import dash
from dash import html, dcc, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_cached
from indicators import calculate_indicators
from signals import evaluate_signals

dash.register_page(__name__, path="/analysis", name="個股分析")

PERIOD_OPTIONS = [
    {"label": "3個月", "value": "3mo"},
    {"label": "6個月", "value": "6mo"},
    {"label": "1年",   "value": "1y"},
    {"label": "2年",   "value": "2y"},
]


# ── UI 元件助手 ────────────────────────────────────────────────────
def _metric_card(label: str, value: str, color: str = "white"):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(label, className="small text-muted mb-1"),
                html.Div(value, className="fw-bold",
                         style={"color": color, "fontSize": "1.05rem", "wordBreak": "break-all"}),
            ], className="py-2 px-3"),
            className="h-100",
        ),
        xs=6, md=2,
    )


def _signal_item(name: str, detail: str, triggered: bool, kind: str):
    if triggered:
        icon  = "✅" if kind == "buy" else "⚠️"
        color = "#26a69a" if kind == "buy" else "#ef5350"
        weight = "bold"
    else:
        icon, color, weight = "○", "#555", "normal"
    return html.Div([
        html.Span(f"{icon} {name}",
                  style={"color": color, "fontWeight": weight, "fontSize": "0.88rem"}),
        html.Div(detail,
                 style={"color": "#777", "fontSize": "0.78rem",
                        "paddingLeft": "1.4em", "lineHeight": "1.3"}),
    ], className="mb-2")


def _verdict_card(buy_n: int, sell_n: int) -> dbc.Alert:
    if buy_n >= 3 and buy_n > sell_n:
        text, color = "偏多",   "success"
    elif buy_n >= 1 and buy_n > sell_n:
        text, color = "略偏多", "success"
    elif sell_n >= 3 and sell_n > buy_n:
        text, color = "偏空",   "danger"
    elif sell_n >= 1 and sell_n > buy_n:
        text, color = "略偏空", "warning"
    else:
        text, color = "中性",   "secondary"

    return dbc.Alert(
        [
            html.Span("綜合判定：", className="fw-bold me-2"),
            dbc.Badge(text, color=color, className="fs-6 px-3 py-1"),
            html.Small(
                f"  買入 {buy_n}/11 觸發 ｜ 賣出 {sell_n}/8 觸發",
                className="ms-3 text-muted",
            ),
        ],
        color=color,
        className="py-2 mb-3",
    )


def _signal_col(signals: list, kind: str, label: str, total: int) -> dbc.Col:
    """Split signals into triggered (shown) and untriggered (collapsed)."""
    triggered = [(n, d, t) for n, d, t in signals if t]
    pending   = [(n, d, t) for n, d, t in signals if not t]
    n_hit     = len(triggered)

    children = [
        html.H6(f"{label}（{n_hit}/{total} 觸發）", className="mb-2"),
        *[_signal_item(n, d, t, kind) for n, d, t in triggered],
    ]

    if pending:
        collapse_id = f"analysis-{kind}-collapse"
        toggle_id   = f"analysis-{kind}-toggle"
        children += [
            dbc.Button(
                f"○ 未觸發 {len(pending)} 個  ▾",
                id=toggle_id,
                color="link",
                size="sm",
                className="p-0 mb-1 d-block",
                style={"color": "#666", "fontSize": "0.82rem"},
            ),
            dbc.Collapse(
                [_signal_item(n, d, t, kind) for n, d, t in pending],
                id=collapse_id,
                is_open=False,
            ),
        ]

    return dbc.Col(children, md=6, className="mb-3")


# ── 分析核心 ───────────────────────────────────────────────────────
def _build_result(ticker: str, period: str):
    """Returns (status_text, result_children_list)"""
    df = get_cached(ticker, period)
    if df.empty:
        return f"❌ 無法獲取 {ticker} 的數據，請確認代碼格式（如 0700.HK）", []
    if len(df) < 62:
        return (
            f"⚠️ {ticker} 在 {period} 週期內數據不足（{len(df)} 根K線，需至少 62 根），"
            "請選擇更長週期",
            [],
        )

    c   = df.iloc[-1]
    p   = df.iloc[-2]
    pct = (float(c["Close"]) / float(p["Close"]) - 1) * 100

    close_val  = float(c["Close"])
    ma20_val   = float(c["MA20"])
    ma60_raw   = c.get("MA60")
    ma60_val   = float(ma60_raw) if pd.notna(ma60_raw) else None

    ma20_dist  = (close_val - ma20_val) / ma20_val * 100 if ma20_val else 0.0
    ma60_dist  = (close_val - ma60_val) / ma60_val * 100 if ma60_val else None

    pct_color  = "#26a69a" if pct >= 0 else "#ef5350"
    rsi_val    = float(c["RSI"])
    rsi_color  = "#ef5350" if rsi_val > 70 else ("#26a69a" if rsi_val < 30 else "white")
    j_val      = float(c["J"])
    j_color    = "#ef5350" if j_val > 80 else ("#26a69a" if j_val < 20 else "white")
    macd_val   = float(c["MACD_Hist"]) if pd.notna(c.get("MACD_Hist")) else 0.0
    macd_color = "#26a69a" if macd_val >= 0 else "#ef5350"

    pct_str     = f"{'+' if pct >= 0 else ''}{pct:.2f}%"
    ma20_str    = f"{'+' if ma20_dist >= 0 else ''}{ma20_dist:.2f}%"
    ma20_color  = "#26a69a" if ma20_dist >= 0 else "#ef5350"
    ma60_str    = (f"{'+' if (ma60_dist or 0) >= 0 else ''}{ma60_dist:.2f}%"
                   if ma60_dist is not None else "—")
    ma60_color  = "#26a69a" if (ma60_dist or 0) >= 0 else "#ef5350"

    # ── 綜合判定 ─────────────────────────────────────────────────────
    sigs  = evaluate_signals(df)
    buy_n = sum(1 for _, _, t in sigs["buy"]  if t)
    sel_n = sum(1 for _, _, t in sigs["sell"] if t)

    verdict = _verdict_card(buy_n, sel_n)

    # ── 指標卡片（6張）──────────────────────────────────────────────
    cards = dbc.Row([
        _metric_card("現價",    f"{close_val:.2f}  {pct_str}", pct_color),
        _metric_card("距MA20",  ma20_str, ma20_color),
        _metric_card("距MA60",  ma60_str, ma60_color),
        _metric_card("RSI",     f"{rsi_val:.1f}", rsi_color),
        _metric_card("J值",     f"{j_val:.1f}",   j_color),
        _metric_card("MACD柱",  f"{macd_val:.4f}", macd_color),
    ], className="mb-4 g-2")

    # ── 訊號列表（觸發/未觸發分開）───────────────────────────────────
    signals_row = dbc.Row([
        _signal_col(sigs["buy"],  "buy",  "🟢 買入訊號", 11),
        _signal_col(sigs["sell"], "sell", "🔴 賣出訊號",  8),
    ], className="mb-2")

    # ── K 線圖 ───────────────────────────────────────────────────────
    chart = dcc.Graph(figure=_chart(df, ticker, period),
                      config={"displayModeBar": False})

    return (
        f"✅ {ticker}｜{period}｜買入 {buy_n} 個｜賣出 {sel_n} 個",
        [verdict, cards, signals_row, chart],
    )


def _chart(df: pd.DataFrame, ticker: str, period: str) -> go.Figure:
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.58, 0.22, 0.20],
        vertical_spacing=0.02,
        subplot_titles=(f"{ticker} K線（{period}）", "MACD", "RSI"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        showlegend=False,
    ), row=1, col=1)
    for col_, color_, lbl in [("MA20", "#f9a825", "MA20"), ("MA60", "#7c4dff", "MA60")]:
        if col_ in df.columns:
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
        height=540,
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
    html.H4("🔍 個股分析", className="mb-3"),

    dbc.Row([
        dbc.Col(
            dbc.Input(
                id="analysis-ticker",
                value="0700.HK",
                placeholder="股票代碼，如 0700.HK",
                type="text",
                size="sm",
            ),
            md=3, sm=6, className="mb-2",
        ),
        dbc.Col(
            dbc.RadioItems(
                id="analysis-period",
                options=PERIOD_OPTIONS,
                value="1y",
                inline=True,
                className="pt-1",
            ),
            md=5, sm=12, className="mb-2",
        ),
        dbc.Col(
            dbc.Button("🔍 開始分析", id="analysis-btn",
                       color="primary", size="sm", className="w-100"),
            md=2, sm=6, className="mb-2",
        ),
    ], align="center", className="mb-3"),

    html.Small(id="analysis-status", className="text-muted d-block mb-3"),

    dcc.Loading(type="circle", color="#42a5f5", children=[
        html.Div(id="analysis-result"),
    ]),
], className="p-3")


# ── Callback：主分析 ──────────────────────────────────────────────────
@callback(
    Output("analysis-status", "children"),
    Output("analysis-result", "children"),
    Input("analysis-btn",     "n_clicks"),
    State("analysis-ticker",  "value"),
    State("analysis-period",  "value"),
    prevent_initial_call=True,
)
def cb_run_analysis(n_clicks, ticker, period):
    if not ticker or not ticker.strip():
        return "⚠️ 請輸入股票代碼", no_update
    status, children = _build_result(ticker.strip().upper(), period)
    return status, children


# ── Callback：未觸發訊號折疊切換 ──────────────────────────────────────
@callback(
    Output("analysis-buy-collapse",  "is_open"),
    Input("analysis-buy-toggle",     "n_clicks"),
    State("analysis-buy-collapse",   "is_open"),
    prevent_initial_call=True,
)
def toggle_buy_collapse(n, is_open):
    return not is_open


@callback(
    Output("analysis-sell-collapse", "is_open"),
    Input("analysis-sell-toggle",    "n_clicks"),
    State("analysis-sell-collapse",  "is_open"),
    prevent_initial_call=True,
)
def toggle_sell_collapse(n, is_open):
    return not is_open

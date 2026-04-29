import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data import get_stock_data, load_stocks
from indicators import calculate_indicators, precompute_signals
from config import STRATEGY_PRESETS, SELL_LABELS

dash.register_page(__name__, path="/sell-scan", name="賣出掃描")

STRATEGY_OPTIONS = [
    {"label": name, "value": name}
    for name in STRATEGY_PRESETS
]
DEFAULT_STRATEGY = list(STRATEGY_PRESETS.keys())[0]

# ── DataTable 樣式 ────────────────────────────────────────────────────
TABLE_COLS = [
    {"name": "代碼",    "id": "代碼"},
    {"name": "現價",    "id": "現價"},
    {"name": "漲跌%",   "id": "漲跌%"},
    {"name": "RSI",     "id": "RSI"},
    {"name": "J值",     "id": "J值"},
    {"name": "訊號數",  "id": "訊號數"},
    {"name": "命中訊號", "id": "命中訊號"},
]

_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_COND = [
    {"if": {"row_index": "odd"},  "backgroundColor": "#1f1f1f"},
    {"if": {"state": "selected"}, "backgroundColor": "rgba(239,83,80,0.2)",
     "border": "1px solid #ef5350"},
    {"if": {"state": "active"},   "backgroundColor": "rgba(239,83,80,0.1)"},
    {"if": {"filter_query": "{漲跌%} > 0", "column_id": "漲跌%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{漲跌%} < 0", "column_id": "漲跌%"},
     "color": "#ef5350", "fontWeight": "bold"},
    # 訊號數越多越紅
    {"if": {"filter_query": "{訊號數} >= 2", "column_id": "訊號數"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{訊號數} = 1",  "column_id": "訊號數"},
     "color": "#f9a825"},
]


# ── 掃描核心（賣出 OR 邏輯）──────────────────────────────────────────
def _scan(strategy_name: str) -> tuple[list, str]:
    """
    賣出掃描：策略定義的賣出訊號只需任一命中（OR 邏輯），
    與回測引擎一致（sell_signal = s1 | s2 | ...）。
    結果按命中訊號數降序，訊號數相同時按 RSI 降序（越高越超買）。
    """
    preset = STRATEGY_PRESETS.get(strategy_name)
    if not preset:
        return [], "⚠️ 找不到策略"

    sell_sigs   = preset.get("sell", ())
    sell_active = [f"s{i+1}" for i, v in enumerate(sell_sigs) if v]
    if not sell_active:
        return [], "⚠️ 策略未設定任何賣出訊號"

    tickers = load_stocks()
    results, errors = [], 0

    for ticker in tickers:
        try:
            raw = get_stock_data(ticker, "1y")
            if raw.empty or len(raw) < 62:
                continue
            df   = calculate_indicators(raw)
            sigs = precompute_signals(df)

            # OR 邏輯：至少一個賣出訊號為 True
            n_hit = sum(bool(sigs[s].iloc[-1]) for s in sell_active)
            if n_hit == 0:
                continue

            c   = df.iloc[-1]
            p   = df.iloc[-2]
            pct = (float(c["Close"]) / float(p["Close"]) - 1) * 100

            hit_labels = [
                SELL_LABELS[i]
                for i, v in enumerate(sell_sigs)
                if v and bool(sigs[f"s{i+1}"].iloc[-1])
            ]

            results.append({
                "代碼":   ticker,
                "現價":   round(float(c["Close"]), 2),
                "漲跌%":  round(pct, 2),
                "RSI":    round(float(c["RSI"]), 1),
                "J值":    round(float(c["J"]), 1),
                "訊號數": n_hit,
                "命中訊號": " | ".join(hit_labels),
            })
        except Exception:
            errors += 1

    results.sort(key=lambda x: (-x["訊號數"], -x["RSI"]))

    n, total = len(results), len(tickers)
    err_note = f"，{errors} 隻略過（下載失敗）" if errors else ""
    if n:
        status = f"⚠️ 完成：{total} 隻中觸發賣出訊號 {n} 隻{err_note}"
    else:
        status = f"✅ 完成：{total} 隻中沒有觸發「{strategy_name}」賣出訊號{err_note}"
    return results, status


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

    df  = calculate_indicators(raw)
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
    html.H4("🔴 賣出掃描", className="mb-3"),

    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id="sscan-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
                style={"color": "#111"},
            ),
            md=8, sm=12, className="mb-2 mb-md-0",
        ),
        dbc.Col(
            dbc.Button("🔍 開始掃描", id="sscan-btn",
                       color="danger", className="w-100"),
            md=2, sm=12,
        ),
    ], align="center", className="mb-3"),

    html.Small(id="sscan-status", className="text-muted"),

    dcc.Store(id="sscan-store"),

    dcc.Loading(type="circle", color="#ef5350", className="mt-2", children=[
        html.Div(
            dash_table.DataTable(
                id="sscan-table",
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

    html.Div(id="sscan-chart", className="mt-4"),
], className="p-3")


# ── CB 1：掃描 ──────────────────────────────────────────────────────
@callback(
    Output("sscan-store",   "data"),
    Output("sscan-status",  "children"),
    Output("sscan-table",   "data"),
    Input("sscan-btn",      "n_clicks"),
    State("sscan-strategy", "value"),
    prevent_initial_call=True,
)
def cb_run_scan(n_clicks, strategy):
    rows, status = _scan(strategy)
    return rows, status, rows


# ── CB 2：點選行 → 圖 ───────────────────────────────────────────────
@callback(
    Output("sscan-chart",                   "children"),
    Input("sscan-table",                    "derived_virtual_selected_rows"),
    State("sscan-table",                    "derived_virtual_data"),
    prevent_initial_call=True,
)
def cb_show_chart(sel_rows, vdata):
    if not sel_rows or not vdata:
        return no_update
    ticker = vdata[sel_rows[0]]["代碼"]
    return dcc.Graph(figure=_chart(ticker), config={"displayModeBar": False})

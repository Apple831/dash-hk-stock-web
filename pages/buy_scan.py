import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_stock_data, load_stocks
from indicators import calculate_indicators, precompute_signals
from signals import signal_strength_score
from config import STRATEGY_PRESETS, BUY_LABELS

dash.register_page(__name__, path="/buy-scan", name="買入掃描")

# ── 策略下拉選單（只顯示 ACTIVE，不顯示 LEGACY 對照組）──────────────
STRATEGY_OPTIONS = [
    {"label": name, "value": name}
    for name in STRATEGY_PRESETS
]
DEFAULT_STRATEGY = list(STRATEGY_PRESETS.keys())[0]

# ── DataTable 欄位 ─────────────────────────────────────────────────
TABLE_COLS = [
    {"name": "代碼",    "id": "代碼"},
    {"name": "現價",    "id": "現價"},
    {"name": "漲跌%",   "id": "漲跌%"},
    {"name": "RSI",     "id": "RSI"},
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
]


# ── 掃描核心 ──────────────────────────────────────────────────────────
def _scan(strategy_name: str) -> tuple[list, str]:
    """
    Returns (results, status_text)
    只有 AND 邏輯命中所有指定買入信號的股票才進入結果。
    """
    preset = STRATEGY_PRESETS.get(strategy_name)
    if not preset:
        return [], "⚠️ 找不到策略"

    buy_sigs = preset.get("buy", ())
    buy_active = [f"b{i+1}" for i, v in enumerate(buy_sigs) if v]
    if not buy_active:
        return [], "⚠️ 策略未設定任何買入信號"

    tickers = load_stocks()
    results, errors = [], 0

    for ticker in tickers:
        try:
            raw = get_stock_data(ticker, "1y")
            if raw.empty or len(raw) < 62:
                continue
            df = calculate_indicators(raw)
            sigs = precompute_signals(df)

            # AND 邏輯：選取的每個買入信號都要 True
            if not all(bool(sigs[b].iloc[-1]) for b in buy_active):
                continue

            c = df.iloc[-1]
            p = df.iloc[-2]
            vol_ma = float(df["Volume"].rolling(20).mean().iloc[-1])
            score  = signal_strength_score(df, len(buy_active), vol_ma)
            pct    = (float(c["Close"]) / float(p["Close"]) - 1) * 100

            results.append({
                "代碼":   ticker,
                "現價":   round(float(c["Close"]), 2),
                "漲跌%":  round(pct, 2),
                "RSI":    round(float(c["RSI"]), 1),
                "評分":   score,
                "命中信號": " | ".join(BUY_LABELS[i] for i, v in enumerate(buy_sigs) if v),
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

    # K 線 + MA
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        showlegend=False,
    ), row=1, col=1)
    for col_, color_, lbl in [("MA20", "#f9a825", "MA20"), ("MA60", "#7c4dff", "MA60")]:
        fig.add_trace(go.Scatter(x=df.index, y=df[col_],
                                 line=dict(color=color_, width=1.3), name=lbl), row=1, col=1)

    # MACD
    bar_c = ["#26a69a" if v >= 0 else "#ef5350" for v in df["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"],
                         marker_color=bar_c, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["DIF"],
                             line=dict(color="#42a5f5", width=1), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["DEA"],
                             line=dict(color="#ff7043", width=1), showlegend=False), row=2, col=1)

    # RSI
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

    # 控制列
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id="bscan-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
                style={"color": "#111"},
            ),
            md=8, sm=12, className="mb-2 mb-md-0",
        ),
        dbc.Col(
            dbc.Button("🔍 開始掃描", id="bscan-btn",
                       color="success", className="w-100"),
            md=2, sm=12,
        ),
    ], align="center", className="mb-3"),

    # 狀態列
    html.Small(id="bscan-status", className="text-muted"),

    # Store（供 chart callback 讀取 ticker）
    dcc.Store(id="bscan-store"),

    # 結果 DataTable
    dcc.Loading(type="circle", color="#26a69a", className="mt-2", children=[
        html.Div(
            dash_table.DataTable(
                id="bscan-table",
                columns=TABLE_COLS,
                data=[],
                sort_action="native",
                page_action="none",          # 不分頁，全部顯示
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


# ── CB 1：按鈕 → 掃描 → Store + 狀態 + Table data ──────────────────
@callback(
    Output("bscan-store",   "data"),
    Output("bscan-status",  "children"),
    Output("bscan-table",   "data"),
    Input("bscan-btn",      "n_clicks"),
    State("bscan-strategy", "value"),
    prevent_initial_call=True,
)
def cb_run_scan(n_clicks, strategy):
    rows, status = _scan(strategy)
    return rows, status, rows


# ── CB 2：點選行 → 個股圖 ────────────────────────────────────────────
# derived_virtual_data 對應排序後的顯示順序，避免 sort 後 index 對不上
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

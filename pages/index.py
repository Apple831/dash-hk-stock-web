import dash
from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_stock_data
from indicators import calculate_indicators

dash.register_page(__name__, path="/", name="指數")

INDICES = {"^HSI": "恒生指數", "^HSTECH": "恒生科技"}

PERIODS = [
    {"label": "3個月", "value": "3mo"},
    {"label": "6個月", "value": "6mo"},
    {"label": "1年",   "value": "1y"},
    {"label": "2年",   "value": "2y"},
]


# ── 市場制度偵測（三層邏輯）────────────────────────────────────────
# 層①：趨勢 — MA20 vs MA60（中線趨勢方向）
# 層②：位置 — 收盤 vs MA20（短線強弱）
# 層③：動能 — MACD 柱正負（買賣力道）
# 三層全牛 → 🟢 牛市；三層全熊 → 🔴 熊市；其餘 → 🟡 震盪市
def detect_regime(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 60:
        return {"label": "資料不足", "color": "secondary", "layers": [], "price": None, "pct": None}

    c = df.iloc[-1]
    p = df.iloc[-2]

    l1 = bool(c["MA20"] > c["MA60"])
    l2 = bool(c["Close"] > c["MA20"])
    l3 = bool(c["MACD_Hist"] > 0)
    n  = sum([l1, l2, l3])

    layers = [
        {
            "name":  "① 趨勢 MA20/60",
            "ok":    l1,
            "val":   f"MA20={c['MA20']:.0f}  MA60={c['MA60']:.0f}",
        },
        {
            "name":  "② 位置 收盤/MA20",
            "ok":    l2,
            "val":   f"Close={c['Close']:.2f}  MA20={c['MA20']:.2f}",
        },
        {
            "name":  "③ 動能 MACD柱",
            "ok":    l3,
            "val":   f"MACD柱={c['MACD_Hist']:.4f}",
        },
    ]

    if n >= 3:
        label, color = "🟢 牛市", "success"
    elif n == 0:
        label, color = "🔴 熊市", "danger"
    else:
        label, color = "🟡 震盪市", "warning"

    pct = (float(c["Close"]) / float(p["Close"]) - 1) * 100 if float(p["Close"]) != 0 else 0.0
    return {
        "label":  label,
        "color":  color,
        "layers": layers,
        "price":  float(c["Close"]),
        "pct":    pct,
        "score":  n,
    }


def _regime_card(ticker: str, df: pd.DataFrame) -> dbc.Card:
    regime = detect_regime(df)
    name   = INDICES[ticker]

    price_text = f"{regime['price']:.2f}" if regime["price"] is not None else "—"
    pct        = regime.get("pct") or 0.0
    pct_color  = "text-success" if pct >= 0 else "text-danger"
    pct_text   = f"{pct:+.2f}%" if regime["price"] is not None else "—"

    layer_items = [
        dbc.ListGroupItem(
            [
                html.Span("✅ " if l["ok"] else "❌ "),
                html.Strong(l["name"] + "：", style={"fontSize": "0.82rem"}),
                html.Small(l["val"], className="text-muted"),
            ],
            color="success" if l["ok"] else "danger",
            style={"padding": "5px 12px"},
        )
        for l in regime["layers"]
    ]

    return dbc.Card(
        [
            dbc.CardHeader(html.Strong(f"{name}  {ticker}")),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(html.H4(price_text, className="mb-0"), width="auto"),
                            dbc.Col(
                                html.Span(pct_text, className=f"{pct_color} fw-bold fs-5"),
                                className="text-end",
                            ),
                        ],
                        align="center",
                        className="mb-2",
                    ),
                    dbc.Badge(
                        regime["label"],
                        color=regime["color"],
                        className="fs-6 mb-2 px-3 py-1",
                    ),
                    dbc.ListGroup(layer_items, flush=True, className="mt-1"),
                ]
            ),
        ],
        className="h-100",
    )


# ── 圖表建立 ─────────────────────────────────────────────────────────
def _build_chart(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="無法取得資料",
            x=0.5, y=0.5, xref="paper", yref="paper",
            font=dict(size=20, color="#888"), showarrow=False,
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=550,
        )
        return fig

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.58, 0.22, 0.20],
        vertical_spacing=0.02,
        subplot_titles=(title, "MACD", "RSI"),
    )

    # ── 行 1：K 線 + MA ──────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            name="K線",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            showlegend=False,
        ),
        row=1, col=1,
    )
    for ma_col, ma_color, ma_name in [
        ("MA20", "#f9a825", "MA20"),
        ("MA60", "#7c4dff", "MA60"),
    ]:
        if ma_col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df[ma_col],
                    line=dict(color=ma_color, width=1.3),
                    name=ma_name,
                ),
                row=1, col=1,
            )

    # ── 行 2：MACD ───────────────────────────────────────────────
    bar_colors = [
        "#26a69a" if v >= 0 else "#ef5350"
        for v in df["MACD_Hist"].fillna(0)
    ]
    fig.add_trace(
        go.Bar(
            x=df.index, y=df["MACD_Hist"],
            marker_color=bar_colors,
            name="MACD柱", showlegend=False,
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df["DIF"],
            line=dict(color="#42a5f5", width=1),
            name="DIF", showlegend=False,
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df["DEA"],
            line=dict(color="#ff7043", width=1),
            name="DEA", showlegend=False,
        ),
        row=2, col=1,
    )

    # ── 行 3：RSI ────────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df["RSI"],
            line=dict(color="#ce93d8", width=1.5),
            name="RSI", showlegend=False,
        ),
        row=3, col=1,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(239,83,80,0.4)",  row=3, col=1)
    fig.add_hline(y=50, line_dash="dot",  line_color="rgba(255,255,255,0.2)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(38,166,154,0.4)", row=3, col=1)

    fig.update_layout(
        height=580,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,20,0.6)",
        margin=dict(t=35, b=15, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True)

    return fig


# ── 頁面 Layout ──────────────────────────────────────────────────────
layout = html.Div(
    [
        # 標題列 + 週期選擇
        dbc.Row(
            [
                dbc.Col(html.H4("🌍 指數總覽", className="mb-0"), width="auto"),
                dbc.Col(
                    dbc.RadioItems(
                        id="index-period",
                        options=PERIODS,
                        value="1y",
                        inline=True,
                        className="mt-1",
                    ),
                ),
            ],
            align="center",
            className="mb-3",
        ),

        dcc.Loading(
            type="circle",
            color="#26a69a",
            children=[
                # 制度偵測卡片
                dbc.Row(
                    [
                        dbc.Col(html.Div(id="hsi-regime-card"),    md=6, className="mb-3"),
                        dbc.Col(html.Div(id="hstech-regime-card"), md=6, className="mb-3"),
                    ]
                ),
                # 圖表 Tabs
                dbc.Tabs(
                    [
                        dbc.Tab(
                            dcc.Graph(id="hsi-chart", config={"displayModeBar": False}),
                            label="^HSI 恒生",
                        ),
                        dbc.Tab(
                            dcc.Graph(id="hstech-chart", config={"displayModeBar": False}),
                            label="^HSTECH 科技",
                        ),
                    ],
                    className="mt-2",
                ),
            ],
        ),
    ],
    className="p-3",
)


# ── Callback ─────────────────────────────────────────────────────────
@callback(
    Output("hsi-regime-card",    "children"),
    Output("hstech-regime-card", "children"),
    Output("hsi-chart",    "figure"),
    Output("hstech-chart", "figure"),
    Input("index-period",  "value"),
)
def update_index(period: str):
    dfs = {}
    for ticker in ("^HSI", "^HSTECH"):
        raw = get_stock_data(ticker, period)
        dfs[ticker] = calculate_indicators(raw) if not raw.empty else raw

    hsi    = dfs["^HSI"]
    hstech = dfs["^HSTECH"]

    return (
        _regime_card("^HSI",    hsi),
        _regime_card("^HSTECH", hstech),
        _build_chart(hsi,    "恒生指數 ^HSI"),
        _build_chart(hstech, "恒生科技 ^HSTECH"),
    )

import dash
from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_stock_data
from indicators import calculate_indicators
from regime import detect_regime

dash.register_page(__name__, path="/", name="指數")

INDICES = {"^HSI": "恒生指數", "^HSTECH": "恒生科技"}

PERIODS = [
    {"label": "3個月", "value": "3mo"},
    {"label": "6個月", "value": "6mo"},
    {"label": "1年",   "value": "1y"},
    {"label": "2年",   "value": "2y"},
]


def _regime_card(ticker: str, df: pd.DataFrame) -> dbc.Card:
    regime = detect_regime(df)
    name   = INDICES[ticker]

    price_text = f"{regime['price']:.2f}" if regime["price"] is not None else "—"
    pct        = regime.get("pct") or 0.0
    pct_color  = "text-success" if pct >= 0 else "text-danger"
    pct_text   = f"{pct:+.2f}%" if regime["price"] is not None else "—"

    def _fmt(val, fmt):
        return fmt.format(val) if val is not None else "—"

    metric_items = [
        dbc.ListGroupItem(
            [
                html.Strong("MA缺口：", style={"fontSize": "0.82rem"}),
                html.Small(_fmt(regime["ma_gap_pct"], "{:+.2f}%"), className="text-muted"),
                html.Small("  （>+2%上升趨勢 / < -2%下降趨勢）",
                           className="text-muted", style={"fontSize": "0.74rem"}),
            ],
            style={"padding": "5px 12px"},
        ),
        dbc.ListGroupItem(
            [
                html.Strong("MACD%：", style={"fontSize": "0.82rem"}),
                html.Small(_fmt(regime["macd_pct"], "{:+.4f}%"), className="text-muted"),
                html.Small("  （>+0.5%強勢 / < -0.5%弱勢）",
                           className="text-muted", style={"fontSize": "0.74rem"}),
            ],
            style={"padding": "5px 12px"},
        ),
        dbc.ListGroupItem(
            [
                html.Strong("波動CoV：", style={"fontSize": "0.82rem"}),
                html.Small(_fmt(regime["cov_20"], "{:.2f}%"), className="text-muted"),
                html.Small("  （>2%震盪市 / ≤2%轉折期）",
                           className="text-muted", style={"fontSize": "0.74rem"}),
            ],
            style={"padding": "5px 12px"},
        ),
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
                    dbc.ListGroup(metric_items, flush=True, className="mt-1"),
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

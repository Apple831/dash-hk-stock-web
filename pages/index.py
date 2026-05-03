import dash
from dash import html, dcc, callback, Output, Input, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_stock_data
from indicators import calculate_indicators
from regime import detect_regime

dash.register_page(__name__, path="/", name="指數")

REGIME_INDICES = {"^HSI": "恒生指數", "^HSTECH": "恒生科技"}

PERIODS = [
    {"label": "3個月", "value": "3mo"},
    {"label": "6個月", "value": "6mo"},
    {"label": "1年",   "value": "1y"},
    {"label": "2年",   "value": "2y"},
]

REGIME_DEFS = [
    ("🟢 強牛市",  "牛市",  "success", "MA缺口>+2% 且 MACD%>+0.5%",    "趨勢強勁，積極做多"),
    ("🟢 弱牛市",  "牛市",  "success", "MA缺口>+2% 且 0<MACD%≤+0.5%",  "偏多但動能弱"),
    ("⚠️ 牛市警惕","牛市",  "warning", "MA缺口>+2% 且 MACD%≤0",         "均線多頭但 MACD 轉弱"),
    ("🟡 震盪市",  "震盪市","warning", "MA缺口±2%以內 且 CoV>2%",        "橫盤震盪，均值回歸策略有效"),
    ("🔵 轉折期",  "震盪市","info",    "MA缺口±2%以內 且 CoV≤2%",        "低波動轉折，趨勢未明"),
    ("⚠️ 熊市觀察","熊市",  "warning", "MA缺口<-2% 且 MACD%≥0",          "均線空頭但 MACD 未惡化"),
    ("🔴 弱熊市",  "熊市",  "danger",  "MA缺口<-2% 且 -0.5%<MACD%<0",  "偏空但動能弱"),
    ("🔴 強熊市",  "熊市",  "danger",  "MA缺口<-2% 且 MACD%<-0.5%",    "趨勢強烈下跌，謹慎操作"),
]

_EMPTY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)


# ── 制度卡片 ─────────────────────────────────────────────────────────
def _regime_card(ticker: str, df: pd.DataFrame) -> dbc.Card:
    regime = detect_regime(df)
    name   = REGIME_INDICES[ticker]

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
                html.Small("  （>+2%上升趨勢 / <-2%下降趨勢）",
                           className="text-muted", style={"fontSize": "0.74rem"}),
            ],
            style={"padding": "5px 12px"},
        ),
        dbc.ListGroupItem(
            [
                html.Strong("MACD%：", style={"fontSize": "0.82rem"}),
                html.Small(_fmt(regime["macd_pct"], "{:+.4f}%"), className="text-muted"),
                html.Small("  （>+0.5%強勢 / <-0.5%弱勢）",
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


# ── K 線 + MACD + RSI 圖表 ───────────────────────────────────────────
def _build_chart(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="無法取得資料",
            x=0.5, y=0.5, xref="paper", yref="paper",
            font=dict(size=20, color="#888"), showarrow=False,
        )
        fig.update_layout(**_EMPTY_LAYOUT, height=550)
        return fig

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.58, 0.22, 0.20],
        vertical_spacing=0.02,
        subplot_titles=(title, "MACD", "RSI"),
    )

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
                go.Scatter(x=df.index, y=df[ma_col],
                           line=dict(color=ma_color, width=1.3), name=ma_name),
                row=1, col=1,
            )

    bar_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in df["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"],
                         marker_color=bar_colors, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["DIF"],
                             line=dict(color="#42a5f5", width=1), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["DEA"],
                             line=dict(color="#ff7043", width=1), showlegend=False), row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"],
                             line=dict(color="#ce93d8", width=1.5), showlegend=False), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(239,83,80,0.4)",   row=3, col=1)
    fig.add_hline(y=50, line_dash="dot",  line_color="rgba(255,255,255,0.2)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(38,166,154,0.4)",  row=3, col=1)

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


# ── MA 缺口走勢圖 ────────────────────────────────────────────────────
def _build_magap_chart(dfs: dict) -> go.Figure:
    fig = go.Figure()
    palette = {"^HSI": "#f9a825", "^HSTECH": "#7c4dff"}
    for ticker, name in REGIME_INDICES.items():
        df = dfs.get(ticker, pd.DataFrame())
        if df.empty or "MA20" not in df.columns or "MA60" not in df.columns:
            continue
        ma_gap = (df["MA20"] - df["MA60"]) / df["MA60"] * 100
        fig.add_trace(go.Scatter(
            x=df.index, y=ma_gap,
            name=name,
            line=dict(color=palette[ticker], width=1.5),
        ))
    for y, clr, txt in [(2, "rgba(38,166,154,0.55)", "+2%"),
                        (0, "rgba(255,255,255,0.2)",  "0"),
                        (-2, "rgba(239,83,80,0.55)",  "-2%")]:
        fig.add_hline(y=y, line_dash="dash", line_color=clr,
                      annotation_text=txt,
                      annotation_font=dict(color=clr, size=11))
    fig.update_layout(
        title=dict(text="MA 缺口 %（MA20−MA60）/ MA60", font=dict(size=13)),
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,20,0.6)",
        margin=dict(t=40, b=20, l=55, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    return fig


# ── MACD% 走勢圖 ─────────────────────────────────────────────────────
def _build_macdpct_chart(dfs: dict) -> go.Figure:
    fig = go.Figure()
    palette = {"^HSI": "#42a5f5", "^HSTECH": "#ff7043"}
    for ticker, name in REGIME_INDICES.items():
        df = dfs.get(ticker, pd.DataFrame())
        if df.empty or "MACD_Hist" not in df.columns:
            continue
        macd_pct = df["MACD_Hist"] / df["Close"].replace(0, float("nan")) * 100
        fig.add_trace(go.Scatter(
            x=df.index, y=macd_pct,
            name=name,
            line=dict(color=palette[ticker], width=1.5),
        ))
    for y, clr, txt in [(0.5,  "rgba(38,166,154,0.55)", "+0.5%"),
                        (0,    "rgba(255,255,255,0.2)",  "0"),
                        (-0.5, "rgba(239,83,80,0.55)",   "-0.5%")]:
        fig.add_hline(y=y, line_dash="dash", line_color=clr,
                      annotation_text=txt,
                      annotation_font=dict(color=clr, size=11))
    fig.update_layout(
        title=dict(text="MACD%（MACD 柱 / 收價）", font=dict(size=13)),
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,20,0.6)",
        margin=dict(t=40, b=20, l=55, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    return fig


# ── 近 60 日制度序列（向量化）────────────────────────────────────────
def _regime_series(df: pd.DataFrame) -> list[dict]:
    if df.empty or len(df) < 62:
        return []

    recent   = df.iloc[-60:]
    ma_gap   = (recent["MA20"] - recent["MA60"]) / recent["MA60"] * 100
    macd_pct = recent["MACD_Hist"] / recent["Close"].replace(0, float("nan")) * 100
    full_cov = df["Close"].rolling(20).std() / df["Close"].rolling(20).mean() * 100
    cov_20   = full_cov.iloc[-60:]

    rows = []
    for i in range(len(recent)):
        mg = float(ma_gap.iloc[i])   if pd.notna(ma_gap.iloc[i])   else 0.0
        mp = float(macd_pct.iloc[i]) if pd.notna(macd_pct.iloc[i]) else 0.0
        cv = float(cov_20.iloc[i])   if pd.notna(cov_20.iloc[i])   else 0.0

        if abs(mg) < 2.0:
            label, color = ("震盪市", "warning") if cv > 2.0 else ("轉折期", "info")
        elif mg > 2.0:
            if mp > 0.5:      label, color = "強牛市",  "success"
            elif mp > 0:      label, color = "弱牛市",  "success"
            else:             label, color = "牛市警惕","warning"
        else:
            if mp < -0.5:     label, color = "強熊市",  "danger"
            elif mp < 0:      label, color = "弱熊市",  "danger"
            else:             label, color = "熊市觀察","warning"

        rows.append({
            "date":  recent.index[i],
            "label": label,
            "color": color,
        })
    return rows


def _build_regime_history(dfs: dict) -> list:
    sections = []
    for ticker, name in REGIME_INDICES.items():
        df  = dfs.get(ticker, pd.DataFrame())
        rows = _regime_series(df)
        if not rows:
            sections.append(html.Small(f"{name}: 資料不足", className="text-muted d-block mb-2"))
            continue
        badges = [
            dbc.Badge(
                f"{r['date'].strftime('%m/%d')} {r['label']}",
                color=r["color"],
                className="me-1 mb-1",
                style={"fontSize": "0.72rem"},
            )
            for r in rows
        ]
        sections.append(html.Div([
            html.Strong(f"{name}", className="d-block mb-1 mt-2 small"),
            html.Div(badges, style={"lineHeight": "2.1"}),
        ]))
    return sections


# ── 制度定義說明表（靜態）────────────────────────────────────────────
_REGIME_DEF_TABLE = dbc.Table(
    [
        html.Thead(html.Tr([
            html.Th("制度標籤"),
            html.Th("類別"),
            html.Th("判定條件"),
            html.Th("操作含義"),
        ])),
        html.Tbody([
            html.Tr([
                html.Td(dbc.Badge(label, color=color, className="px-2 py-1")),
                html.Td(bucket, style={"fontSize": "0.82rem"}),
                html.Td(cond,   style={"fontSize": "0.82rem"}),
                html.Td(meaning,style={"fontSize": "0.82rem"}),
            ])
            for label, bucket, color, cond, meaning in REGIME_DEFS
        ]),
    ],
    bordered=True, dark=True, hover=True, size="sm",
    className="mb-0",
)


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
                # 圖表 Tabs（HSI / HSTECH / VIX）
                dbc.Tabs(
                    [
                        dbc.Tab(
                            dcc.Graph(id="hsi-chart",    config={"displayModeBar": False}),
                            label="^HSI 恒生",
                        ),
                        dbc.Tab(
                            dcc.Graph(id="hstech-chart", config={"displayModeBar": False}),
                            label="^HSTECH 科技",
                        ),
                        dbc.Tab(
                            dcc.Graph(id="vix-chart",    config={"displayModeBar": False}),
                            label="^VIX 恐慌",
                        ),
                    ],
                    className="mt-2",
                ),
                # MA 缺口 + MACD% 走勢圖
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Graph(id="index-magap-chart",
                                      config={"displayModeBar": False}),
                            md=6, className="mt-3",
                        ),
                        dbc.Col(
                            dcc.Graph(id="index-macdpct-chart",
                                      config={"displayModeBar": False}),
                            md=6, className="mt-3",
                        ),
                    ]
                ),
                # 近 60 日制度演變
                dbc.Card(
                    [
                        dbc.CardHeader(html.Strong("📅 近 60 日制度演變")),
                        dbc.CardBody(
                            html.Div(id="regime-history"),
                            className="py-2",
                        ),
                    ],
                    className="mt-3",
                ),
            ],
        ),

        # 制度定義說明表（可折疊，靜態內容，在 Loading 外）
        dbc.Card(
            [
                dbc.CardHeader(
                    dbc.Button(
                        "📖 制度定義說明表",
                        id="regime-def-toggle",
                        color="link",
                        className="text-start w-100 p-0 text-decoration-none",
                        style={"color": "#aaa", "fontSize": "0.9rem"},
                    )
                ),
                dbc.Collapse(
                    dbc.CardBody(_REGIME_DEF_TABLE, className="p-2"),
                    id="regime-def-collapse",
                    is_open=False,
                ),
            ],
            className="mt-3",
        ),
    ],
    className="p-3",
)


# ── Callback 1：主圖（HSI + HSTECH + VIX）────────────────────────────
@callback(
    Output("hsi-regime-card",    "children"),
    Output("hstech-regime-card", "children"),
    Output("hsi-chart",    "figure"),
    Output("hstech-chart", "figure"),
    Output("vix-chart",    "figure"),
    Input("index-period",  "value"),
)
def update_index(period: str):
    dfs = {}
    for ticker in ("^HSI", "^HSTECH", "^VIX"):
        raw = get_stock_data(ticker, period)
        dfs[ticker] = calculate_indicators(raw) if not raw.empty else raw

    return (
        _regime_card("^HSI",    dfs["^HSI"]),
        _regime_card("^HSTECH", dfs["^HSTECH"]),
        _build_chart(dfs["^HSI"],    "恒生指數 ^HSI"),
        _build_chart(dfs["^HSTECH"], "恒生科技 ^HSTECH"),
        _build_chart(dfs["^VIX"],    "VIX 恐慌指數 ^VIX"),
    )


# ── Callback 2：MA 缺口、MACD%、制度歷史 ─────────────────────────────
@callback(
    Output("index-magap-chart",   "figure"),
    Output("index-macdpct-chart", "figure"),
    Output("regime-history",      "children"),
    Input("index-period", "value"),
)
def update_supplementary(period: str):
    dfs = {}
    for ticker in ("^HSI", "^HSTECH"):
        raw = get_stock_data(ticker, period)
        dfs[ticker] = calculate_indicators(raw) if not raw.empty else raw

    return (
        _build_magap_chart(dfs),
        _build_macdpct_chart(dfs),
        _build_regime_history(dfs),
    )


# ── Callback 3：制度定義折疊 ──────────────────────────────────────────
@callback(
    Output("regime-def-collapse", "is_open"),
    Input("regime-def-toggle",    "n_clicks"),
    State("regime-def-collapse",  "is_open"),
    prevent_initial_call=True,
)
def toggle_regime_def(n_clicks, is_open):
    return not is_open

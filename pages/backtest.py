import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data import get_cached, load_stocks
from backtest import run_backtest, calc_bt_metrics
from config import STRATEGY_PRESETS, BUY_LABELS, SELL_LABELS, PRESET_CUSTOM, MIN_BARS_FOR_INDICATORS

dash.register_page(__name__, path="/backtest", name="回測")

STRATEGY_OPTIONS = (
    [{"label": PRESET_CUSTOM, "value": PRESET_CUSTOM}]
    + [{"label": n, "value": n} for n in STRATEGY_PRESETS]
)
DEFAULT_STRATEGY = list(STRATEGY_PRESETS.keys())[0]

PERIOD_OPTIONS = [
    {"label": "1年", "value": "1y"},
    {"label": "2年", "value": "2y"},
    {"label": "5年", "value": "5y"},
]

# ── Table 樣式 ────────────────────────────────────────────────────────
_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_TRADE_COND = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
    {"if": {"filter_query": "{回報%} > 0", "column_id": "回報%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{回報%} < 0", "column_id": "回報%"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{盈虧(HKD)} > 0", "column_id": "盈虧(HKD)"},
     "color": "#26a69a"},
    {"if": {"filter_query": "{盈虧(HKD)} < 0", "column_id": "盈虧(HKD)"},
     "color": "#ef5350"},
]

TRADE_COLS = [
    {"name": "買入日期",   "id": "買入日期"},
    {"name": "賣出日期",   "id": "賣出日期"},
    {"name": "買入價",     "id": "買入價"},
    {"name": "賣出價",     "id": "賣出價"},
    {"name": "回報%",      "id": "回報%"},
    {"name": "盈虧(HKD)",  "id": "盈虧(HKD)"},
    {"name": "持倉天數",   "id": "持倉天數"},
    {"name": "賣出原因",   "id": "賣出原因"},
]


# ── UI 助手 ───────────────────────────────────────────────────────────
def _metric_card(label: str, value: str, color: str = "white"):
    return dbc.Col(
        dbc.Card(dbc.CardBody([
            html.Div(label, className="small text-muted mb-1"),
            html.Div(value, className="fw-bold",
                     style={"color": color, "fontSize": "1.05rem"}),
        ], className="py-2 px-3"), className="h-100"),
        xs=6, md=2,
    )


def _color_pct(val: float) -> str:
    return "#26a69a" if val > 0 else ("#ef5350" if val < 0 else "white")


# ── 圖表 ──────────────────────────────────────────────────────────────
def _equity_chart(equity_df: pd.DataFrame, df: pd.DataFrame, trade_size: float) -> go.Figure:
    fig = go.Figure()

    if equity_df.empty:
        fig.add_annotation(text="無交易記錄", x=0.5, y=0.5,
                           xref="paper", yref="paper",
                           font=dict(size=16, color="#888"), showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", height=300)
        return fig

    eq = equity_df["equity"].sort_index()

    fig.add_trace(go.Scatter(
        x=eq.index, y=eq.values,
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.08)",
        line=dict(color="#26a69a", width=2),
        name="策略資金曲線",
    ))

    # 持有不動基準線
    if not df.empty and len(df) > 62:
        bh_start = float(df["Close"].iloc[61])
        if bh_start > 0:
            bh = df["Close"].iloc[61:] / bh_start * trade_size
            fig.add_trace(go.Scatter(
                x=bh.index, y=bh.values,
                line=dict(color="#7c4dff", width=1.5, dash="dash"),
                name="持有不動", opacity=0.65,
            ))

    fig.add_hline(y=trade_size, line_dash="dot",
                  line_color="rgba(255,255,255,0.2)")

    fig.update_layout(
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,20,0.6)",
        margin=dict(t=10, b=15, l=70, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)",
                     tickformat=",.0f", tickprefix="$")
    return fig


def _monthly_heatmap(equity_df: pd.DataFrame, trade_size: float) -> go.Figure:
    if equity_df.empty or len(equity_df) < 2:
        return go.Figure()

    eq = equity_df["equity"].sort_index()

    # 前向填充缺失日期，再取月末
    try:
        date_rng  = pd.date_range(eq.index[0], eq.index[-1], freq="D")
        eq_full   = eq.reindex(date_rng).ffill()
        eq_monthly = eq_full.resample("ME").last()
    except Exception:
        eq_monthly = eq.resample("ME").last()

    # 首月補 trade_size 作為起始值
    first_month = eq_monthly.index[0] - pd.offsets.MonthEnd(1)
    if first_month not in eq_monthly.index:
        eq_monthly = pd.concat([pd.Series([trade_size], index=[first_month]), eq_monthly])
        eq_monthly.sort_index(inplace=True)

    monthly_pct = eq_monthly.pct_change() * 100
    monthly_pct = monthly_pct.dropna()

    if monthly_pct.empty:
        return go.Figure()

    years        = sorted(monthly_pct.index.year.unique())
    month_labels = ["1月", "2月", "3月", "4月", "5月", "6月",
                    "7月", "8月", "9月", "10月", "11月", "12月"]
    z, text_z = [], []
    for yr in years:
        row, txt = [], []
        for m in range(1, 13):
            mask = (monthly_pct.index.year == yr) & (monthly_pct.index.month == m)
            if mask.any():
                v = float(monthly_pct[mask].iloc[0])
                row.append(v)
                txt.append(f"{v:+.1f}%")
            else:
                row.append(None)
                txt.append("")
        z.append(row)
        text_z.append(txt)

    fig = go.Figure(go.Heatmap(
        z=z, x=month_labels, y=[str(y) for y in years],
        colorscale=[[0, "#ef5350"], [0.5, "#263238"], [1, "#26a69a"]],
        zmid=0,
        text=text_z, texttemplate="%{text}",
        showscale=False,
        hovertemplate="<b>%{y} %{x}</b><br>月回報: %{z:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        height=max(160, len(years) * 42 + 60),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=45, r=10),
        font=dict(color="#ccc", size=11),
    )
    return fig


# ── K 線 + 交易標記圖 ─────────────────────────────────────────────────
def _trade_chart(df: pd.DataFrame, trades: list) -> go.Figure:
    if df.empty or not trades:
        return go.Figure()

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name="K線",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        showlegend=False,
    ))
    for col, color, name in [("MA20", "#f9a825", "MA20"), ("MA60", "#7c4dff", "MA60")]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col],
                line=dict(color=color, width=1),
                name=name,
            ))

    buy_x, buy_y = [], []
    sell_x, sell_y, sell_c = [], [], []

    for t in trades:
        try:
            bd = pd.Timestamp(t["買入日期"])
            buy_x.append(bd)
            buy_y.append(float(t["買入價"]))
        except Exception:
            pass
        sd_str = t.get("賣出日期", "")
        if "（持倉中）" not in sd_str and t.get("賣出價"):
            try:
                sell_x.append(pd.Timestamp(sd_str))
                sell_y.append(float(t["賣出價"]))
                sell_c.append("#26a69a" if float(t.get("回報%", 0)) > 0 else "#ef5350")
            except Exception:
                pass

    if buy_x:
        fig.add_trace(go.Scatter(
            x=buy_x, y=buy_y, mode="markers",
            marker=dict(symbol="triangle-up", size=12, color="#26a69a",
                        line=dict(color="#fff", width=1)),
            name="買入",
        ))
    if sell_x:
        fig.add_trace(go.Scatter(
            x=sell_x, y=sell_y, mode="markers",
            marker=dict(symbol="triangle-down", size=12, color=sell_c,
                        line=dict(color="#fff", width=1)),
            name="賣出",
        ))

    fig.update_layout(
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,20,0.6)",
        margin=dict(t=20, b=15, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    return fig


# ── 全倉掃描回測 ──────────────────────────────────────────────────────
_PORTFOLIO_COLS = [
    {"name": "代碼",          "id": "代碼"},
    {"name": "平均每筆%",     "id": "平均每筆%"},
    {"name": "勝率%",         "id": "勝率%"},
    {"name": "交易次數",      "id": "交易次數"},
    {"name": "Profit Factor", "id": "Profit Factor"},
    {"name": "最大回撤%",     "id": "最大回撤%"},
]
_PORTFOLIO_COND = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
    {"if": {"filter_query": "{平均每筆%} > 0", "column_id": "平均每筆%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{平均每筆%} < 0", "column_id": "平均每筆%"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{Profit Factor} >= 1.5", "column_id": "Profit Factor"},
     "color": "#26a69a"},
]


def _run_portfolio_scan(strategy, period, trade_size, slippage,
                        stop_loss, take_profit, max_hold,
                        custom_buy, custom_sell, commission=None):
    tickers = load_stocks()
    rows    = []
    errors  = 0

    for ticker in tickers:
        try:
            trades_t, eq_t, m_t, _, err_t = _run(
                strategy, ticker, period, trade_size,
                slippage, stop_loss, take_profit, max_hold,
                custom_buy=custom_buy, custom_sell=custom_sell,
                commission_ui=commission,
            )
            if err_t or not m_t or m_t["交易次數"] == 0:
                continue
            rows.append({
                "代碼":          ticker,
                "平均每筆%":     round(m_t["平均每筆回報%"], 2),
                "勝率%":         round(m_t["勝率%"], 1),
                "交易次數":      m_t["交易次數"],
                "Profit Factor": round(m_t["Profit Factor"], 2),
                "最大回撤%":     round(m_t["最大回撤%"], 2),
            })
        except Exception:
            errors += 1

    rows.sort(key=lambda x: -x["平均每筆%"])
    return rows, errors


# ── 回測核心 ──────────────────────────────────────────────────────────
def _run(strategy, ticker, period, trade_size, slippage_pct_ui,
         stop_loss, take_profit, max_hold,
         custom_buy=None, custom_sell=None, commission_ui=None):

    if strategy == PRESET_CUSTOM:
        buy_sigs  = tuple(f"b{i+1}" in (custom_buy  or []) for i in range(len(BUY_LABELS)))
        sell_sigs = tuple(f"s{i+1}" in (custom_sell or []) for i in range(8))
        if not any(buy_sigs):
            return None, None, None, None, "⚠️ 自定義模式請至少選擇一個買入信號"
        min_hold_days   = None
        cooldown_days   = None
        seasonal_filter = False
    else:
        preset = STRATEGY_PRESETS.get(strategy)
        if not preset:
            return None, None, None, None, "⚠️ 找不到策略"
        buy_sigs        = preset["buy"]
        sell_sigs       = preset["sell"]
        min_hold_days   = preset.get("min_hold_days")
        cooldown_days   = preset.get("cooldown_days")
        seasonal_filter = preset.get("seasonal_filter", False)

    ticker          = (ticker or "0700.HK").strip().upper()
    trade_size      = float(trade_size or 100_000)
    slippage_pct    = float(slippage_pct_ui or 0.10) / 100
    commission_pct  = float(commission_ui or 0.26) / 100
    stop_loss_v  = float(stop_loss  or 0) or None
    take_profit_v= float(take_profit or 0) or None
    max_hold_v   = int(float(max_hold or 0)) or None

    df = get_cached(ticker, period)
    if df.empty:
        return None, None, None, None, f"❌ 無法獲取 {ticker} 數據"
    if len(df) < MIN_BARS_FOR_INDICATORS:
        return None, None, None, None, f"⚠️ {ticker} 數據不足（{len(df)} 根K線）"

    try:
        trades, equity_df, _ = run_backtest(
            df,
            buy_sigs=buy_sigs,
            sell_sigs=sell_sigs,
            trade_size=trade_size,
            slippage_pct=slippage_pct,
            commission_pct=commission_pct,
            stop_loss_pct=stop_loss_v,
            take_profit_pct=take_profit_v,
            max_hold_days=max_hold_v,
            min_hold_days=min_hold_days,
            cooldown_days=cooldown_days,
            ticker=ticker,
            seasonal_filter=seasonal_filter,
        )
    except ValueError as e:
        return None, None, None, None, f"⚠️ 參數錯誤：{e}"
    except Exception as e:
        return None, None, None, None, f"❌ 回測失敗：{str(e)[:80]}"

    metrics = calc_bt_metrics(trades, equity_df, trade_size)
    return trades, equity_df, metrics, df, None


# ── Layout ───────────────────────────────────────────────────────────
def _param_col(label, input_id, **kwargs):
    return dbc.Col([
        html.Label(label, className="small text-muted mb-1 d-block"),
        dbc.Input(id=input_id, type="number", size="sm", **kwargs),
    ], xs=6, md=2, className="mb-2")


layout = html.Div([
    html.H4("📊 回測", className="mb-3"),

    # ── 行 1：策略 + 股票 + 週期 ─────────────────────────────────────
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id="bt-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
                style={"color": "#111"},
            ),
            md=6, className="mb-2",
        ),
        dbc.Col(
            dbc.Input(id="bt-ticker", value="0700.HK",
                      placeholder="股票代碼", type="text", size="sm"),
            md=2, className="mb-2",
        ),
        dbc.Col(
            dbc.RadioItems(
                id="bt-period",
                options=PERIOD_OPTIONS,
                value="1y",
                inline=True,
                className="pt-1",
            ),
            md=3, className="mb-2",
        ),
    ], className="mb-1"),

    # ── 行 2：回測參數 + 按鈕 ─────────────────────────────────────────
    dbc.Row([
        _param_col("每筆金額 (HKD)", "bt-trade-size",  value=100000, step=10000),
        _param_col("純滑點%",         "bt-slippage",    value=0.10,   step=0.01,  min=0),
        _param_col("手續費%（雙邊）",  "bt-commission",  value=0.26,   step=0.01,  min=0),
        _param_col("止損% (0=不啟用)", "bt-stop-loss",  value=0,      step=1,     min=0),
        _param_col("止盈% (0=不啟用)", "bt-take-profit",value=0,      step=5,     min=0),
        _param_col("最長持倉天數 (0=不限)", "bt-max-hold", value=0,   step=10,    min=0),
        dbc.Col(
            dbc.Button("📊 開始回測", id="bt-btn",
                       color="primary", size="sm", className="w-100 mt-4"),
            xs=6, md=2, className="mb-2",
        ),
        dbc.Col(
            dbc.Button("🚀 全倉掃描", id="bt-portfolio-btn",
                       color="warning", size="sm", className="w-100 mt-4"),
            xs=6, md=2, className="mb-2",
        ),
    ], className="mb-3"),

    # 自定義訊號面板（選「✏️ 自定義」時顯示）
    html.Div(
        id="bt-custom-panel",
        style={"display": "none"},
        children=[
            dbc.Card(dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Small(
                            "📈 買入信號（AND 邏輯）",
                            className="text-muted fw-bold d-block mb-2",
                        ),
                        dbc.Checklist(
                            id="bt-custom-buy",
                            options=[
                                {"label": f" {BUY_LABELS[i]}", "value": f"b{i+1}"}
                                for i in range(len(BUY_LABELS))
                            ],
                            value=[],
                            inline=True,
                            className="small",
                            inputStyle={"cursor": "pointer"},
                            labelStyle={"marginRight": "12px", "cursor": "pointer"},
                        ),
                    ], md=7, className="mb-2"),
                    dbc.Col([
                        html.Small(
                            "📉 賣出訊號（任一觸發）",
                            className="text-muted fw-bold d-block mb-2",
                        ),
                        dbc.Checklist(
                            id="bt-custom-sell",
                            options=[
                                {"label": f" {SELL_LABELS[i]}", "value": f"s{i+1}"}
                                for i in range(8)
                            ],
                            value=[],
                            inline=True,
                            className="small",
                            inputStyle={"cursor": "pointer"},
                            labelStyle={"marginRight": "12px", "cursor": "pointer"},
                        ),
                    ], md=5, className="mb-2"),
                ]),
            ], className="py-2 px-3"), className="border-warning mb-3"),
        ],
    ),

    html.Small(id="bt-status", className="text-muted d-block mb-3"),

    dcc.Loading(type="circle", color="#42a5f5", children=[
        html.Div(id="bt-result"),
    ]),
], className="p-3")


# ── Callbacks ────────────────────────────────────────────────────────
@callback(
    Output("bt-custom-panel", "style"),
    Input("bt-strategy",      "value"),
)
def cb_toggle_custom(strategy):
    return {} if strategy == PRESET_CUSTOM else {"display": "none"}


@callback(
    Output("bt-status", "children"),
    Output("bt-result", "children"),
    Input("bt-btn",              "n_clicks"),
    Input("bt-portfolio-btn",    "n_clicks"),
    State("bt-strategy",         "value"),
    State("bt-ticker",           "value"),
    State("bt-period",           "value"),
    State("bt-trade-size",       "value"),
    State("bt-slippage",         "value"),
    State("bt-commission",       "value"),
    State("bt-stop-loss",        "value"),
    State("bt-take-profit",      "value"),
    State("bt-max-hold",         "value"),
    State("bt-custom-buy",       "value"),
    State("bt-custom-sell",      "value"),
    prevent_initial_call=True,
)
def cb_run_backtest(n_single, n_portfolio, strategy, ticker, period,
                    trade_size, slippage, commission, stop_loss, take_profit, max_hold,
                    custom_buy, custom_sell):

    trigger = ctx.triggered_id

    # ── 🚀 全倉掃描回測 ──────────────────────────────────────────────
    if trigger == "bt-portfolio-btn":
        rows, errors = _run_portfolio_scan(
            strategy, period, trade_size, slippage,
            stop_loss, take_profit, max_hold,
            custom_buy, custom_sell, commission=commission,
        )
        if not rows:
            return "⚠️ 全倉掃描：無任何股票有交易記錄（請先下載緩存數據）", []

        err_note = f"，{errors} 隻略過" if errors else ""
        status = (
            f"🚀 全倉掃描完成：{len(rows)} 隻有交易記錄"
            f"（策略：{strategy}，週期：{period}）{err_note}"
        )
        table = dash_table.DataTable(
            columns=_PORTFOLIO_COLS,
            data=rows,
            sort_action="native",
            page_size=30,
            style_header=_HDR,
            style_data=_DAT,
            style_data_conditional=_PORTFOLIO_COND,
            style_cell={
                "textAlign": "center", "padding": "5px 12px",
                "fontFamily": "monospace", "fontSize": "0.85rem",
            },
            style_cell_conditional=[
                {"if": {"column_id": "代碼"}, "textAlign": "left"},
            ],
            style_table={"overflowX": "auto"},
        )
        return status, [
            dbc.Alert(
                f"🚀 {len(rows)} 隻命中策略，按平均每筆%降序排列",
                color="warning", className="mb-3",
            ),
            html.H6("📊 全倉掃描排行榜", className="mb-2"),
            table,
        ]

    # ── 📊 單股回測 ──────────────────────────────────────────────────
    trades, equity_df, m, df, err = _run(
        strategy, ticker, period, trade_size,
        slippage, stop_loss, take_profit, max_hold,
        custom_buy=custom_buy, custom_sell=custom_sell,
        commission_ui=commission,
    )
    if err:
        return err, []
    if not m:
        return "⚠️ 無交易記錄（策略條件未觸發）", []

    trade_size_v = float(trade_size or 100_000)
    ticker_clean = (ticker or "0700.HK").strip().upper()
    if strategy == PRESET_CUSTOM:
        min_hold = 0
    else:
        preset   = STRATEGY_PRESETS.get(strategy, {})
        min_hold = preset.get("min_hold_days", 0) or 0

    # ── 指標卡片 ────────────────────────────────────────────────────
    cards = dbc.Row([
        _metric_card("累計回報%（非複利）", f"{m['累計回報%']:+.2f}%",
                     _color_pct(m["累計回報%"])),
        _metric_card("平均每筆回報%",  f"{m['平均每筆回報%']:+.2f}%",
                     _color_pct(m["平均每筆回報%"])),
        _metric_card("交易次數",       str(m["交易次數"])),
        _metric_card("勝率%",          f"{m['勝率%']:.1f}%",
                     "#26a69a" if m["勝率%"] >= 50 else "#ef5350"),
        _metric_card("最大回撤%",      f"{m['最大回撤%']:.2f}%", "#ef5350"),
        _metric_card("Profit Factor", f"{m['Profit Factor']:.2f}",
                     "#26a69a" if m["Profit Factor"] >= 1.5 else "white"),
    ], className="mb-3 g-2")

    sub_cards = dbc.Row([
        _metric_card("平均盈利%",    f"{m['平均盈利%']:+.2f}%", "#26a69a"),
        _metric_card("平均虧損%",    f"{m['平均虧損%']:+.2f}%", "#ef5350"),
        _metric_card("最佳一筆%",    f"{m['最佳一筆%']:+.2f}%", "#26a69a"),
        _metric_card("最差一筆%",    f"{m['最差一筆%']:+.2f}%", "#ef5350"),
        _metric_card("平均持倉天數", f"{m['平均持倉天數']:.1f}日"),
        _metric_card("最大連輸",     str(m["最大連輸"]),
                     "#ef5350" if m["最大連輸"] >= 5 else "white"),
    ], className="mb-4 g-2")

    # ── 資金曲線 ─────────────────────────────────────────────────────
    equity_fig = _equity_chart(equity_df, df, trade_size_v)
    equity_section = html.Div([
        html.H6("📈 資金曲線（含持有不動基準）", className="mt-2 mb-1"),
        dcc.Graph(figure=equity_fig, config={"displayModeBar": False}),
    ], className="mb-3")

    # ── K 線交易標記圖 ────────────────────────────────────────────────
    trade_chart_fig = _trade_chart(df, trades)
    trade_chart_section = html.Div([
        html.H6("🕯️ K 線交易標記（▲買入  ▼賣出）", className="mb-1"),
        dcc.Graph(figure=trade_chart_fig, config={"displayModeBar": False}),
    ], className="mb-3")

    # ── 月度熱力圖 ───────────────────────────────────────────────────
    heatmap_fig = _monthly_heatmap(equity_df, trade_size_v)
    heatmap_section = html.Div([
        html.H6("🗓️ 月度損益熱力圖", className="mb-1"),
        dcc.Graph(figure=heatmap_fig, config={"displayModeBar": False}),
    ], className="mb-3") if not equity_df.empty else []

    # ── 逐筆交易記錄 ─────────────────────────────────────────────────
    display_trades = [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in trades
    ]
    trade_table = html.Div([
        html.H6(f"📋 逐筆交易記錄（共 {len(trades)} 筆）", className="mb-1"),
        dash_table.DataTable(
            columns=TRADE_COLS,
            data=display_trades,
            sort_action="native",
            page_size=20,
            style_header=_HDR,
            style_data=_DAT,
            style_data_conditional=_TRADE_COND,
            style_cell={
                "textAlign": "left",
                "padding": "5px 12px",
                "fontFamily": "monospace",
                "fontSize": "0.85rem",
            },
            style_table={"overflowX": "auto"},
        ),
    ], className="mb-3")

    status = (
        f"✅ {ticker_clean} | {strategy} | "
        f"最終資金 {m['最終資金']:,.0f} HKD | "
        f"MIN{min_hold}日"
    )

    return status, [
        html.Small(
            "ℹ️ 回測採固定倉位模式（每筆各用設定金額獨立試驗，非複利）",
            className="text-muted d-block mb-2",
            style={"fontSize": "0.78rem"},
        ),
        cards, sub_cards,
        equity_section, trade_chart_section,
        heatmap_section, trade_table,
    ]

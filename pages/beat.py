import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc

from data import get_stock_data, get_cached, load_stocks
from indicators import calculate_indicators

dash.register_page(__name__, path="/beat", name="跑贏大市")

PERIOD_OPTIONS = [
    {"label": "1日",   "value": "1d"},
    {"label": "1週",   "value": "1w"},
    {"label": "1個月", "value": "1mo"},
    {"label": "3個月", "value": "3mo"},
    {"label": "6個月", "value": "6mo"},
]

PERIOD_DAYS = {
    "1d":  1,
    "1w":  5,
    "1mo": 21,
    "3mo": 63,
    "6mo": 126,
}

PERIOD_LABEL = {
    "1d":  "1日",
    "1w":  "1週",
    "1mo": "1個月",
    "3mo": "3個月",
    "6mo": "6個月",
}

# ── Table 樣式 ────────────────────────────────────────────────────────
_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_COND = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
    {"if": {"state": "selected"}, "backgroundColor": "rgba(249,168,37,0.2)",
     "border": "1px solid #f9a825"},
    # 股票升幅
    {"if": {"filter_query": "{股票升幅%} > 0", "column_id": "股票升幅%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{股票升幅%} < 0", "column_id": "股票升幅%"},
     "color": "#ef5350", "fontWeight": "bold"},
    # 超額回報（主要指標）
    {"if": {"filter_query": "{超額回報%} >= 5", "column_id": "超額回報%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{超額回報%} > 0 && {超額回報%} < 5", "column_id": "超額回報%"},
     "color": "#80cbc4"},
    {"if": {"filter_query": "{超額回報%} <= 0", "column_id": "超額回報%"},
     "color": "#ef5350"},
]

_COLS = [
    {"name": "代碼",     "id": "代碼"},
    {"name": "現價",     "id": "現價"},
    {"name": "股票升幅%", "id": "股票升幅%"},
    {"name": "恒指升幅%", "id": "恒指升幅%"},
    {"name": "超額回報%", "id": "超額回報%"},
]


# ── 計算核心 ──────────────────────────────────────────────────────────
def _period_return(df, n_days: int):
    """n_days 個交易日前到今天的回報率（%），數據不足返回 None。"""
    if len(df) < n_days + 1:
        return None
    close_now = float(df["Close"].iloc[-1])
    close_ago = float(df["Close"].iloc[-1 - n_days])
    if close_ago == 0:
        return None
    return (close_now / close_ago - 1) * 100


def _scan(period: str) -> tuple[float | None, str, list]:
    """Returns (hsi_return, status_text, rows)"""
    n_days = PERIOD_DAYS[period]
    lbl    = PERIOD_LABEL[period]

    # 恒指回報
    raw_hsi = get_stock_data("^HSI", "1y")
    if raw_hsi.empty:
        return None, "❌ 無法獲取恒指數據", []
    hsi_df  = calculate_indicators(raw_hsi)
    hsi_ret = _period_return(hsi_df, n_days)
    if hsi_ret is None:
        return None, f"❌ 恒指數據不足（需至少 {n_days+1} 根K線）", []

    tickers = load_stocks()
    results, errors = [], 0

    for ticker in tickers:
        try:
            df = get_cached(ticker, "1y")
            if df.empty or len(df) < n_days + 1:
                continue
            stock_ret = _period_return(df, n_days)
            if stock_ret is None:
                continue
            excess = stock_ret - hsi_ret
            if excess <= 0:
                continue     # 只保留跑贏大市的個股
            results.append({
                "代碼":     ticker,
                "現價":     round(float(df["Close"].iloc[-1]), 2),
                "股票升幅%": round(stock_ret, 2),
                "恒指升幅%": round(hsi_ret,   2),
                "超額回報%": round(excess,     2),
            })
        except Exception:
            errors += 1

    results.sort(key=lambda x: x["超額回報%"], reverse=True)

    n_total  = len(tickers)
    n_win    = len(results)
    err_note = f"，{errors} 隻略過（下載失敗）" if errors else ""
    sign     = "+" if hsi_ret >= 0 else ""
    status   = (
        f"恒指 {lbl} 回報：{sign}{hsi_ret:.2f}%"
        f"  |  {n_total} 隻中跑贏 {n_win} 隻{err_note}"
    )
    return hsi_ret, status, results


# ── Layout ───────────────────────────────────────────────────────────
layout = html.Div([
    html.H4("🏆 跑贏大市", className="mb-3"),

    dbc.Row([
        dbc.Col(
            dbc.RadioItems(
                id="beat-period",
                options=PERIOD_OPTIONS,
                value="1mo",
                inline=True,
                className="pt-1",
            ),
            md=7, sm=12, className="mb-2",
        ),
        dbc.Col(
            dbc.Button("🏆 開始計算", id="beat-btn",
                       color="warning", size="sm", className="w-100"),
            md=2, sm=6, className="mb-2",
        ),
    ], align="center", className="mb-3"),

    html.Small(id="beat-status", className="text-muted d-block mb-2"),

    html.Div(id="beat-hsi-banner", className="mb-3"),

    dcc.Loading(type="circle", color="#f9a825", children=[
        html.Div(id="beat-result"),
    ]),
], className="p-3")


# ── Callback ─────────────────────────────────────────────────────────
@callback(
    Output("beat-status",     "children"),
    Output("beat-hsi-banner", "children"),
    Output("beat-result",     "children"),
    Input("beat-btn",         "n_clicks"),
    State("beat-period",      "value"),
    prevent_initial_call=True,
)
def cb_run_beat(n_clicks, period):
    hsi_ret, status, rows = _scan(period)

    # 恒指橫幅
    if hsi_ret is not None:
        hsi_color = "success" if hsi_ret >= 0 else "danger"
        sign      = "+" if hsi_ret >= 0 else ""
        banner    = dbc.Alert(
            [
                html.Strong(f"恒生指數 {PERIOD_LABEL[period]} 回報："),
                html.Span(f"{sign}{hsi_ret:.2f}%",
                          style={"fontSize": "1.2rem", "fontWeight": "bold"}),
                html.Span(f"  ·  共 {len(rows)} 隻個股跑贏大市",
                          className="ms-3 small"),
            ],
            color=hsi_color,
            className="py-2",
        )
    else:
        banner = []

    if not rows:
        return status, banner, html.Small("無個股跑贏大市", className="text-muted")

    table = dash_table.DataTable(
        columns=_COLS,
        data=rows,
        sort_action="native",
        page_action="none",
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
    )
    return status, banner, table

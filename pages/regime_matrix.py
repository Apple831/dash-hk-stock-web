import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd

from data import get_stock_data, load_stocks, batch_download
from indicators import calculate_indicators
from walk_forward import run_portfolio_walk_forward
from config import ACTIVE_PRESETS, STRATEGY_PRESETS
from regime import detect_regime

dash.register_page(__name__, path="/regime-matrix", name="制度矩陣")

# ── Constants ─────────────────────────────────────────────────────
ACTIVE_NAMES       = list(ACTIVE_PRESETS.keys())
ALL_STRATEGY_OPTS  = [{"label": n, "value": n} for n in STRATEGY_PRESETS]
REGIMES = ["強牛市", "弱牛市", "牛市警惕", "熊市觀察", "弱熊市", "強熊市", "震盪市", "轉折期"]
REG_IDS = {r: f"r{i+1}" for i, r in enumerate(REGIMES)}
REG_HIDDEN = {r: f"_h{i+1}" for i, r in enumerate(REGIMES)}
REGIME_DISPLAY = {
    "強牛市":  "🟢 強牛市",
    "弱牛市":  "🟢 弱牛市",
    "牛市警惕": "⚠️ 牛市警惕",
    "熊市觀察": "⚠️ 熊市觀察",
    "弱熊市":  "🔴 弱熊市",
    "強熊市":  "🔴 強熊市",
    "震盪市":  "🟡 震盪市",
    "轉折期":  "🔵 轉折期",
}

# yfinance only supports 5y / 10y (not "3y") so map accordingly
YF_PERIOD = {"3y": "5y", "5y": "5y", "10y": "10y"}
TRIM_DAYS = {"3y": 756,  "5y": None, "10y": None}

PERIOD_OPTIONS = [
    {"label": "3年", "value": "3y"},
    {"label": "5年", "value": "5y"},
    {"label": "10年", "value": "10y"},
]

_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_CELL = {"textAlign": "center", "padding": "6px 14px",
          "fontFamily": "monospace", "fontSize": "0.83rem", "whiteSpace": "pre-line"}

_CELL_LEFT = {**_CELL, "textAlign": "left"}


# ══════════════════════════════════════════════════════════════════
# Regime helpers
# ══════════════════════════════════════════════════════════════════

def _fold_regime(hsi_df: pd.DataFrame, oos_start_date) -> str:
    if hsi_df is None or hsi_df.empty:
        return "震盪市"
    idx      = hsi_df.index.searchsorted(oos_start_date)
    idx      = min(max(0, idx), len(hsi_df) - 1)
    slice_df = hsi_df.iloc[: idx + 1]
    label    = detect_regime(slice_df)["label"]
    return label if label in REGIMES else "震盪市"


def _aggregate_by_regime(wf_results: list, hsi_df: pd.DataFrame) -> dict:
    """Aggregates OOS trades by regime at each trade's buy date (trade-level tagging)."""
    acc = {r: {"rets": [], "wins": [], "fold_set": set()} for r in REGIMES}

    for fold in wf_results:
        if not fold.get("valid_oos", False):
            continue
        fold_n = fold.get("fold", 0)
        for trade in fold.get("oos_trades", []):
            buy_date = trade.get("_buy_date")
            if buy_date is None:
                continue
            regime = _fold_regime(hsi_df, buy_date)
            ret    = float(trade.get("回報%", 0.0))
            acc[regime]["rets"].append(ret)
            acc[regime]["wins"].append(1 if ret > 0 else 0)
            acc[regime]["fold_set"].add(fold_n)

    out = {}
    for r in REGIMES:
        d = acc[r]
        if d["rets"]:
            out[r] = {
                "avg_ret":  round(sum(d["rets"]) / len(d["rets"]), 2),
                "win_rate": round(sum(d["wins"]) / len(d["wins"]) * 100, 1),
                "n":        len(d["rets"]),
                "folds":    len(d["fold_set"]),
            }
        else:
            out[r] = None
    return out


def _fmt_cell(m) -> str:
    if m is None:
        return "—"
    sign = "+" if m["avg_ret"] > 0 else ""
    return f"{sign}{m['avg_ret']:.2f}%\n({m['n']}筆 {m['win_rate']:.0f}%)"


# ══════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════

def _load_data(period_val: str) -> tuple:
    """Returns (stock_data, hsi_df)."""
    yf_p = YF_PERIOD[period_val]
    trim = TRIM_DAYS[period_val]

    hsi_raw = get_stock_data("^HSI", yf_p)
    hsi_df  = calculate_indicators(hsi_raw) if not hsi_raw.empty else pd.DataFrame()
    if trim and not hsi_df.empty:
        hsi_df = hsi_df.iloc[-trim:]

    tickers  = load_stocks()
    raw_data = batch_download(tickers, yf_p)          # already has indicators via batch_download

    if trim:
        stock_data = {}
        for t, df in raw_data.items():
            trimmed = df.iloc[-trim:]
            if len(trimmed) >= 62:
                stock_data[t] = trimmed
    else:
        stock_data = {t: df for t, df in raw_data.items() if len(df) >= 62}

    return stock_data, hsi_df


# ══════════════════════════════════════════════════════════════════
# Strategy runner
# ══════════════════════════════════════════════════════════════════

def _run_strategy(name, preset, stock_data, hsi_df, is_mo, oos_mo, trade_size, slippage, min_oos):
    kw = {"min_oos_trades": min_oos}
    if preset.get("min_hold_days") is not None: kw["min_hold_days"] = preset["min_hold_days"]
    if preset.get("cooldown_days")  is not None: kw["cooldown_days"]  = preset["cooldown_days"]
    try:
        results = run_portfolio_walk_forward(
            stock_data, preset["buy"], preset["sell"],
            is_months=is_mo, oos_months=oos_mo,
            trade_size=trade_size, slippage=slippage,
            **kw,
        )
    except Exception:
        results = []
    return _aggregate_by_regime(results, hsi_df)


# ══════════════════════════════════════════════════════════════════
# Matrix table builder
# ══════════════════════════════════════════════════════════════════

def _build_matrix_table(srm: dict):
    """srm = {strategy_name: {regime_label: metrics_or_None}}"""
    columns = [{"name": "策略", "id": "策略", "type": "text"}]
    for r in REGIMES:
        columns.append({"name": REGIME_DISPLAY[r], "id": REG_IDS[r], "type": "text"})

    rows   = []
    styles = []

    for i, (name, rd) in enumerate(srm.items()):
        row = {"策略": name}
        for r in REGIMES:
            rid  = REG_IDS[r]
            hid  = REG_HIDDEN[r]
            m    = rd.get(r)
            val  = (m or {}).get("avg_ret")
            row[rid] = _fmt_cell(m)
            row[hid] = val
            if val is not None:
                clr_bg = "#0d2b0d" if val > 0 else "#2b0d0d"
                clr_fg = "#6fcf6f" if val > 0 else "#cf6f6f"
                styles.append({"if": {"row_index": i, "column_id": rid},
                                "backgroundColor": clr_bg, "color": clr_fg})
        rows.append(row)

    return columns, rows, styles


def _build_summary_table(srm: dict):
    """Best strategy per regime."""
    best = {}
    for name, rd in srm.items():
        for regime in REGIMES:
            m = rd.get(regime)
            if m is None:
                continue
            if regime not in best or m["avg_ret"] > best[regime]["avg_ret"]:
                best[regime] = {"策略": name, **m}

    if not best:
        return [], []

    columns = [
        {"name": "制度",     "id": "制度"},
        {"name": "最佳策略", "id": "策略"},
        {"name": "均回報%",  "id": "ret"},
        {"name": "勝率%",    "id": "wr"},
        {"name": "OOS交易數","id": "n"},
        {"name": "涉及Fold", "id": "folds"},
    ]
    rows = []
    for regime in REGIMES:
        if regime not in best:
            continue
        b    = best[regime]
        sign = "+" if b["avg_ret"] > 0 else ""
        rows.append({
            "制度":  REGIME_DISPLAY.get(regime, regime),
            "策略":  b["策略"],
            "ret":   f"{sign}{b['avg_ret']:.2f}%",
            "wr":    f"{b['win_rate']:.1f}%",
            "n":     b["n"],
            "folds": b["folds"],
        })
    return columns, rows


# ══════════════════════════════════════════════════════════════════
# Custom strategy bar chart
# ══════════════════════════════════════════════════════════════════

def _build_custom_chart(strategy_name: str, rd: dict) -> go.Figure:
    x, y, colors, texts = [], [], [], []
    for regime in REGIMES:
        m = rd.get(regime)
        x.append(REGIME_DISPLAY.get(regime, regime))
        if m is None:
            y.append(0); colors.append("#555"); texts.append("無數據")
        else:
            y.append(m["avg_ret"])
            colors.append("#27ae60" if m["avg_ret"] >= 0 else "#c0392b")
            sign = "+" if m["avg_ret"] > 0 else ""
            texts.append(f"{sign}{m['avg_ret']:.2f}%<br>{m['n']}筆 {m['win_rate']:.0f}%")

    fig = go.Figure(go.Bar(
        x=x, y=y, marker_color=colors,
        text=texts, textposition="outside",
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#888", line_width=1)
    fig.update_layout(
        title=f"{strategy_name} — 各制度 OOS 均回報%",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,20,20,0.6)",
        font_color="#ddd",
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="#333", zeroline=False, ticksuffix="%"),
        height=400, margin=dict(t=60, b=40),
    )
    return fig


# ══════════════════════════════════════════════════════════════════
# Layout
# ══════════════════════════════════════════════════════════════════

def _params_row():
    return dbc.Row([
        dbc.Col([
            dbc.Label("總數據週期", className="small"),
            dbc.Select(id="rm-period", options=PERIOD_OPTIONS, value="3y"),
        ], xs=6, md=2),
        dbc.Col([
            dbc.Label("IS 窗口（月）", className="small"),
            dbc.Input(id="rm-is-mo",  type="number", value=12, min=6,  max=36, step=1),
        ], xs=6, md=2),
        dbc.Col([
            dbc.Label("OOS 窗口（月）", className="small"),
            dbc.Input(id="rm-oos-mo", type="number", value=6,  min=3,  max=24, step=1),
        ], xs=6, md=2),
        dbc.Col([
            dbc.Label("每筆金額", className="small"),
            dbc.Input(id="rm-trade-size", type="number", value=100000, min=10000, step=10000),
        ], xs=6, md=2),
        dbc.Col([
            dbc.Label("純滑點%", className="small"),
            dbc.Input(id="rm-slippage", type="number", value=0.10, min=0, max=2, step=0.01),
        ], xs=6, md=2),
        dbc.Col([
            dbc.Label("最低有效OOS交易數", className="small"),
            dbc.Input(id="rm-min-oos", type="number", value=5, min=1, max=20, step=1),
        ], xs=6, md=2),
    ], className="mb-3 g-2")


layout = dbc.Container([
    html.H4("🗺️ 制度矩陣", className="mb-3 mt-2"),

    # Mode
    dbc.Row([
        dbc.Col([
            dbc.RadioItems(
                id="rm-mode",
                options=[
                    {"label": "📊 全預設策略矩陣", "value": "matrix"},
                    {"label": "✏️ 自定義策略",      "value": "custom"},
                ],
                value="matrix",
                inline=True,
                inputClassName="me-1",
                labelClassName="me-4",
            ),
        ]),
    ], className="mb-3"),

    _params_row(),

    # Custom strategy row (toggled by callback)
    dbc.Row([
        dbc.Col([
            dbc.Label("策略選擇", className="small"),
            dbc.Select(
                id="rm-strategy",
                options=ALL_STRATEGY_OPTS,
                value=list(STRATEGY_PRESETS.keys())[0],
            ),
        ], md=8),
    ], id="rm-custom-row", className="mb-3", style={"display": "none"}),

    # Run button
    dbc.Row([
        dbc.Col([
            dbc.Button("🚀 開始跑全部策略", id="rm-run-btn", color="primary", n_clicks=0),
            html.Small(
                " ⚠️ 全矩陣模式需下載數據並跑多策略，可能需要幾分鐘",
                className="text-muted ms-2",
                id="rm-run-hint",
            ),
        ]),
    ], className="mb-4"),

    # Result
    dcc.Loading(
        id="rm-loading",
        type="circle",
        children=html.Div(id="rm-result"),
    ),
], fluid=True, className="px-3 py-3")


# ══════════════════════════════════════════════════════════════════
# Callbacks
# ══════════════════════════════════════════════════════════════════

@callback(
    Output("rm-custom-row", "style"),
    Output("rm-run-btn",    "children"),
    Output("rm-run-hint",   "children"),
    Input("rm-mode", "value"),
)
def cb_mode_switch(mode):
    if mode == "custom":
        return (
            {"display": "block"},
            "🚀 開始測試",
            " ⚠️ 自定義模式：跑單策略投資組合 WF",
        )
    return (
        {"display": "none"},
        "🚀 開始跑全部策略",
        " ⚠️ 全矩陣模式需下載數據並跑多策略，可能需要幾分鐘",
    )


@callback(
    Output("rm-result", "children"),
    Input("rm-run-btn", "n_clicks"),
    State("rm-mode",       "value"),
    State("rm-period",     "value"),
    State("rm-is-mo",      "value"),
    State("rm-oos-mo",     "value"),
    State("rm-trade-size", "value"),
    State("rm-slippage",   "value"),
    State("rm-min-oos",    "value"),
    State("rm-strategy",   "value"),
    prevent_initial_call=True,
)
def cb_run(n_clicks, mode, period, is_mo, oos_mo, trade_size, slippage_ui, min_oos, strategy):
    is_mo      = int(is_mo      or 12)
    oos_mo     = int(oos_mo     or 6)
    trade_size = float(trade_size or 100000)
    slippage   = float(slippage_ui or 0.10) / 100
    min_oos    = int(min_oos    or 5)

    # ── Load data ─────────────────────────────────────────────────
    try:
        stock_data, hsi_df = _load_data(period or "3y")
    except Exception as e:
        return dbc.Alert(f"❌ 數據加載失敗：{e}", color="danger")

    if len(stock_data) < 5:
        return dbc.Alert(
            f"❌ 有效股票數據不足（取得 {len(stock_data)} 隻），請先下載數據或換較短週期。",
            color="danger",
        )

    # ── Full matrix mode ──────────────────────────────────────────
    if mode == "matrix":
        srm = {}
        for name in ACTIVE_NAMES:
            preset = ACTIVE_PRESETS[name]
            srm[name] = _run_strategy(
                name, preset, stock_data, hsi_df,
                is_mo, oos_mo, trade_size, slippage, min_oos,
            )

        if not any(any(v is not None for v in rd.values()) for rd in srm.values()):
            return dbc.Alert("❌ 所有策略均無有效 Fold，請嘗試延長週期或縮短 IS/OOS 窗口。", color="danger")

        mat_cols, mat_rows, mat_styles = _build_matrix_table(srm)
        sum_cols, sum_rows             = _build_summary_table(srm)

        # Count how many folds total
        n_stocks = len(stock_data)
        n_strats = len(ACTIVE_NAMES)

        header = dbc.Alert(
            f"✅ 完成｜{n_strats} 策略 × {n_stocks} 股 × 多制度  "
            f"（格式：均回報% / 交易數 / 勝率%，逐筆交易按入場日制度分類）",
            color="success", className="mb-3",
        )

        matrix_table = dash_table.DataTable(
            columns=mat_cols,
            data=mat_rows,
            style_header=_HDR,
            style_data=_DAT,
            style_cell=_CELL,
            style_cell_conditional=[
                {"if": {"column_id": "策略"}, **_CELL_LEFT, "minWidth": "260px", "maxWidth": "360px"},
                *[{"if": {"column_id": REG_IDS[r]}, "minWidth": "115px"} for r in REGIMES],
            ],
            style_data_conditional=mat_styles,
            style_as_list_view=False,
            page_action="none",
            id="rm-matrix-table",
        )

        summary_section = []
        if sum_rows:
            summary_section = [
                html.H6("🏆 各制度最佳策略", className="mt-4 mb-2"),
                dash_table.DataTable(
                    columns=sum_cols,
                    data=sum_rows,
                    style_header=_HDR,
                    style_data=_DAT,
                    style_cell={**_CELL, "textAlign": "left"},
                    style_data_conditional=[
                        {"if": {"column_id": "ret", "filter_query": '{ret} contains "+"'},
                         "color": "#6fcf6f"},
                        {"if": {"column_id": "ret", "filter_query": '{ret} contains "-"'},
                         "color": "#cf6f6f"},
                    ],
                    style_as_list_view=False,
                    page_action="none",
                ),
            ]

        return [header, html.H6("📊 策略 × 制度 矩陣", className="mb-2"),
                matrix_table, *summary_section]

    # ── Custom strategy mode ──────────────────────────────────────
    preset = STRATEGY_PRESETS.get(strategy)
    if preset is None:
        return dbc.Alert("❌ 找不到所選策略。", color="danger")

    rd = _run_strategy(
        strategy, preset, stock_data, hsi_df,
        is_mo, oos_mo, trade_size, slippage, min_oos,
    )

    if all(v is None for v in rd.values()):
        return dbc.Alert("❌ 無有效 OOS Fold，請嘗試延長週期或縮短 IS/OOS 窗口。", color="danger")

    fig = _build_custom_chart(strategy, rd)

    # Detail cards per regime
    def _reg_card(regime):
        m = rd.get(regime)
        if m is None:
            body = html.Div("無數據", className="text-muted small")
        else:
            sign = "+" if m["avg_ret"] > 0 else ""
            color = "#6fcf6f" if m["avg_ret"] >= 0 else "#cf6f6f"
            body = html.Div([
                html.Div(f"{sign}{m['avg_ret']:.2f}%",
                         style={"fontSize": "1.4rem", "fontWeight": "bold", "color": color}),
                html.Small(f"{m['n']} 筆交易 · 勝率 {m['win_rate']:.1f}% · {m['folds']} 個Fold"),
            ])
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(REGIME_DISPLAY.get(regime, regime), className="small text-muted mb-1"),
            body,
        ], className="py-2 px-3")), xs=6, md=3, className="mb-2")

    return [
        dbc.Alert(f"✅ {strategy}  |  {len(stock_data)} 隻股票  |  IS={is_mo}月 OOS={oos_mo}月",
                  color="success", className="mb-3"),
        dbc.Row([_reg_card(r) for r in REGIMES], className="mb-3"),
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
    ]

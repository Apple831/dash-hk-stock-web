import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
from collections import defaultdict

from data import get_stock_data, get_cached, load_stocks
from indicators import calculate_indicators, precompute_signals
from config import STRATEGY_PRESETS, ACTIVE_PRESETS, SELL_LABELS
from regime import detect_regime

dash.register_page(__name__, path="/multi-scan", name="共振掃描")

# ── 制度 → 推薦策略對照表 ─────────────────────────────────────────────
_REGIME_RECS = {
    "🟢 牛市": [
        "⚡ 突破確認",
        "🔄+ MACD+趨勢MIN30",
    ],
    "🟡 震盪市": [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎+ M30 RSI進雙出MIN30",
        "💎M30 純粹均值回歸MIN30",
        "🔄🔄M30 均值回歸長持MIN30",
    ],
    "🔴 熊市": [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎M30 純粹均值回歸MIN30",
    ],
}

# ── Table 樣式（和其他 scan 頁一致）──────────────────────────────────
_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_CELL = {
    "textAlign": "left", "padding": "6px 14px",
    "fontFamily": "monospace", "fontSize": "0.88rem",
}

_BUY_COND = [
    {"if": {"row_index": "odd"},  "backgroundColor": "#1f1f1f"},
    {"if": {"state": "selected"}, "backgroundColor": "rgba(38,166,154,0.25)",
     "border": "1px solid #26a69a"},
    {"if": {"filter_query": "{漲跌%} > 0", "column_id": "漲跌%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{漲跌%} < 0", "column_id": "漲跌%"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{共振數} >= 3", "column_id": "共振數"},
     "color": "#ffd700", "fontWeight": "bold"},
    {"if": {"filter_query": "{共振數} = 2", "column_id": "共振數"},
     "color": "#f9a825", "fontWeight": "bold"},
]

_SELL_COND = [
    {"if": {"row_index": "odd"},  "backgroundColor": "#1f1f1f"},
    {"if": {"state": "selected"}, "backgroundColor": "rgba(239,83,80,0.2)",
     "border": "1px solid #ef5350"},
    {"if": {"filter_query": "{漲跌%} > 0", "column_id": "漲跌%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{漲跌%} < 0", "column_id": "漲跌%"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{訊號數} >= 3", "column_id": "訊號數"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{訊號數} = 2", "column_id": "訊號數"},
     "color": "#f9a825", "fontWeight": "bold"},
    {"if": {"filter_query": "{訊號數} = 0", "column_id": "訊號數"},
     "color": "#555"},
]

_BUY_COLS = [
    {"name": "代碼",    "id": "代碼"},
    {"name": "現價",    "id": "現價"},
    {"name": "漲跌%",   "id": "漲跌%"},
    {"name": "RSI",     "id": "RSI"},
    {"name": "共振數",  "id": "共振數"},
    {"name": "命中策略", "id": "命中策略"},
]

_SELL_COLS = [
    {"name": "代碼",        "id": "代碼"},
    {"name": "現價",        "id": "現價"},
    {"name": "漲跌%",       "id": "漲跌%"},
    {"name": "RSI",         "id": "RSI"},
    {"name": "訊號數",      "id": "訊號數"},
    {"name": "觸發賣出訊號", "id": "觸發賣出訊號"},
]


# ── 恒指制度偵測 ──────────────────────────────────────────────────────
def _detect_regime() -> tuple[str, list]:
    """Returns (bucket_label, card_components) — bucket matches _REGIME_RECS keys."""
    raw = get_stock_data("^HSI", "1y")
    if raw.empty:
        return "🟡 震盪市", [dbc.Alert("⚠️ 無法獲取恒指數據，預設震盪市策略", color="warning")]

    df  = calculate_indicators(raw)
    reg = detect_regime(df)

    pct_color = "#26a69a" if (reg["pct"] or 0) >= 0 else "#ef5350"
    recs      = _REGIME_RECS.get(reg["bucket"], [])

    def _fmt(val, fmt):
        return fmt.format(val) if val is not None else "—"

    card = dbc.Card([
        dbc.CardHeader(html.Strong("🌍 恒生指數 — 當前制度")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.H5(f"{reg['price']:.0f}" if reg["price"] else "—",
                                className="mb-0"), width="auto"),
                dbc.Col(
                    html.Span(_fmt(reg["pct"], "{:+.2f}%"),
                              style={"color": pct_color, "fontWeight": "bold", "fontSize": "1.1rem"}),
                    className="text-end",
                ),
            ], align="center", className="mb-2"),
            dbc.Badge(reg["label"], color=reg["color"], className="fs-6 mb-3 px-3 py-1"),
            dbc.Row([
                dbc.Col([
                    html.Small("📊 制度指標", className="text-muted d-block fw-bold mb-1"),
                    html.Small(f"MA缺口：{_fmt(reg['ma_gap_pct'], '{:+.2f}%')}", className="d-block"),
                    html.Small(f"MACD%：{_fmt(reg['macd_pct'], '{:+.4f}%')}",   className="d-block"),
                    html.Small(f"波動CoV：{_fmt(reg['cov_20'], '{:.2f}%')}",     className="d-block"),
                ], md=5),
                dbc.Col([
                    html.Small("🎯 推薦策略", className="text-muted d-block fw-bold mb-1"),
                    *[html.Small(f"• {r}", className="d-block") for r in recs],
                ], md=7),
            ]),
        ]),
    ], className="mb-3 border-secondary")

    return reg["bucket"], [card]


# ── 買入共振掃描 ──────────────────────────────────────────────────────
def _triggered_recently(sigs: dict, active: list, n_days: int) -> bool:
    """True if ALL active signals fired simultaneously on any bar in the last n_days."""
    n = min(n_days, len(next(iter(sigs.values()))))
    for i in range(1, n + 1):
        if all(bool(sigs[b].iloc[-i]) for b in active):
            return True
    return False


def _resonance_scan(strategy_names: list, lookback_days: int = 1) -> tuple[list, str]:
    tickers = load_stocks()
    results, errors = [], 0

    for ticker in tickers:
        try:
            df = get_cached(ticker, "1y")
            if df.empty or len(df) < 62:
                continue
            sigs = precompute_signals(df)

            hit = []
            for sname in strategy_names:
                preset = STRATEGY_PRESETS.get(sname)
                if not preset:
                    continue
                buy_sigs = preset.get("buy", ())
                active   = [f"b{i+1}" for i, v in enumerate(buy_sigs) if v]
                if active and _triggered_recently(sigs, active, lookback_days):
                    hit.append(sname)

            if not hit:
                continue

            c   = df.iloc[-1]
            p   = df.iloc[-2]
            pct = (float(c["Close"]) / float(p["Close"]) - 1) * 100
            results.append({
                "代碼":    ticker,
                "現價":    round(float(c["Close"]), 2),
                "漲跌%":   round(pct, 2),
                "RSI":     round(float(c["RSI"]), 1),
                "共振數":  len(hit),
                "命中策略": " | ".join(hit),
            })
        except Exception:
            errors += 1

    results.sort(key=lambda x: (-x["共振數"], -x["RSI"]))

    n, total = len(results), len(tickers)
    err_note = f"，{errors} 隻略過" if errors else ""
    status   = (f"✅ 共振掃描完成：{total} 隻中命中 {n} 隻{err_note}"
                if n else f"🔍 無共振：{total} 隻均未命中{err_note}")
    return results, status


def _grouped_result(results: list, total_recs: int) -> list:
    if not results:
        return [html.Small("無符合結果", className="text-muted")]

    groups = defaultdict(list)
    for r in results:
        groups[r["共振數"]].append(r)

    sections = []
    for n in sorted(groups.keys(), reverse=True):
        rows = groups[n]
        if n == total_recs and total_recs > 1:
            icon, title, color = "🔥", f"全策略共振（{n}/{total_recs}）", "#ffd700"
        elif n > 1:
            icon, title, color = "⚡", f"{n}策略共振", "#f9a825"
        else:
            icon, title, color = "✨", "單策略", "#aaa"

        sections.append(html.Div([
            html.H6(f"{icon} {title}（{len(rows)} 隻）",
                    className="mt-3 mb-2", style={"color": color}),
            dash_table.DataTable(
                columns=_BUY_COLS,
                data=rows,
                sort_action="native",
                page_action="none",
                style_header=_HDR,
                style_data=_DAT,
                style_data_conditional=_BUY_COND,
                style_cell=_CELL,
                style_table={"overflowX": "auto"},
            ),
        ]))

    return sections


# ── 持倉賣出警報 ──────────────────────────────────────────────────────
def _parse_tickers(textarea: str) -> list:
    tickers = []
    for line in textarea.split("\n"):
        t = line.strip().upper()
        if not t:
            continue
        if not t.endswith(".HK"):
            if t.isdigit():
                t = f"{int(t):04d}.HK"
        tickers.append(t)
    return tickers


def _sell_alert(tickers: list) -> tuple[list, str]:
    results, errors = [], 0

    for ticker in tickers:
        try:
            df = get_cached(ticker, "1y")
            if df.empty or len(df) < 62:
                errors += 1
                results.append({
                    "代碼": ticker, "現價": "—", "漲跌%": "—",
                    "RSI": "—", "訊號數": 0, "觸發賣出訊號": "❌ 數據不足",
                })
                continue

            sigs      = precompute_signals(df)
            triggered = [
                SELL_LABELS[i]
                for i in range(len(SELL_LABELS))
                if bool(sigs[f"s{i+1}"].iloc[-1])
            ]

            c   = df.iloc[-1]
            p   = df.iloc[-2]
            pct = (float(c["Close"]) / float(p["Close"]) - 1) * 100
            results.append({
                "代碼":       ticker,
                "現價":       round(float(c["Close"]), 2),
                "漲跌%":      round(pct, 2),
                "RSI":        round(float(c["RSI"]), 1),
                "訊號數":     len(triggered),
                "觸發賣出訊號": " | ".join(triggered) if triggered else "—",
            })
        except Exception:
            errors += 1
            results.append({
                "代碼": ticker, "現價": "—", "漲跌%": "—",
                "RSI": "—", "訊號數": 0, "觸發賣出訊號": "❌ 下載失敗",
            })

    results.sort(key=lambda x: (-x["訊號數"] if isinstance(x["訊號數"], int) else 0,
                                 -x["RSI"]    if isinstance(x["RSI"], float)    else 0))

    n_warn = sum(1 for r in results if isinstance(r["訊號數"], int) and r["訊號數"] > 0)
    status = (f"⚠️ {n_warn}/{len(tickers)} 隻持倉觸發賣出訊號"
              if n_warn else f"✅ {len(tickers)} 隻持倉暫無賣出訊號")
    if errors:
        status += f"（{errors} 隻數據異常）"
    return results, status


# ── Layout ───────────────────────────────────────────────────────────
layout = html.Div([
    html.H4("📡 共振掃描", className="mb-3"),

    dbc.RadioItems(
        id="mscan-mode",
        options=[
            {"label": "🟢 買入共振（全市場）", "value": "buy"},
            {"label": "🔴 持倉賣出警報",       "value": "sell"},
        ],
        value="buy",
        inline=True,
        className="mb-3",
    ),

    # ── 買入共振面板 ─────────────────────────────────────────────────
    html.Div(id="mscan-buy-panel", children=[
        html.Div(id="mscan-regime-card"),
        dbc.Row([
            dbc.Col(
                html.Small("📅 訊號回溯交易日：", className="text-muted"),
                width="auto", className="d-flex align-items-center",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="mscan-lookback",
                    options=[
                        {"label": "今日",  "value": 1},
                        {"label": "近3日", "value": 3},
                        {"label": "近5日", "value": 5},
                        {"label": "近10日","value": 10},
                    ],
                    value=1,
                    inline=True,
                    className="small",
                ),
            ),
            dbc.Col(
                dbc.Button("🔍 開始共振掃描", id="mscan-buy-btn",
                           color="success", size="sm"),
                width="auto",
            ),
        ], align="center", className="mb-2 g-2"),
        html.Small(id="mscan-buy-status", className="text-muted d-block mb-2"),
        dcc.Loading(type="circle", color="#26a69a", children=[
            html.Div(id="mscan-buy-result"),
        ]),
    ]),

    # ── 持倉賣出警報面板 ─────────────────────────────────────────────
    html.Div(id="mscan-sell-panel", style={"display": "none"}, children=[
        html.Label("輸入持倉代碼（每行一個，支援 0700.HK 或純數字 700）",
                   className="small text-muted mb-1"),
        dbc.Textarea(
            id="mscan-sell-tickers",
            placeholder="0700.HK\n9988.HK\n3690.HK",
            rows=6,
            className="mb-2",
            style={
                "fontFamily": "monospace", "fontSize": "0.9rem",
                "backgroundColor": "#1e1e1e", "color": "#fff",
                "border": "1px solid #444",
            },
        ),
        dbc.Button("⚠️ 掃描賣出訊號", id="mscan-sell-btn",
                   color="danger", size="sm", className="mb-2"),
        html.Small(id="mscan-sell-status", className="text-muted d-block mb-2"),
        dcc.Loading(type="circle", color="#ef5350", children=[
            html.Div(id="mscan-sell-result"),
        ]),
    ]),

    dcc.Store(id="mscan-regime-store"),
], className="p-3")


# ── CB 1：模式切換 + 制度偵測 ────────────────────────────────────────
@callback(
    Output("mscan-buy-panel",    "style"),
    Output("mscan-sell-panel",   "style"),
    Output("mscan-regime-card",  "children"),
    Output("mscan-regime-store", "data"),
    Input("mscan-mode",          "value"),
)
def cb_switch_mode(mode):
    buy_style  = {} if mode == "buy" else {"display": "none"}
    sell_style = {} if mode == "sell" else {"display": "none"}

    if mode == "buy":
        label, card_children = _detect_regime()
        return buy_style, sell_style, card_children, label

    return buy_style, sell_style, no_update, no_update


# ── CB 2：買入共振掃描 ────────────────────────────────────────────────
@callback(
    Output("mscan-buy-status", "children"),
    Output("mscan-buy-result", "children"),
    Input("mscan-buy-btn",     "n_clicks"),
    State("mscan-regime-store","data"),
    State("mscan-lookback",    "value"),
    prevent_initial_call=True,
)
def cb_buy_scan(n_clicks, regime_label, lookback):
    lookback = int(lookback or 1)
    if not regime_label:
        regime_label, _ = _detect_regime()

    recs = _REGIME_RECS.get(regime_label, list(ACTIVE_PRESETS.keys()))
    if not recs:
        return "⚠️ 無推薦策略", []

    results, status = _resonance_scan(recs, lookback)
    return status, _grouped_result(results, len(recs))


# ── CB 3：持倉賣出警報 ────────────────────────────────────────────────
@callback(
    Output("mscan-sell-status", "children"),
    Output("mscan-sell-result", "children"),
    Input("mscan-sell-btn",     "n_clicks"),
    State("mscan-sell-tickers", "value"),
    prevent_initial_call=True,
)
def cb_sell_alert(n_clicks, textarea):
    if not textarea or not textarea.strip():
        return "⚠️ 請輸入持倉代碼", no_update

    tickers = _parse_tickers(textarea)
    if not tickers:
        return "⚠️ 無有效代碼，請確認格式（如 0700.HK）", no_update

    results, status = _sell_alert(tickers)

    table = dash_table.DataTable(
        columns=_SELL_COLS,
        data=results,
        sort_action="native",
        page_action="none",
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=_SELL_COND,
        style_cell=_CELL,
        style_table={"overflowX": "auto"},
    )
    return status, table

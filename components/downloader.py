"""
批量預下載元件 + TradingView 股票清單更新

Modal 分兩區：
  ① 從 TradingView 更新股票清單（篩選條件 → 寫入 core/stocks.txt）
  ② 批量預下載（讀 stocks.txt → 存 diskcache，進度由 Interval 驅動）
"""
import os
from datetime import datetime

from dash import html, dcc, callback, Output, Input, State, no_update, ctx
import dash_bootstrap_components as dbc

from data import get_stock_data, load_stocks, fetch_stocks_from_tradingview
from indicators import calculate_indicators
import cache_store

BATCH_SIZE  = 3
INTERVAL_MS = 2_000
DISK_TTL    = 86_400   # 24 小時

# stocks.txt 路徑（components/ 的上層是 project root，再進 core/）
_STOCKS_TXT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "core", "stocks.txt",
)


# ── 工具函式 ──────────────────────────────────────────────────────────
def _download_batch(tickers: list, period: str) -> int:
    saved = 0
    for ticker in tickers:
        try:
            raw = get_stock_data(ticker, period)
            if raw.empty or len(raw) < 62:
                continue
            df = calculate_indicators(raw)
            cache_store.dc.set(f"stock_{ticker}_{period}", df, expire=DISK_TTL)
            saved += 1
        except Exception:
            continue
    return saved


def _write_stocks_txt(tickers: list, comment: str) -> None:
    with open(_STOCKS_TXT, "w", encoding="utf-8") as f:
        f.write(f"# {comment}\n")
        for t in tickers:
            f.write(t + "\n")


# ── Layout 元件 ───────────────────────────────────────────────────────
def get_components():
    """回傳需注入 app.layout 的元件列表。"""

    # ── 區塊①：TradingView 篩選器 ─────────────────────────────────
    tv_section = dbc.Card([
        dbc.CardHeader("📡 從 TradingView 更新股票清單", className="py-1 small fw-bold"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("最低市值", className="small text-muted mb-1"),
                    dbc.Select(
                        id="tv-min-cap",
                        options=[
                            {"label": "50 億 HKD",  "value": 5_000_000_000},
                            {"label": "100 億 HKD", "value": 10_000_000_000},
                            {"label": "500 億 HKD", "value": 50_000_000_000},
                        ],
                        value=10_000_000_000,
                        size="sm",
                    ),
                ], width=4),
                dbc.Col([
                    html.Label("最低日均成交額", className="small text-muted mb-1"),
                    dbc.Select(
                        id="tv-min-vol",
                        options=[
                            {"label": "3,000 萬 HKD", "value": 30_000_000},
                            {"label": "5,000 萬 HKD", "value": 50_000_000},
                            {"label": "1 億 HKD",     "value": 100_000_000},
                        ],
                        value=50_000_000,
                        size="sm",
                    ),
                ], width=4),
                dbc.Col([
                    html.Label("最低股價", className="small text-muted mb-1"),
                    dbc.Select(
                        id="tv-min-price",
                        options=[
                            {"label": "2 元 HKD",  "value": 2.0},
                            {"label": "5 元 HKD",  "value": 5.0},
                            {"label": "10 元 HKD", "value": 10.0},
                        ],
                        value=5.0,
                        size="sm",
                    ),
                ], width=4),
            ], className="mb-2"),
            dbc.Button(
                "📡 更新股票清單",
                id="tv-update-btn",
                color="info",
                size="sm",
                className="w-100 mb-2",
            ),
            html.Small(id="tv-update-status", className="text-muted"),
        ], className="py-2"),
    ], className="mb-3 border-info")

    # ── 區塊②：批量下載 ───────────────────────────────────────────
    dl_section = dbc.Card([
        dbc.CardHeader("⬇️ 批量預下載數據", className="py-1 small fw-bold"),
        dbc.CardBody([
            html.Label("下載週期", className="small text-muted mb-1"),
            dbc.RadioItems(
                id="dl-period",
                options=[
                    {"label": "1 年", "value": "1y"},
                    {"label": "2 年", "value": "2y"},
                ],
                value="1y",
                inline=True,
                className="mb-2",
            ),
            dbc.Button(
                "▶ 開始下載",
                id="dl-start-btn",
                color="primary",
                size="sm",
                className="w-100 mb-2",
            ),
            html.Small(id="dl-progress-text", className="text-muted d-block mb-1"),
            dbc.Progress(
                id="dl-bar",
                value=0,
                striped=True,
                animated=True,
                style={"height": "6px"},
            ),
        ], className="py-2"),
    ], className="border-primary")

    modal = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("數據管理")),
            dbc.ModalBody([tv_section, dl_section]),
            dbc.ModalFooter(
                dbc.Button("關閉", id="dl-close-btn", color="secondary", size="sm"),
            ),
        ],
        id="dl-modal",
        is_open=False,
        backdrop="static",
        size="lg",
    )

    return [
        modal,
        dcc.Store(id="dl-store"),
        dcc.Interval(id="dl-interval", interval=INTERVAL_MS, disabled=True),
    ]


# ── CB 1：開關 Modal ─────────────────────────────────────────────────
@callback(
    Output("dl-modal", "is_open"),
    Input("dl-open-btn",  "n_clicks"),
    Input("dl-close-btn", "n_clicks"),
    State("dl-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_modal(n_open, n_close, is_open):
    return not is_open


# ── CB 2：從 TradingView 更新股票清單 ────────────────────────────────
@callback(
    Output("tv-update-status", "children"),
    Input("tv-update-btn",     "n_clicks"),
    State("tv-min-cap",        "value"),
    State("tv-min-vol",        "value"),
    State("tv-min-price",      "value"),
    prevent_initial_call=True,
)
def cb_tv_update(n_clicks, min_cap, min_vol, min_price):
    try:
        tickers = fetch_stocks_from_tradingview(
            min_cap_hkd=int(min_cap),
            min_vol_hkd=int(min_vol),
            min_price_hkd=float(min_price),
        )
    except Exception as e:
        return f"❌ API 請求失敗：{str(e)[:60]}"

    if not tickers:
        return "⚠️ 無符合條件的股票，請放寬篩選條件"

    ts      = datetime.now().strftime("%Y-%m-%d %H:%M")
    comment = (
        f"由 TradingView 自動更新：{ts}｜"
        f"市值≥{int(min_cap)//1_0000_0000}億｜"
        f"成交額≥{int(min_vol)//1_000_000}M｜"
        f"股價≥{float(min_price):.0f}"
    )
    _write_stocks_txt(tickers, comment)
    return f"✅ 已更新：共 {len(tickers)} 隻（{ts}）"


# ── CB 3：開始下載 + Interval tick（合一避免雙 Output 衝突）──────────
@callback(
    Output("dl-store",         "data"),
    Output("dl-progress-text", "children"),
    Output("dl-bar",           "value"),
    Output("dl-bar",           "animated"),
    Output("dl-interval",      "disabled"),
    Input("dl-start-btn",      "n_clicks"),
    Input("dl-interval",       "n_intervals"),
    State("dl-period",         "value"),
    State("dl-store",          "data"),
    prevent_initial_call=True,
)
def download_handler(n_start, n_intervals, period, state):
    trigger = ctx.triggered_id

    if trigger == "dl-start-btn":
        tickers   = load_stocks()   # 讀最新的 stocks.txt
        new_state = {
            "status":  "running",
            "pending": tickers,
            "done":    0,
            "total":   len(tickers),
            "period":  period,
        }
        return new_state, f"準備下載 {len(tickers)} 隻…", 0, True, False

    if trigger == "dl-interval":
        if not state or state.get("status") != "running":
            return no_update, no_update, no_update, no_update, True

        pending = state.get("pending", [])
        if not pending:
            ts    = datetime.now().strftime("%H:%M")
            done  = state["done"]
            total = state["total"]
            return (
                {**state, "status": "done", "pending": [], "ts": ts},
                f"✅ 已緩存 {done}/{total} 隻｜{ts} 完成",
                100, False, True,
            )

        batch     = pending[:BATCH_SIZE]
        remaining = pending[BATCH_SIZE:]
        saved     = _download_batch(batch, state["period"])
        done      = state["done"] + saved
        total     = state["total"]
        pct       = int(done / total * 100) if total > 0 else 0

        return (
            {**state, "pending": remaining, "done": done},
            f"⬇️ {done}/{total}…（本批 {saved}/{len(batch)} 成功）",
            pct, True, False,
        )

    return no_update, no_update, no_update, no_update, no_update


# ── CB 4：Navbar 狀態文字 ─────────────────────────────────────────────
@callback(
    Output("dl-navbar-status", "children"),
    Input("dl-store",          "data"),
)
def update_navbar_status(state):
    if not state:
        return ""
    if state.get("status") == "running":
        return f"⬇️ {state.get('done', 0)}/{state.get('total', 0)}"
    if state.get("status") == "done":
        return f"✅ {state.get('done', 0)} 隻｜{state.get('ts', '')}"
    return ""

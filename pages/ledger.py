"""
pages/ledger.py — 📒 實盤帳本頁

把 scripts/paper_ledger.py 每日寫進 GitHub 的 data/paper_trades.json 在 Dash UI 顯示，
補上 AUDIT-G 🟡-1 缺口：summarize() 的 by_resonance / by_strategy / avg_hold_days 過去算了沒地方看。

讀檔策略（重點）：
  - Render web 服務沒有 GH_TOKEN（只有 daily_scan 的 cron/Actions 環境有），
    所以這裡走 raw.githubusercontent.com（repo 公開時免 token）。
  - repo / 分支用環境變數帶預設值：GH_REPO 預設 Apple831/my-hk-stock-web、GH_BRANCH 預設 main。
  - 讀取失敗（404 / 私有 repo / 網路）只顯示明確訊息，不白畫、不 crash。

彙總邏輯不重造輪子：paper_ledger 在 scripts/（不在 core/），掛上 sys.path 後重用 summarize()。
paper_ledger 只 import os/json/base64/datetime/requests，無 core 依賴，import 安全。
"""
import os
import sys

import dash
from dash import html, dcc, dash_table, callback, Output, Input
import dash_bootstrap_components as dbc
import requests

# ── 重用 scripts/paper_ledger.py 的 summarize（不在 core/，需掛 sys.path）─────────
_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import paper_ledger as pl  # noqa: E402

dash.register_page(__name__, path="/ledger", name="實盤帳本")

# ── raw.githubusercontent 讀檔位置（web 服務無 GH_TOKEN，走公開 raw）──────────────
_GH_REPO   = os.environ.get("GH_REPO", "Apple831/dash-hk-stock-web")
_GH_BRANCH = os.environ.get("GH_BRANCH", "main")
_RAW_URL   = (
    f"https://raw.githubusercontent.com/{_GH_REPO}/{_GH_BRANCH}/{pl.LEDGER_PATH}"
)

# ── Table 樣式（與其他頁一致）────────────────────────────────────────────────
_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
         "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_CELL = {"textAlign": "center", "padding": "6px 14px",
         "fontFamily": "monospace", "fontSize": "0.85rem"}


# ══════════════════════════════════════════════════════════════════
# 讀檔
# ══════════════════════════════════════════════════════════════════
def _load_trades() -> tuple:
    """回 (trades_list, error_msg)。成功 error_msg=None。"""
    try:
        resp = requests.get(_RAW_URL, timeout=15)
        if resp.status_code == 404:
            return [], (
                f"尚無帳本檔（{pl.LEDGER_PATH} 不存在；首次 daily_scan 寫入後才會產生）"
            )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return [], "帳本格式異常（預期 JSON 陣列）"
        return data, None
    except Exception as e:
        return [], (
            f"讀取失敗（{type(e).__name__}）：{e}。"
            f"若 repo 為私有，raw 連結需 token——請設 GH_REPO/GH_BRANCH 或改公開。"
        )


# ══════════════════════════════════════════════════════════════════
# UI 元件
# ══════════════════════════════════════════════════════════════════
def _metric_card(label: str, value: str, color: str = "white"):
    return dbc.Col(
        dbc.Card(dbc.CardBody([
            html.Div(label, className="small text-muted mb-1"),
            html.Div(value, className="fw-bold",
                     style={"color": color, "fontSize": "1.05rem"}),
        ], className="py-2 px-3"), className="h-100"),
        xs=6, md=2,
    )


def _summary_cards(s: dict) -> list:
    total   = s["total_return_pct"]
    avg_ret = s["avg_return_pct"]
    cards = dbc.Row([
        _metric_card("已平倉筆數", str(s["closed_n"])),
        _metric_card("累計總回報%", f"{'+' if total >= 0 else ''}{total}%",
                     "#26a69a" if total >= 0 else "#ef5350"),
        _metric_card("勝率%", f"{s['win_rate']}%",
                     "#26a69a" if s["win_rate"] >= 50 else "#ef5350"),
        _metric_card("平均每筆%", f"{'+' if avg_ret >= 0 else ''}{avg_ret}%",
                     "#26a69a" if avg_ret >= 0 else "#ef5350"),
        _metric_card("平均持倉天", f"{s['avg_hold_days']}"),
        _metric_card("持倉中 / 待成交",
                     f"{s['open_n']} / {s['pending_n']}"),
    ], className="mb-3 g-2")
    return cards


def _group_table(group: dict, key_name: str, key_label: str, sort_numeric: bool):
    """把 summarize 的 by_resonance / by_strategy dict 攤成 DataTable。"""
    if not group:
        return html.Small("（尚無已平倉資料）", className="text-muted d-block mb-3")

    keys = list(group.keys())
    if sort_numeric:
        keys.sort(key=lambda k: (k is None, k))
    else:
        keys.sort(key=lambda k: -group[k]["n"])

    rows = []
    for k in keys:
        m = group[k]
        avg = m["avg_ret"]
        rows.append({
            key_name: "—" if k is None else str(k),
            "n": m["n"],
            "wr": f"{m['win_rate']}%",
            "avg": f"{'+' if avg >= 0 else ''}{avg}%",
        })

    cond = [
        {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
        {"if": {"filter_query": '{avg} contains "+"', "column_id": "avg"},
         "color": "#26a69a", "fontWeight": "bold"},
        {"if": {"filter_query": '{avg} contains "-"', "column_id": "avg"},
         "color": "#ef5350", "fontWeight": "bold"},
    ]
    return dash_table.DataTable(
        columns=[
            {"name": key_label,   "id": key_name},
            {"name": "已平倉筆數", "id": "n"},
            {"name": "勝率%",     "id": "wr"},
            {"name": "平均每筆%", "id": "avg"},
        ],
        data=rows,
        sort_action="native",
        page_action="none",
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=cond,
        style_cell={**_CELL, "textAlign": "left"},
        style_table={"overflowX": "auto", "maxWidth": "640px"},
    )


_TRADE_COLS = [
    {"name": "代碼",     "id": "ticker"},
    {"name": "策略",     "id": "strategy"},
    {"name": "狀態",     "id": "status_disp"},
    {"name": "共振",     "id": "resonance_n"},
    {"name": "訊號日",   "id": "signal_date"},
    {"name": "進場日",   "id": "entry_date"},
    {"name": "進場價",   "id": "entry_px"},
    {"name": "出場日",   "id": "exit_date"},
    {"name": "出場價",   "id": "exit_px"},
    {"name": "回報%",    "id": "return_pct"},
    {"name": "持倉bar",  "id": "hold_bars"},
    {"name": "出場原因", "id": "exit_reason"},
]

_STATUS_DISP = {
    "closed":       "✅ 已平倉",
    "open":         "🟢 持倉中",
    "pending_buy":  "⏳ 待成交",
    "pending_sell": "⏳ 待平倉",
}

# 狀態排序：持倉中 / 待成交 / 待平倉 在前（最需要關注），已平倉在後
_STATUS_ORDER = {"open": 0, "pending_sell": 1, "pending_buy": 2, "closed": 3}


def _trade_table(trades: list):
    rows = []
    for t in trades:
        rows.append({
            "ticker":      t.get("ticker", ""),
            "strategy":    t.get("strategy", ""),
            "status_disp": _STATUS_DISP.get(t.get("status"), t.get("status", "")),
            "resonance_n": t.get("resonance_n", ""),
            "signal_date": t.get("signal_date") or "—",
            "entry_date":  t.get("entry_date") or "—",
            "entry_px":    t.get("entry_px") if t.get("entry_px") is not None else "—",
            "exit_date":   t.get("exit_date") or "—",
            "exit_px":     t.get("exit_px") if t.get("exit_px") is not None else "—",
            "return_pct":  t.get("return_pct") if t.get("return_pct") is not None else "—",
            "hold_bars":   t.get("hold_bars") if t.get("hold_bars") is not None else "—",
            "exit_reason": t.get("exit_reason") or "—",
            "_order":      _STATUS_ORDER.get(t.get("status"), 9),
        })
    rows.sort(key=lambda r: (r["_order"], str(r["signal_date"])), reverse=False)
    data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]

    cond = [
        {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
        {"if": {"filter_query": "{return_pct} > 0", "column_id": "return_pct"},
         "color": "#26a69a", "fontWeight": "bold"},
        {"if": {"filter_query": "{return_pct} < 0", "column_id": "return_pct"},
         "color": "#ef5350", "fontWeight": "bold"},
    ]
    return dash_table.DataTable(
        columns=_TRADE_COLS,
        data=data,
        sort_action="native",
        page_size=40,
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=cond,
        style_cell={**_CELL, "textAlign": "left"},
        style_table={"overflowX": "auto"},
    )


# ══════════════════════════════════════════════════════════════════
# Layout
# ══════════════════════════════════════════════════════════════════
layout = html.Div([
    dbc.Row([
        dbc.Col(html.H4("📒 實盤帳本", className="mb-0"), width="auto"),
        dbc.Col(
            dbc.Button("🔄 重新載入", id="ledger-refresh",
                       color="primary", size="sm"),
            width="auto",
        ),
    ], align="center", className="mb-2 g-2"),

    html.Small(
        f"資料來源：{_GH_REPO}@{_GH_BRANCH} 的 {pl.LEDGER_PATH}"
        "（raw.githubusercontent；每日 daily_scan 收盤後更新，raw CDN 可能延遲數分鐘）",
        className="text-muted d-block mb-2",
        style={"fontSize": "0.78rem"},
    ),

    html.Small(
        "ℹ️ 帳本口徑與 WF OOS 對齊：單邊成本 0.0023、T+1 進出、s2 布林上軌出場、MIN5、"
        "固定倉位非複利。數字可直接與 Walk-Forward 的 OOS 對照。",
        className="text-muted d-block mb-3",
        style={"fontSize": "0.78rem"},
    ),

    # 自動載入一次 + 手動刷新
    dcc.Interval(id="ledger-init", interval=300, max_intervals=1),
    html.Div(id="ledger-status", className="mb-2"),

    dcc.Loading(type="circle", color="#26a69a", children=[
        html.Div(id="ledger-body"),
    ]),
], className="p-3")


# ══════════════════════════════════════════════════════════════════
# Callback：載入 / 刷新
# ══════════════════════════════════════════════════════════════════
@callback(
    Output("ledger-status", "children"),
    Output("ledger-body",   "children"),
    Input("ledger-refresh", "n_clicks"),
    Input("ledger-init",    "n_intervals"),
)
def cb_load_ledger(_n_clicks, _n_init):
    trades, err = _load_trades()

    if err:
        return dbc.Alert(f"⚠️ {err}", color="warning", className="py-2 mb-0"), []

    if not trades:
        return (
            dbc.Alert("帳本為空，尚無任何交易紀錄。", color="secondary",
                      className="py-2 mb-0"),
            [],
        )

    s = pl.summarize(trades)

    status = dbc.Alert(
        f"✅ 已載入 {len(trades)} 筆紀錄"
        f"（已平倉 {s['closed_n']}｜持倉中 {s['open_n']}｜待處理 {s['pending_n']}）",
        color="success", className="py-2 mb-2",
    )

    body = [
        _summary_cards(s),
        dbc.Row([
            dbc.Col([
                html.H6("🎯 共振數 → 勝率（by_resonance）", className="mb-2"),
                html.Small(
                    "驗證「共振越多、勝率越高？」——這是當初記 resonance_n 的本意。",
                    className="text-muted d-block mb-2",
                    style={"fontSize": "0.78rem"},
                ),
                _group_table(s["by_resonance"], "key", "共振數",
                             sort_numeric=True),
            ], md=6),
            dbc.Col([
                html.H6("📊 各策略表現（by_strategy）", className="mb-2"),
                html.Small(
                    "每支 💎 策略的實盤已平倉表現，可與該策略 WF OOS 對照。",
                    className="text-muted d-block mb-2",
                    style={"fontSize": "0.78rem"},
                ),
                _group_table(s["by_strategy"], "key", "策略",
                             sort_numeric=False),
            ], md=6),
        ], className="mb-3"),
        html.H6("📋 逐筆交易（持倉/待處理在前，已平倉在後）", className="mb-2"),
        _trade_table(trades),
    ]
    return status, body
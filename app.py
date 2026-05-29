import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Output, Input

from components import downloader   # 注冊 callbacks
from data import get_cached
from regime import regime_history
from config import REGIME_HISTORY_BARS

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.DARKLY],
)

navbar = dbc.NavbarSimple(
    brand="🏹 港股狙擊手 V22.1",
    brand_href="/",
    color="dark",
    dark=True,
    fluid=True,
    children=[
        dbc.NavItem(dbc.NavLink("🌍 指數",    href="/")),
        dbc.NavItem(dbc.NavLink("🟢 買入掃描", href="/buy-scan")),
        dbc.NavItem(dbc.NavLink("🔴 賣出掃描", href="/sell-scan")),
        dbc.NavItem(dbc.NavLink("🔍 個股分析", href="/analysis")),
        dbc.NavItem(dbc.NavLink("📡 共振掃描", href="/multi-scan")),
        dbc.NavItem(dbc.NavLink("🏆 跑贏大市", href="/beat")),
        dbc.NavItem(dbc.NavLink("📊 回測",    href="/backtest")),
        dbc.NavItem(dbc.NavLink("🔬 Walk-Forward", href="/walkforward")),
        dbc.NavItem(dbc.NavLink("🗺️ 制度矩陣",    href="/regime-matrix")),
        dbc.NavItem(dbc.NavLink("🎲 Monte Carlo",    href="/monte-carlo")),
        # 下載狀態文字（diskcache 準備好後更新）
        dbc.NavItem(
            html.Small(id="dl-navbar-status", className="text-muted me-2 mt-1"),
        ),
        # 下載按鈕
        dbc.NavItem(
            dbc.Button(
                "⬇️ 下載數據",
                id="dl-open-btn",
                color="outline-light",
                size="sm",
                n_clicks=0,
            ),
        ),
    ],
)

app.layout = dbc.Container(
    [
        navbar,
        *downloader.get_components(),   # modal + Store + Interval
        dcc.Interval(id="regime-interval", interval=900_000, n_intervals=0),
        html.Div(id="regime-banner", className="px-3 py-1 border-bottom"),
        dash.page_container,
    ],
    fluid=True,
    className="px-0",
)

server = app.server


_REGIME_COLOR = {
    "強牛市":  "success",
    "弱牛市":  "success",
    "牛市警惕": "warning",
    "熊市觀察": "warning",
    "震盪市":  "warning",
    "轉折期":  "info",
    "弱熊市":  "danger",
    "強熊市":  "danger",
}


@callback(
    Output("regime-banner", "children"),
    Input("regime-interval", "n_intervals"),
)
def update_regime_banner(_):
    try:
        df = get_cached("^HSI", "1y")
        if df.empty:
            raise ValueError("no data")

        # 一次向量化計算最近 120 bar 的制度序列；
        # 當前制度 = hist[-1]，回看找出本段持續長度。
        hist = regime_history(df, n_bars=REGIME_HISTORY_BARS)
        if not hist:
            raise ValueError("insufficient data")

        label = hist[-1]["label"]
        color = _REGIME_COLOR.get(label, "secondary")

        duration = 1
        for i in range(len(hist) - 2, -1, -1):
            if hist[i]["label"] != label:
                break
            duration += 1
        switch_date = hist[-duration]["date"].strftime("%Y-%m-%d")

        parts = [
            html.Small("制度監測（恒指）：", className="text-muted me-1"),
            dbc.Badge(label, color=color, className="me-2"),
            html.Small(f"持續 {duration} 日 | 切換日 {switch_date}", className="text-muted"),
        ]
        if label in ("強熊市", "弱熊市"):
            parts.append(dbc.Badge("⛔ 實盤禁區", color="danger", className="ms-2"))
        elif label == "牛市警惕":
            parts.append(dbc.Badge("⚠️ 警惕", color="warning", text_color="dark", className="ms-2"))
        return parts
    except Exception:
        return html.Small("制度監測：載入中…", className="text-muted")


if __name__ == "__main__":
    app.run(debug=False, threaded=True)

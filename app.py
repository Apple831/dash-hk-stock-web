import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

import dash
import dash_bootstrap_components as dbc
from dash import html

from components import downloader   # 注冊 callbacks

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.DARKLY],
)

navbar = dbc.NavbarSimple(
    brand="🏹 港股狙擊手 V18",
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
        dash.page_container,
    ],
    fluid=True,
    className="px-0",
)

server = app.server

if __name__ == "__main__":
    app.run(debug=False)

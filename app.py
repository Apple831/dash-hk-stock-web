import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

import dash
import dash_bootstrap_components as dbc
from dash import html

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
        dbc.NavItem(dbc.NavLink("🌍 指數",   href="/")),
        dbc.NavItem(dbc.NavLink("🟢 買入掃描", href="/buy-scan")),
        dbc.NavItem(dbc.NavLink("🔴 賣出掃描", href="/sell-scan")),
    ],
)

app.layout = dbc.Container(
    [
        navbar,
        dash.page_container,
    ],
    fluid=True,
    className="px-0",
)

server = app.server

if __name__ == "__main__":
    app.run(debug=False)

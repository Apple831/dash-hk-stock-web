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
    app.run(debug=True)

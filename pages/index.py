import dash
from dash import html

dash.register_page(__name__, path="/", name="指數")

layout = html.H2("🌍 指數 Tab — 施工中", className="text-center mt-5")

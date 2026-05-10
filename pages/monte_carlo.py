# pages/monte_carlo.py
# ══════════════════════════════════════════════════════════════════
# 🎲 Monte Carlo 模擬頁面
#
# 原理：對歷史交易回報進行 Bootstrap 重採樣（有放回），
#       重組成 n_sim 條模擬權益曲線，評估策略的統計穩健性。
# ══════════════════════════════════════════════════════════════════

import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import numpy as np
import pandas as pd

from data import get_cached
from backtest import run_backtest, calc_bt_metrics
from config import STRATEGY_PRESETS, MIN_BARS_FOR_INDICATORS

dash.register_page(__name__, path="/monte-carlo", name="🎲 Monte Carlo")

# ── 常數 ─────────────────────────────────────────────────────────
STRATEGY_OPTIONS  = [{"label": n, "value": n} for n in STRATEGY_PRESETS]
DEFAULT_STRATEGY  = list(STRATEGY_PRESETS.keys())[0]

PERIOD_OPTIONS = [
    {"label": "1年", "value": "1y"},
    {"label": "2年", "value": "2y"},
    {"label": "5年", "value": "5y"},
]

_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
         "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}

# ══════════════════════════════════════════════════════════════════
# UI 工具
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


def _section(title: str, children):
    return html.Div([
        html.H6(title, className="mt-3 mb-2"),
        children,
    ], className="mb-3")


# ══════════════════════════════════════════════════════════════════
# Monte Carlo 核心運算
# ══════════════════════════════════════════════════════════════════
def _run_mc(returns_pct: list, n_sim: int, initial_capital: float) -> np.ndarray:
    """
    Bootstrap 重採樣，返回 shape (n_sim, n_trades+1) 的資金矩陣。
    第 0 列 = initial_capital（起點）。
    """
    arr = np.array(returns_pct, dtype=float) / 100.0
    n   = len(arr)
    # 有放回抽樣：shape (n_sim, n)
    sampled = np.random.choice(arr, size=(n_sim, n), replace=True)
    # 累乘 → 資金增長倍數
    growth = np.cumprod(1.0 + sampled, axis=1)
    # 補上起點 1.0
    starts = np.ones((n_sim, 1))
    return initial_capital * np.hstack([starts, growth])   # (n_sim, n+1)


def _max_drawdown_vec(equity_matrix: np.ndarray) -> np.ndarray:
    """向量化計算每條曲線的最大回撤（%）, shape (n_sim,)"""
    # peak: running max along axis=1
    peak = np.maximum.accumulate(equity_matrix, axis=1)
    dd   = (equity_matrix - peak) / peak          # ≤ 0
    return dd.min(axis=1) * 100                   # most negative per row


def _sharpe_vec(equity_matrix: np.ndarray) -> np.ndarray:
    """每條曲線的簡化 Sharpe（以每筆回報%計）"""
    step_returns = np.diff(equity_matrix, axis=1) / equity_matrix[:, :-1]
    mean_r = step_returns.mean(axis=1)
    std_r  = step_returns.std(axis=1) + 1e-9
    return mean_r / std_r


# ══════════════════════════════════════════════════════════════════
# Layout
# ══════════════════════════════════════════════════════════════════
layout = html.Div([
    html.H4("🎲 Monte Carlo 模擬", className="mb-1"),
    html.P(
        "對歷史交易回報進行 Bootstrap 重採樣，評估策略在不同運氣組合下的統計穩健性。",
        className="text-muted small mb-3",
    ),

    # ── 參數列 ────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("策略", className="small text-muted mb-1 d-block"),
            dcc.Dropdown(
                id="mc-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
            ),
        ], xs=12, md=3, className="mb-2"),

        dbc.Col([
            html.Label("股票代碼", className="small text-muted mb-1 d-block"),
            dbc.Input(id="mc-ticker", value="0700.HK", type="text", size="sm"),
        ], xs=6, md=2, className="mb-2"),

        dbc.Col([
            html.Label("週期", className="small text-muted mb-1 d-block"),
            dcc.Dropdown(
                id="mc-period",
                options=PERIOD_OPTIONS,
                value="2y",
                clearable=False,
            ),
        ], xs=6, md=2, className="mb-2"),

        dbc.Col([
            html.Label("初始資金 (HKD)", className="small text-muted mb-1 d-block"),
            dbc.Input(id="mc-capital", value=100000, type="number",
                      min=10000, step=10000, size="sm"),
        ], xs=6, md=2, className="mb-2"),

        dbc.Col([
            html.Label("純滑點%", className="small text-muted mb-1 d-block"),
            dbc.Input(id="mc-slippage", value=0.10, type="number",
                      min=0, step=0.01, size="sm"),
        ], xs=6, md=1, className="mb-2"),

        dbc.Col([
            html.Label("手續費%（雙邊）", className="small text-muted mb-1 d-block"),
            dbc.Input(id="mc-commission", value=0.26, type="number",
                      min=0, step=0.01, size="sm"),
        ], xs=6, md=1, className="mb-2"),

        dbc.Col([
            html.Label("模擬次數", className="small text-muted mb-1 d-block"),
            dbc.Input(id="mc-nsim", value=1000, type="number",
                      min=100, max=5000, step=100, size="sm"),
        ], xs=6, md=1, className="mb-2"),

        dbc.Col([
            html.Label("\u00a0", className="small text-muted mb-1 d-block"),
            dbc.Button("▶ 執行模擬", id="mc-run-btn",
                       color="success", size="sm", className="w-100"),
        ], xs=6, md=2, className="mb-2"),
    ], className="g-2 mb-3"),

    # ── 狀態列 ────────────────────────────────────────────────────
    html.Div(id="mc-status", className="text-muted small mb-2"),

    # ── 結果區（含 Loading 動畫）─────────────────────────────────
    dcc.Loading(
        type="circle",
        color="#26a69a",
        children=html.Div(id="mc-results"),
    ),

    html.Hr(className="my-4", style={"borderColor": "#333"}),

    # ══════════════════════════════════════════════════════════════
    # 📖 結果判讀手冊（可摺疊）
    # ══════════════════════════════════════════════════════════════
    dbc.Button(
        "📖 結果判讀手冊　▾",
        id="mc-guide-toggle",
        color="secondary",
        outline=True,
        size="sm",
        className="mb-3",
        style={"fontSize": "0.85rem"},
    ),
    dbc.Collapse(
        id="mc-guide-collapse",
        is_open=True,   # 預設展開
        children=dbc.Card(
            dbc.CardBody([

                # ── 破產概率 ──────────────────────────────────────
                html.H6("💀 破產概率（最終資金 < 50%）",
                        className="mt-1 mb-2", style={"color": "#ef5350"}),
                dbc.Table([
                    html.Thead(html.Tr([
                        html.Th("數值"),
                        html.Th("判讀"),
                    ]), style={"backgroundColor": "#1a1a1a"}),
                    html.Tbody([
                        html.Tr([html.Td("< 5%",   style={"color": "#26a69a", "fontWeight": "bold"}),
                                 html.Td("✅ 優秀——策略在絕大多數運氣組合下都能保住資金")]),
                        html.Tr([html.Td("5–15%",  style={"color": "#f9a825", "fontWeight": "bold"}),
                                 html.Td("⚠️ 可接受，但要注意倉位管理")]),
                        html.Tr([html.Td("> 15%",  style={"color": "#ef5350", "fontWeight": "bold"}),
                                 html.Td("🔴 危險——每 6–7 次就可能腰斬，不建議實盤")]),
                    ]),
                ], bordered=True, size="sm", dark=True, className="mb-3"),

                # ── 虧損概率 ──────────────────────────────────────
                html.H6("📉 虧損概率（最終資金 < 初始）",
                        className="mb-2", style={"color": "#f9a825"}),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("數值"), html.Th("判讀")]),
                               style={"backgroundColor": "#1a1a1a"}),
                    html.Tbody([
                        html.Tr([html.Td("< 20%",  style={"color": "#26a69a", "fontWeight": "bold"}),
                                 html.Td("✅ 策略勝算高，80% 的運氣排列都能賺錢")]),
                        html.Tr([html.Td("20–40%", style={"color": "#f9a825", "fontWeight": "bold"}),
                                 html.Td("⚠️ 中性——策略有效但需要耐心等待正回報")]),
                        html.Tr([html.Td("> 40%",  style={"color": "#ef5350", "fontWeight": "bold"}),
                                 html.Td("🔴 邊緣策略，接近擲硬幣，不宜大倉位")]),
                    ]),
                ], bordered=True, size="sm", dark=True, className="mb-3"),

                # ── 中位最終資金 ──────────────────────────────────
                html.H6("⚖️ 中位最終資金（最重要的數字）",
                        className="mb-2", style={"color": "#26a69a"}),
                dbc.Alert([
                    html.Div("代表「一般運氣」下的結果，是評估策略優劣最核心的指標。",
                             className="small mb-2"),
                    html.Div([
                        html.Span("明顯高於初始資金", style={"color": "#26a69a", "fontWeight": "bold"}),
                        html.Span(" → ✅ 策略有正期望值", className="ms-2"),
                    ], className="small mb-1"),
                    html.Div([
                        html.Span("略高於初始資金", style={"color": "#f9a825", "fontWeight": "bold"}),
                        html.Span(" → ⚠️ 策略勉強有效，邊際策略", className="ms-2"),
                    ], className="small mb-1"),
                    html.Div([
                        html.Span("低於初始資金", style={"color": "#ef5350", "fontWeight": "bold"}),
                        html.Span(" → 🔴 即使一般運氣也虧損，策略本身有問題", className="ms-2"),
                    ], className="small"),
                ], color="dark", className="mb-3 py-2 px-3"),

                # ── VaR ───────────────────────────────────────────
                html.H6("🔻 5% VaR（最壞 5% 情境的最終資金）",
                        className="mb-2", style={"color": "#f9a825"}),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("狀況"), html.Th("判讀")]),
                               style={"backgroundColor": "#1a1a1a"}),
                    html.Tbody([
                        html.Tr([html.Td("VaR > 初始 × 70%", style={"color": "#26a69a", "fontWeight": "bold"}),
                                 html.Td("✅ 尾部風險可控，最差情況最多虧 30%")]),
                        html.Tr([html.Td("VaR 在 50–70%",    style={"color": "#f9a825", "fontWeight": "bold"}),
                                 html.Td("⚠️ 尾部風險偏大，考慮縮小倉位")]),
                        html.Tr([html.Td("VaR < 50%",        style={"color": "#ef5350", "fontWeight": "bold"}),
                                 html.Td("🔴 極端情況會觸及破產線，必須加止損")]),
                    ]),
                ], bordered=True, size="sm", dark=True, className="mb-3"),

                # ── 最大回撤 ──────────────────────────────────────
                html.H6("📊 中位最大回撤",
                        className="mb-2", style={"color": "#ef5350"}),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("數值"), html.Th("判讀")]),
                               style={"backgroundColor": "#1a1a1a"}),
                    html.Tbody([
                        html.Tr([html.Td("< 15%",  style={"color": "#26a69a", "fontWeight": "bold"}),
                                 html.Td("✅ 很舒適，心理壓力低，容易持倉")]),
                        html.Tr([html.Td("15–30%", style={"color": "#f9a825", "fontWeight": "bold"}),
                                 html.Td("⚠️ 可接受，實盤時要有心理準備不要底部出場")]),
                        html.Tr([html.Td("> 30%",  style={"color": "#ef5350", "fontWeight": "bold"}),
                                 html.Td("🔴 回撤很大，容易恐慌出場，需要嚴格止損設定")]),
                    ]),
                ], bordered=True, size="sm", dark=True, className="mb-3"),

                # ── 曲線圖解讀 ────────────────────────────────────
                html.H6("📈 模擬曲線圖怎麼看", className="mb-2"),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("觀察"), html.Th("代表意思")]),
                               style={"backgroundColor": "#1a1a1a"}),
                    html.Tbody([
                        html.Tr([html.Td("5%–95% 帶很窄"),  html.Td("✅ 策略結果穩定，不太依賴運氣")]),
                        html.Tr([html.Td("5%–95% 帶很寬"),  html.Td("⚠️ 運氣成分大，結果差異懸殊")]),
                        html.Tr([html.Td("中位數向右上傾"), html.Td("✅ 策略長期有正期望值")]),
                        html.Tr([html.Td("中位數向右下傾"), html.Td("🔴 策略長期虧損，不可用")]),
                        html.Tr([html.Td("大量曲線跌破破產線"), html.Td("🔴 策略存在嚴重尾部風險")]),
                    ]),
                ], bordered=True, size="sm", dark=True, className="mb-3"),

                # ── 百分位表 ──────────────────────────────────────
                html.H6("📋 百分位分析表怎麼看", className="mb-2"),
                dbc.Alert([
                    html.Div("重點看 P25 和 P75，這是「一般偏差運氣」的範圍：", className="small mb-2"),
                    html.Div("P25 仍為正回報 → ✅ 策略非常穩健，偏差運氣也能賺",
                             className="small mb-1", style={"color": "#26a69a"}),
                    html.Div("P50 正但 P25 負 → ⚠️ 策略有效但需要相對好的運氣",
                             className="small mb-1", style={"color": "#f9a825"}),
                    html.Div("P50 都為負 → 🔴 策略根本性有問題",
                             className="small", style={"color": "#ef5350"}),
                ], color="dark", className="mb-3 py-2 px-3"),

                # ── Sharpe ────────────────────────────────────────
                html.H6("🧮 中位 Sharpe", className="mb-2"),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("數值"), html.Th("判讀")]),
                               style={"backgroundColor": "#1a1a1a"}),
                    html.Tbody([
                        html.Tr([html.Td("> 0.5",      style={"color": "#26a69a", "fontWeight": "bold"}),
                                 html.Td("✅ 每單位波動帶來不錯的回報")]),
                        html.Tr([html.Td("0.1 – 0.5",  style={"color": "#f9a825", "fontWeight": "bold"}),
                                 html.Td("⚠️ 可接受")]),
                        html.Tr([html.Td("< 0.1 或負值", style={"color": "#ef5350", "fontWeight": "bold"}),
                                 html.Td("🔴 回報不足以補償波動風險")]),
                    ]),
                ], bordered=True, size="sm", dark=True, className="mb-3"),

                # ── WF 關係說明 ───────────────────────────────────
                html.H6("🔬 Monte Carlo vs Walk-Forward 的關係", className="mb-2"),
                dbc.Alert([
                    html.Div([
                        html.Strong("Walk-Forward"),
                        html.Span("：測試策略在「未見過的真實時間段」是否有效 → 消除過擬合", className="ms-1"),
                    ], className="small mb-1"),
                    html.Div([
                        html.Strong("Monte Carlo"),
                        html.Span("：假設策略有效的前提下，測試「不同運氣排列」的風險分布 → 評估倉位風險", className="ms-1"),
                    ], className="small mb-2"),
                    html.Div(
                        "✅ 正確順序：先用 Walk-Forward 確認有真實 Alpha，再用 Monte Carlo 決定實盤倉位大小。",
                        className="small fw-bold",
                        style={"color": "#26a69a"},
                    ),
                ], color="dark", className="mb-0 py-2 px-3"),

            ], className="py-3 px-4"),
            style={"backgroundColor": "#1e1e1e", "border": "1px solid #333"},
        ),
    ),
], className="p-3")


# ══════════════════════════════════════════════════════════════════
# Callback：判讀手冊摺疊
# ══════════════════════════════════════════════════════════════════
@callback(
    Output("mc-guide-collapse", "is_open"),
    Output("mc-guide-toggle",   "children"),
    Input("mc-guide-toggle",    "n_clicks"),
    State("mc-guide-collapse",  "is_open"),
    prevent_initial_call=True,
)
def toggle_guide(n, is_open):
    new_open = not is_open
    label = "📖 結果判讀手冊　▴" if new_open else "📖 結果判讀手冊　▾"
    return new_open, label


# ══════════════════════════════════════════════════════════════════
# Callback：執行模擬
# ══════════════════════════════════════════════════════════════════
@callback(
    Output("mc-status",  "children"),
    Output("mc-results", "children"),
    Input("mc-run-btn",  "n_clicks"),
    State("mc-strategy", "value"),
    State("mc-ticker",   "value"),
    State("mc-period",   "value"),
    State("mc-capital",  "value"),
    State("mc-slippage",    "value"),
    State("mc-commission",  "value"),
    State("mc-nsim",        "value"),
    prevent_initial_call=True,
)
def run_simulation(_clicks, strategy, ticker, period, capital, slippage, commission, n_sim):

    # ── 參數清理 ──────────────────────────────────────────────────
    ticker          = (ticker or "0700.HK").strip().upper()
    capital         = float(capital or 100_000)
    slippage_pct    = float(slippage or 0.10) / 100
    commission_pct  = float(commission or 0.26) / 100
    n_sim           = max(100, min(int(n_sim or 1000), 5000))

    preset = STRATEGY_PRESETS.get(strategy)
    if not preset:
        return "⚠️ 找不到策略", []

    # ── 取價格數據並執行回測 ──────────────────────────────────────
    df = get_cached(ticker, period)
    if df.empty:
        return f"❌ 無法獲取 {ticker} 數據", []
    if len(df) < MIN_BARS_FOR_INDICATORS:
        return f"⚠️ {ticker} 數據不足（{len(df)} K線）", []

    try:
        trades, _, _ = run_backtest(
            df,
            buy_sigs=preset["buy"],
            sell_sigs=preset["sell"],
            trade_size=capital,
            slippage_pct=slippage_pct,
            commission_pct=commission_pct,
            stop_loss_pct=preset.get("stop_loss_pct"),
            take_profit_pct=preset.get("take_profit_pct"),
            max_hold_days=preset.get("max_hold_days"),
            min_hold_days=preset.get("min_hold_days"),
            cooldown_days=preset.get("cooldown_days"),
            ticker=ticker,
        )
    except Exception as e:
        return f"❌ 回測失敗：{str(e)[:80]}", []

    if not trades:
        return "⚠️ 無交易記錄（策略條件未觸發），無法執行 Monte Carlo", []

    returns = [t["回報%"] for t in trades]
    n_trades = len(returns)

    if n_trades < 5:
        return (
            f"⚠️ 交易筆數太少（{n_trades} 筆），需至少 5 筆才有統計意義",
            [],
        )

    # ── 執行 MC 模擬 ───────────────────────────────────────────────
    np.random.seed(None)   # 每次隨機
    eq = _run_mc(returns, n_sim, capital)   # (n_sim, n_trades+1)

    final_eq   = eq[:, -1]
    max_dds    = _max_drawdown_vec(eq)
    sharpes    = _sharpe_vec(eq)

    # ── 彙總統計 ───────────────────────────────────────────────────
    def _pct(a, p): return float(np.percentile(a, p))

    bankruptcy_rate = float(np.mean(final_eq < capital * 0.50) * 100)
    loss_rate       = float(np.mean(final_eq < capital)        * 100)
    median_final    = _pct(final_eq, 50)
    mean_final      = float(final_eq.mean())
    p5_final        = _pct(final_eq, 5)
    p95_final       = _pct(final_eq, 95)
    median_dd       = float(np.median(max_dds))
    worst_dd        = float(max_dds.min())
    median_sharpe   = float(np.median(sharpes))

    # 百分位表
    pct_levels = [5, 10, 25, 50, 75, 90, 95]
    pct_vals   = [_pct(final_eq, p) for p in pct_levels]
    pct_rets   = [(v - capital) / capital * 100 for v in pct_vals]

    # ══════════════════════════════════════════════════════════════
    # 圖 1：模擬資金曲線
    # ══════════════════════════════════════════════════════════════
    x = list(range(n_trades + 1))

    # 取樣 150 條用於顯示（統計仍用全部）
    sample_idx = np.random.choice(n_sim, size=min(150, n_sim), replace=False)

    p5_band  = np.percentile(eq,  5, axis=0)
    p25_band = np.percentile(eq, 25, axis=0)
    p50_band = np.percentile(eq, 50, axis=0)
    p75_band = np.percentile(eq, 75, axis=0)
    p95_band = np.percentile(eq, 95, axis=0)

    fig_curves = go.Figure()

    # 半透明模擬線（樣本）
    for i in sample_idx:
        fig_curves.add_trace(go.Scatter(
            x=x, y=eq[i].tolist(),
            mode="lines",
            line=dict(width=0.4, color="rgba(100,160,255,0.07)"),
            showlegend=False,
            hoverinfo="skip",
        ))

    # 5%–95% 填色帶
    fig_curves.add_trace(go.Scatter(
        x=x + x[::-1],
        y=p95_band.tolist() + p5_band.tolist()[::-1],
        fill="toself",
        fillcolor="rgba(38,166,154,0.10)",
        line=dict(color="rgba(0,0,0,0)"),
        name="5%–95% 信心帶",
        hoverinfo="skip",
    ))

    # 25%–75% 填色帶
    fig_curves.add_trace(go.Scatter(
        x=x + x[::-1],
        y=p75_band.tolist() + p25_band.tolist()[::-1],
        fill="toself",
        fillcolor="rgba(38,166,154,0.20)",
        line=dict(color="rgba(0,0,0,0)"),
        name="25%–75% 四分位帶",
        hoverinfo="skip",
    ))

    # 5% 下界
    fig_curves.add_trace(go.Scatter(
        x=x, y=p5_band.tolist(),
        mode="lines",
        line=dict(width=1.2, color="#ef5350", dash="dot"),
        name="5% 下界 (VaR)",
    ))

    # 95% 上界
    fig_curves.add_trace(go.Scatter(
        x=x, y=p95_band.tolist(),
        mode="lines",
        line=dict(width=1.2, color="#f9a825", dash="dot"),
        name="95% 上界",
    ))

    # 中位數（粗線）
    fig_curves.add_trace(go.Scatter(
        x=x, y=p50_band.tolist(),
        mode="lines",
        line=dict(width=2.8, color="#26a69a"),
        name="中位數",
    ))

    # 參考水平線
    fig_curves.add_hline(
        y=capital,
        line_dash="dash", line_color="rgba(255,255,255,0.35)",
        annotation_text=f"初始資金 {capital:,.0f}",
        annotation_position="top left",
        annotation_font_color="rgba(255,255,255,0.5)",
    )
    fig_curves.add_hline(
        y=capital * 0.5,
        line_dash="dash", line_color="rgba(239,83,80,0.55)",
        annotation_text="破產線 (50%)",
        annotation_position="top right",
        annotation_font_color="#ef5350",
    )

    fig_curves.update_layout(
        title=(
            f"🎲 {n_sim} 次 Bootstrap 模擬 ─ "
            f"{ticker} × {strategy} （{n_trades} 筆歷史交易）"
        ),
        xaxis_title="累計交易次數",
        yaxis_title="資金 (HKD)",
        template="plotly_dark",
        paper_bgcolor="#1a1a1a",
        plot_bgcolor="#1a1a1a",
        legend=dict(orientation="h", y=1.03, x=0, font_size=11),
        height=500,
        margin=dict(l=60, r=20, t=60, b=40),
    )

    # ══════════════════════════════════════════════════════════════
    # 圖 2：最終資金分布直方圖
    # ══════════════════════════════════════════════════════════════
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=final_eq.tolist(),
        nbinsx=60,
        marker_color="#26a69a",
        opacity=0.78,
        name="最終資金",
    ))
    for xv, label, color in [
        (capital,       "初始資金",  "rgba(255,255,255,0.7)"),
        (capital * 0.5, "破產線",    "#ef5350"),
        (median_final,  "中位數",    "#26a69a"),
        (p5_final,      "5% VaR",    "#f9a825"),
    ]:
        fig_hist.add_vline(
            x=xv, line_dash="dot", line_color=color,
            annotation_text=label,
            annotation_position="top right",
            annotation_font_color=color,
            annotation_font_size=11,
        )
    fig_hist.update_layout(
        title="📊 最終資金分布",
        xaxis_title="最終資金 (HKD)",
        yaxis_title="頻次",
        template="plotly_dark",
        paper_bgcolor="#1a1a1a",
        plot_bgcolor="#1a1a1a",
        height=330,
        margin=dict(l=50, r=20, t=50, b=40),
    )

    # ══════════════════════════════════════════════════════════════
    # 圖 3：最大回撤分布直方圖
    # ══════════════════════════════════════════════════════════════
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Histogram(
        x=max_dds.tolist(),
        nbinsx=50,
        marker_color="#ef5350",
        opacity=0.78,
        name="最大回撤",
    ))
    fig_dd.add_vline(
        x=median_dd, line_dash="dot", line_color="#f9a825",
        annotation_text=f"中位 {median_dd:.1f}%",
        annotation_position="top right",
        annotation_font_color="#f9a825",
        annotation_font_size=11,
    )
    fig_dd.add_vline(
        x=worst_dd, line_dash="dot", line_color="#ef5350",
        annotation_text=f"最差 {worst_dd:.1f}%",
        annotation_position="top left",
        annotation_font_color="#ef5350",
        annotation_font_size=11,
    )
    fig_dd.update_layout(
        title="📉 最大回撤分布",
        xaxis_title="最大回撤 (%)",
        yaxis_title="頻次",
        template="plotly_dark",
        paper_bgcolor="#1a1a1a",
        plot_bgcolor="#1a1a1a",
        height=330,
        margin=dict(l=50, r=20, t=50, b=40),
    )

    # ══════════════════════════════════════════════════════════════
    # 圖 4：歷史真實回報分布（直方圖）
    # ══════════════════════════════════════════════════════════════
    fig_ret = go.Figure()
    fig_ret.add_trace(go.Histogram(
        x=returns,
        nbinsx=30,
        marker_color="#7986cb",
        opacity=0.78,
        name="歷史每筆回報",
    ))
    fig_ret.add_vline(
        x=0, line_dash="dash", line_color="rgba(255,255,255,0.5)",
        annotation_text="損益平衡", annotation_position="top right",
        annotation_font_size=11,
    )
    mean_ret = float(np.mean(returns))
    fig_ret.add_vline(
        x=mean_ret, line_dash="dot", line_color="#f9a825",
        annotation_text=f"均值 {mean_ret:+.2f}%",
        annotation_position="top left",
        annotation_font_color="#f9a825",
        annotation_font_size=11,
    )
    fig_ret.update_layout(
        title="📋 歷史真實交易回報分布",
        xaxis_title="每筆回報 (%)",
        yaxis_title="頻次",
        template="plotly_dark",
        paper_bgcolor="#1a1a1a",
        plot_bgcolor="#1a1a1a",
        height=280,
        margin=dict(l=50, r=20, t=50, b=40),
    )

    # ══════════════════════════════════════════════════════════════
    # 組裝結果
    # ══════════════════════════════════════════════════════════════

    # 指標卡片
    def _bk_color(r):
        return "#ef5350" if r > 15 else "#f9a825" if r > 5 else "#26a69a"

    def _loss_color(r):
        return "#ef5350" if r > 40 else "#f9a825" if r > 20 else "#26a69a"

    cards = dbc.Row([
        _metric_card("💀 破產概率 (<50%)",
                     f"{bankruptcy_rate:.1f}%",
                     _bk_color(bankruptcy_rate)),
        _metric_card("📉 虧損概率",
                     f"{loss_rate:.1f}%",
                     _loss_color(loss_rate)),
        _metric_card("⚖️ 中位最終資金",
                     f"HK${median_final:,.0f}",
                     "#26a69a" if median_final > capital else "#ef5350"),
        _metric_card("🔻 5% VaR",
                     f"HK${p5_final:,.0f}",
                     "#ef5350" if p5_final < capital else "#26a69a"),
        _metric_card("🎯 95% 上界",
                     f"HK${p95_final:,.0f}",
                     "#f9a825"),
        _metric_card("📊 中位最大回撤",
                     f"{median_dd:.1f}%",
                     "#ef5350"),
    ], className="mb-3 g-2")

    sub_cards = dbc.Row([
        _metric_card("📈 平均最終資金",
                     f"HK${mean_final:,.0f}",
                     "#26a69a" if mean_final > capital else "#ef5350"),
        _metric_card("📉 最差模擬回撤",
                     f"{worst_dd:.1f}%",
                     "#ef5350"),
        _metric_card("🧮 中位 Sharpe",
                     f"{median_sharpe:.3f}",
                     "#26a69a" if median_sharpe > 0 else "#ef5350"),
        _metric_card("🎲 歷史交易筆數",
                     str(n_trades),
                     "white"),
        _metric_card("🔁 模擬次數",
                     f"{n_sim:,}",
                     "white"),
        _metric_card("📊 歷史均回報",
                     f"{mean_ret:+.2f}%",
                     "#26a69a" if mean_ret > 0 else "#ef5350"),
    ], className="mb-4 g-2")

    # 百分位表
    pct_table = dash_table.DataTable(
        columns=[
            {"name": "百分位",       "id": "百分位"},
            {"name": "最終資金 (HKD)", "id": "最終資金"},
            {"name": "相對回報 %",   "id": "相對回報"},
            {"name": "盈 / 虧",      "id": "盈虧"},
        ],
        data=[
            {
                "百分位": f"P{p}",
                "最終資金": f"HK${v:,.0f}",
                "相對回報": f"{r:+.1f}%",
                "盈虧": "✅ 盈" if r >= 0 else "🔴 虧",
            }
            for p, v, r in zip(pct_levels, pct_vals, pct_rets)
        ],
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
            {"if": {"filter_query": '{盈虧} = "✅ 盈"', "column_id": "相對回報"},
             "color": "#26a69a", "fontWeight": "bold"},
            {"if": {"filter_query": '{盈虧} = "🔴 虧"', "column_id": "相對回報"},
             "color": "#ef5350", "fontWeight": "bold"},
        ],
        style_cell={
            "textAlign": "center",
            "padding": "6px 14px",
            "fontFamily": "monospace",
            "fontSize": "0.88rem",
        },
        style_table={"maxWidth": "600px"},
    )

    # ── 方法論說明 ────────────────────────────────────────────────
    methodology_note = dbc.Alert([
        html.Strong("📌 方法論說明："),
        " 本模擬採用 Bootstrap 重採樣，假設每筆交易回報互相獨立（i.i.d.）。",
        " 交易次數與真實歷史相同，每次模擬隨機打亂順序重組。",
        " 結果反映「在相同回報分布下，不同運氣排列」的統計範圍，",
        " 不能預測未來，但可評估策略的穩健性與尾部風險。",
    ], color="secondary", className="small mt-4 mb-2")

    results = [
        cards,
        sub_cards,
        _section("📈 模擬資金曲線",
                 dcc.Graph(figure=fig_curves, config={"displayModeBar": False})),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_hist, config={"displayModeBar": False}), md=6),
            dbc.Col(dcc.Graph(figure=fig_dd,   config={"displayModeBar": False}), md=6),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                _section("📋 百分位分析", pct_table),
            ], md=6),
            dbc.Col([
                _section("📊 歷史真實回報分布",
                         dcc.Graph(figure=fig_ret, config={"displayModeBar": False})),
            ], md=6),
        ]),
        methodology_note,
    ]

    status = (
        f"✅ {ticker} × {strategy} | "
        f"{n_trades} 筆歷史交易 | {n_sim:,} 次模擬完成 | "
        f"破產率 {bankruptcy_rate:.1f}% | 虧損率 {loss_rate:.1f}%"
    )
    return status, results
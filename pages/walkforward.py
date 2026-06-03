import uuid
import threading
import time
import traceback

import dash
from dash import html, dcc, dash_table, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import os
import diskcache as _diskcache
import cache_store as _cs

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")

def _job_get(job_id: str) -> dict | None:
    try:
        with _diskcache.Cache(_CACHE_DIR) as c:
            return c.get("wf_job_" + job_id)
    except Exception:
        return None

def _job_set(job_id: str, data: dict) -> None:
    try:
        with _diskcache.Cache(_CACHE_DIR) as c:
            c.set("wf_job_" + job_id, data, expire=3600)
    except Exception as e:
        print(f"[WF] _job_set FAILED job={job_id[:8]}: {type(e).__name__}: {e}", flush=True)

def _job_delete(job_id: str) -> None:
    try:
        with _diskcache.Cache(_CACHE_DIR) as c:
            c.delete("wf_job_" + job_id)
    except Exception:
        pass

def _job_count() -> int:
    try:
        with _diskcache.Cache(_CACHE_DIR) as c:
            return len([k for k in c if str(k).startswith("wf_job_")])
    except Exception:
        return 0

from data import get_cached, load_stocks
from indicators import calculate_indicators
from walk_forward import run_walk_forward, run_portfolio_walk_forward, _extended_summary
from backtest import calc_bt_metrics
from config import (
    STRATEGY_PRESETS,
    BUY_LABELS, SELL_LABELS,
    MIN_BARS_FOR_INDICATORS,
    WF_ROBUST_MAX_DEGRADATION, WF_ROBUST_MIN_OOS_POS_RATE,
    WF_WARNING_MAX_DEGRADATION, WF_WARNING_MIN_OOS_POS_RATE,
    WF_MIN_IS_RETURN_FOR_CALC,
)

dash.register_page(__name__, path="/walkforward", name="Walk-Forward")

CUSTOM_KEY = "🔧 自訂策略"

STRATEGY_OPTIONS = (
    [{"label": n, "value": n} for n in STRATEGY_PRESETS]
    + [{"label": CUSTOM_KEY, "value": CUSTOM_KEY}]
)
DEFAULT_STRATEGY  = list(STRATEGY_PRESETS.keys())[0]

PERIOD_OPTIONS = [
    {"label": "2年", "value": "2y"},
    {"label": "3年", "value": "3y"},
    {"label": "5年", "value": "5y"},
]

# ── Table 樣式 ────────────────────────────────────────────────────────
_HDR  = {"backgroundColor": "#1a1a1a", "color": "#fff",
          "fontWeight": "bold", "border": "1px solid #444"}
_DAT  = {"backgroundColor": "#262626", "color": "#fff", "border": "1px solid #333"}
_CELL = {"textAlign": "left", "padding": "5px 12px",
         "fontFamily": "monospace", "fontSize": "0.83rem"}

FOLD_COLS = [
    {"name": "Fold",       "id": "Fold"},
    {"name": "IS 期間",    "id": "IS 期間"},
    {"name": "OOS 期間",   "id": "OOS 期間"},
    {"name": "IS 均回報%", "id": "IS 均回報%"},
    {"name": "OOS均回報%", "id": "OOS 均回報%"},
    {"name": "退化率%",    "id": "退化率%"},
    {"name": "IS 勝率%",   "id": "IS 勝率%"},
    {"name": "OOS勝率%",   "id": "OOS 勝率%"},
    {"name": "IS 交易數",  "id": "IS 交易數"},
    {"name": "OOS交易數",  "id": "OOS 交易數"},
    {"name": "強制平倉",   "id": "強制平倉數"},
    {"name": "延伸追蹤",   "id": "延伸追蹤數"},
    {"name": "有效",       "id": "有效"},
    {"name": "股票數",     "id": "股票數"},
    {"name": "過濾原因",   "id": "過濾原因"},
]



# ── 核心工具函式 ──────────────────────────────────────────────────────
def _degradation(is_ret: float, oos_ret: float):
    if abs(is_ret) < WF_MIN_IS_RETURN_FOR_CALC:
        return None
    return (is_ret - oos_ret) / abs(is_ret) * 100


def _build_rows(wf_results: list) -> list:
    rows = []
    for r in wf_results:
        if r.get("skipped_bear"):
            rows.append({
                "Fold":        r["fold"],
                "IS 期間":     f"{r['is_start'].strftime('%Y-%m')} → {r['is_end'].strftime('%Y-%m')}",
                "OOS 期間":    f"{r['oos_start'].strftime('%Y-%m')} → {r['oos_end'].strftime('%Y-%m')}",
                "IS 均回報%":  "—",
                "OOS 均回報%": "—",
                "退化率%":     "—",
                "IS 勝率%":    "—",
                "OOS 勝率%":   "—",
                "IS 交易數":   "—",
                "OOS 交易數":  "—",
                "強制平倉數":  "—",
                "延伸追蹤數":  "—",
                "有效":        "⏭️ 跳過",
                "股票數":      "—",
                "過濾原因":    r.get("filter_reason", "⛔ 熊市"),
                "_deg_raw":    None,
                "_valid_oos":  False,
            })
            continue
        im      = r["is_metrics"]  or {}
        om      = r["oos_metrics"] or {}
        is_ret  = im.get("平均每筆回報%", 0.0)
        oos_ret = om.get("平均每筆回報%", 0.0)
        deg     = _degradation(is_ret, oos_ret)
        forced_n   = r.get("forced_exit_count", 0)
        extended_n = r.get("extended_count", 0)
        rows.append({
            "Fold":        r["fold"],
            "IS 期間":     f"{r['is_start'].strftime('%Y-%m')} → {r['is_end'].strftime('%Y-%m')}",
            "OOS 期間":    f"{r['oos_start'].strftime('%Y-%m')} → {r['oos_end'].strftime('%Y-%m')}",
            "IS 均回報%":  round(is_ret, 2),
            "OOS 均回報%": round(oos_ret, 2),
            "退化率%":     f"{deg:.1f}%" if deg is not None else "—",
            "IS 勝率%":    round(im.get("勝率%", 0.0), 1),
            "OOS 勝率%":   round(om.get("勝率%", 0.0), 1),
            "IS 交易數":   im.get("交易次數", 0),
            "OOS 交易數":  r["oos_trade_count"],
            "強制平倉數":  forced_n,
            "延伸追蹤數":  extended_n,
            "有效":        "✅" if r["valid_oos"] else f"⚠️ {r['oos_trade_count']}筆",
            "股票數":      r.get("pit_stock_count", r.get("n_stocks", 0)),
            "過濾原因":    "",
            # 內部欄位（不直接顯示）
            "_deg_raw":    deg,
            "_valid_oos":  r["valid_oos"],
        })
    return rows


# ── 評估 & 元件建構 ───────────────────────────────────────────────────
def _verdict_section(rows: list, is_portfolio: bool, max_pos: int = 0, use_pit: bool = False) -> list:
    valid_rows = [r for r in rows if r["_valid_oos"] and r["_deg_raw"] is not None]
    if not valid_rows:
        return [dbc.Alert("❌ 所有 Fold 均未達標，無法評估策略。", color="danger")]

    avg_is  = sum(r["IS 均回報%"]  for r in valid_rows) / len(valid_rows)
    avg_oos = sum(r["OOS 均回報%"] for r in valid_rows) / len(valid_rows)
    degs    = [r["_deg_raw"] for r in valid_rows]
    avg_deg = sum(degs) / len(degs)
    oos_pos  = sum(1 for r in valid_rows if r["OOS 均回報%"] > 0)
    oos_rate = oos_pos / len(valid_rows) * 100

    if avg_oos > 0 and avg_deg < WF_ROBUST_MAX_DEGRADATION and oos_rate >= WF_ROBUST_MIN_OOS_POS_RATE:
        verdict, v_color = "🟢 策略穩健（具備真實 Alpha）", "success"
        detail = f"OOS 正回報比率 {oos_rate:.0f}%，退化率 {avg_deg:.1f}% < {WF_ROBUST_MAX_DEGRADATION:.0f}%，策略很可能在實盤有效"
    elif avg_oos > 0 and avg_deg < WF_WARNING_MAX_DEGRADATION and oos_rate >= WF_WARNING_MIN_OOS_POS_RATE:
        verdict, v_color = "🟡 輕度過擬合", "warning"
        detail = f"OOS 仍有正回報但退化率 {avg_deg:.1f}% 偏高，建議加入更嚴格條件或延長驗證期"
    elif avg_oos <= 0:
        verdict, v_color = "🔴 策略危險（OOS 虧損）", "danger"
        detail = f"OOS 平均回報 {avg_oos:.2f}%，策略在未見過的數據上虧損，不應實盤使用"
    else:
        verdict, v_color = "🔴 嚴重過擬合", "danger"
        detail = f"退化率 {avg_deg:.1f}% 過高，IS 回報無法在 OOS 重現"

    mode_lbl  = "（投資組合）" if is_portfolio else "（單股）"
    deg_color = "#26a69a" if avg_deg < WF_ROBUST_MAX_DEGRADATION else ("#f9a825" if avg_deg < WF_WARNING_MAX_DEGRADATION else "#ef5350")

    def _mc(label, value, color="white"):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, className="small text-muted mb-1"),
            html.Div(value, className="fw-bold",
                     style={"color": color, "fontSize": "1.0rem"}),
        ], className="py-2 px-3")), xs=6, md=2, className="mb-2")

    capital_note = html.Small(
        f"⚠️ 投資組合回測假設{'無限資金' if not max_pos else f'最多 {max_pos} 隻同時持倉'}",
        className="text-muted",
    ) if is_portfolio else None

    _pit_low_folds = sum(
        1 for r in rows
        if isinstance(r.get("股票數"), (int, float)) and r.get("股票數") < 20
    ) if (is_portfolio and use_pit) else 0

    return [
        *([
            dbc.Alert(
                "⚠️ PIT 股票池未啟用：當前 OOS 數字使用固定池（2026-05-14 的 183 隻），"
                "可能高估 7-10%。建議開啟「🧬 PIT 股票池」重跑以獲得可信數字。",
                color="warning",
                className="mb-2",
            )
        ] if is_portfolio and not use_pit else []),
        *([
            dbc.Alert(
                f"⚠️ 有 {_pit_low_folds} 個 Fold 的 PIT 股票池少於 20 隻，統計可靠度偏低。"
                "可能原因：EODHD 數據未覆蓋該時段，建議補充 data/eodhd_prices/ 資料。",
                color="warning",
                className="mb-2",
            )
        ] if _pit_low_folds > 0 else []),
        dbc.Alert([
            html.Strong(f"{verdict} {mode_lbl}",
                        style={"fontSize": "1.1rem"}),
            html.Br(),
            html.Small(detail),
        ], color=v_color, className="mb-2"),

        dbc.Row([
            _mc("IS 平均每筆%",    f"{avg_is:+.2f}%",
                "#26a69a" if avg_is  > 0 else "#ef5350"),
            _mc("OOS 平均每筆%",   f"{avg_oos:+.2f}%",
                "#26a69a" if avg_oos > 0 else "#ef5350"),
            _mc("平均退化率%",     f"{avg_deg:.1f}%", deg_color),
            _mc("OOS 正回報 Fold", f"{oos_pos}/{len(valid_rows)}"),
            _mc("有效 Fold",       f"{len(valid_rows)}/{len(rows)}"),
        ], className="g-2 mb-3"),
        html.Small(
            "ℹ️ WF 採固定倉位模式（每筆各用 trade_size 獨立試驗），"
            "OOS 均回報% 為各筆平均，非複利累計回報",
            className="text-muted d-block mb-2",
            style={"fontSize": "0.78rem"},
        ),
        *([capital_note] if capital_note else []),
        *([
            html.Div([
                dbc.Badge("🧬 PIT 股票池已啟用", color="info", className="me-2"),
                html.Small("每個 Fold 使用當時符合條件的股票池，已修正生存者偏差與前視偏差",
                           className="text-muted"),
            ], className="mb-3")
        ] if use_pit else []),
    ]


# ══════════════════════════════════════════════════════════════════
# 🔍 延伸追蹤 + survivorship bias 警示
# （從 Streamlit 版 show_walk_forward_results 移植回 Dash）
# 把原本在 Fold 邊界被強制平倉的交易，用全期數據繼續持有到真實 sell
# 信號（或 365 日上限），比對「真實均回報」vs「WF OOS 指標」。
# 若真實均回報明顯低於 OOS 指標 → 疑似 survivorship bias。
# ══════════════════════════════════════════════════════════════════
def _extended_section(wf_results: list, rows: list) -> html.Div:
    valid_rows = [r for r in rows if r["_valid_oos"] and r["_deg_raw"] is not None]
    if not valid_rows:
        return html.Div()
    avg_oos = sum(r["OOS 均回報%"] for r in valid_rows) / len(valid_rows)

    total_forced = sum(r.get("forced_exit_count", 0) for r in wf_results)
    all_extended = [t for r in wf_results for t in r.get("oos_extended_trades", [])]
    ext = _extended_summary(all_extended)

    # 完全沒有強制平倉 → 無 survivorship 疑慮，給一行綠字確認即可
    if total_forced == 0:
        return html.Div([
            html.H6("🔍 延伸追蹤：強制平倉檢查", className="mb-2 mt-2"),
            dbc.Alert(
                "✅ 本次驗證沒有任何 Fold 邊界強制平倉，OOS 指標完整反映策略出場，"
                "無 survivorship bias 疑慮。",
                color="success", className="py-2 mb-2",
            ),
        ], className="mb-3")

    closed = ext.get("closed", 0)

    def _mc(label, value, color="white", sub=None):
        body = [
            html.Div(label, className="small text-muted mb-1"),
            html.Div(value, className="fw-bold",
                     style={"color": color, "fontSize": "1.0rem"}),
        ]
        if sub:
            body.append(html.Small(sub, className="text-muted"))
        return dbc.Col(dbc.Card(dbc.CardBody(body, className="py-2 px-3")),
                       xs=6, md=3, className="mb-2")

    children = [
        html.H6("🔍 延伸追蹤：強制平倉交易的真實結果", className="mb-2 mt-2"),
        html.Small(
            "把原本在 Fold 邊界被強制平倉的交易保留，用全期數據繼續持有到真實 sell 信號"
            "（或 365 日上限）。純診斷用途，不計入上方 WF 指標。",
            className="text-muted d-block mb-2",
            style={"fontSize": "0.8rem"},
        ),
    ]

    if closed == 0:
        # 有強制平倉但延伸後全部仍未觸發出場 → 真實結果不可知
        still = ext.get("still_held", 0)
        children.append(dbc.Alert(
            f"ℹ️ 全程 {total_forced} 筆期末強制平倉，延伸追蹤後 {still} 筆即使持有 365 日"
            "仍未觸發真實 sell 信號，真實結果不可知。OOS 指標僅反映「跑完全程」的交易，"
            "請對 OOS 數字保留戒心。",
            color="warning", className="py-2 mb-2",
        ))
        return html.Div(children, className="mb-3")

    ext_avg  = ext.get("avg_return", 0.0)
    ext_wr   = ext.get("win_rate", 0.0)
    ext_days = ext.get("avg_days", 0.0)
    still    = ext.get("still_held", 0)

    children.append(dbc.Row([
        _mc("真實出場交易數", f"{closed} 筆",
            sub=f"共 {ext.get('total', closed)} 筆中"),
        _mc("真實出場均回報%", f"{'+' if ext_avg >= 0 else ''}{ext_avg:.2f}%",
            "#26a69a" if ext_avg >= 0 else "#ef5350",
            sub=f"vs OOS 指標 {avg_oos:+.2f}%"),
        _mc("真實出場勝率", f"{ext_wr:.1f}%"),
        _mc("平均持倉天數", f"{ext_days:.0f} 天"),
    ], className="g-2 mb-2"))

    # ── 核心守門邏輯：survivorship bias 判定 ──
    if ext_avg < avg_oos - 3:
        children.append(dbc.Alert([
            html.Strong("⚠️ 警示：疑似 survivorship bias"),
            html.Br(),
            html.Small(
                f"WF 指標 OOS {avg_oos:+.2f}%，但把原本被強制平倉的交易加回後，"
                f"真實均回報只有 {ext_avg:+.2f}%。原本的高 OOS 數字很可能只統計了"
                "「跑完全程、觸發到真實出場」的贏家，被排除的平庸/虧損單沒被計入。"
                "此策略的 OOS 數字不可信，請勿據此實盤或升 💎。"
            ),
        ], color="danger", className="py-2 mb-2"))
    elif ext_avg > avg_oos:
        children.append(dbc.Alert([
            html.Strong("✅ 無 survivorship bias"),
            html.Br(),
            html.Small(
                f"強制平倉交易的真實結果（{ext_avg:+.2f}%）比 WF OOS 指標"
                f"（{avg_oos:+.2f}%）更好，說明 OOS 數字沒有高估策略，策略紮實。"
            ),
        ], color="success", className="py-2 mb-2"))
    else:
        children.append(dbc.Alert([
            html.Strong("🟡 輕微差距，尚可接受"),
            html.Br(),
            html.Small(
                f"真實均回報 {ext_avg:+.2f}% 略低於 OOS 指標 {avg_oos:+.2f}%，"
                "但差距在 3% 以內，無明顯 survivorship bias。"
            ),
        ], color="warning", className="py-2 mb-2"))

    if still > 0:
        children.append(html.Small(
            f"ℹ️ 另有 {still} 筆即使延伸 365 日仍未觸發 sell 信號，按延伸期末收盤計算，"
            "這類交易的真實結果仍不可知。",
            className="text-muted d-block",
            style={"fontSize": "0.78rem"},
        ))

    return html.Div(children, className="mb-3")


def _bar_chart(rows: list) -> go.Figure:
    def _safe_num(v):
        return v if isinstance(v, (int, float)) else None

    def _safe_fmt(v):
        return f"{v:+.1f}%" if isinstance(v, (int, float)) else str(v)

    labels = [
        f"Fold {r['Fold']}<br>{r['OOS 期間'].split(' → ')[0]}"
        + ("" if r["_valid_oos"] else " ⚠️")
        for r in rows
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="In-Sample", x=labels,
        y=[_safe_num(r["IS 均回報%"]) for r in rows],
        marker_color=["rgba(100,180,255,0.7)" if r["_valid_oos"]
                      else "rgba(100,180,255,0.25)" for r in rows],
        text=[_safe_fmt(r["IS 均回報%"]) for r in rows],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Out-of-Sample", x=labels,
        y=[_safe_num(r["OOS 均回報%"]) for r in rows],
        marker_color=[
            ("#26a69a" if r["OOS 均回報%"] >= 0 else "#ef5350") if r["_valid_oos"]
            else "rgba(128,128,128,0.3)"
            for r in rows
        ],
        text=[_safe_fmt(r["OOS 均回報%"]) for r in rows],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.25)")
    fig.update_layout(
        barmode="group", height=380, margin=dict(t=25, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _deg_chart(rows: list) -> go.Figure:
    deg_vals = [r["_deg_raw"] if r["_deg_raw"] is not None else 0 for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[f"Fold {r['Fold']}" for r in rows],
        y=deg_vals,
        mode="lines+markers+text",
        text=[r["退化率%"] for r in rows],
        textposition="top center",
        line=dict(color="#f9a825", width=2),
        marker=dict(
            size=10,
            color=[
                "rgba(150,150,150,0.4)" if (not r["_valid_oos"] or r["_deg_raw"] is None)
                else ("#26a69a" if d < 40 else ("#f9a825" if d < 65 else "#ef5350"))
                for r, d in zip(rows, deg_vals)
            ],
        ),
    ))
    fig.add_hline(y=WF_ROBUST_MAX_DEGRADATION, line_dash="dot",
                  line_color="rgba(38,166,154,0.5)",
                  annotation_text=f"{WF_ROBUST_MAX_DEGRADATION:.0f}% 健康線",
                  annotation_position="right")
    fig.add_hline(y=WF_WARNING_MAX_DEGRADATION, line_dash="dot",
                  line_color="rgba(239,83,80,0.5)",
                  annotation_text=f"{WF_WARNING_MAX_DEGRADATION:.0f}% 警戒線",
                  annotation_position="right")
    fig.update_layout(
        height=280, margin=dict(t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%", yaxis_title="退化率%",
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _oos_equity_chart(wf_results: list, trade_size: float) -> go.Figure:
    pieces, running = [], trade_size
    for r in wf_results:
        if not r["valid_oos"] or r["oos_equity"].empty:
            continue
        scale = running / trade_size
        piece = r["oos_equity"]["equity"] * scale
        pieces.append(piece)
        running = float(piece.iloc[-1])

    if not pieces:
        fig = go.Figure()
        fig.add_annotation(text="無有效 Fold，無法繪製 OOS 曲線",
                           x=0.5, y=0.5, xref="paper", yref="paper",
                           font=dict(size=14, color="#888"), showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", height=260)
        return fig

    combined = pd.concat(pieces)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    norm      = combined / trade_size * 100 - 100
    final_ret = float(norm.iloc[-1])
    line_c    = "#26a69a" if final_ret >= 0 else "#ef5350"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=norm.index, y=norm,
        fill="tozeroy",
        line=dict(color=line_c, width=2),
        fillcolor=f"rgba({'38,166,154' if final_ret >= 0 else '239,83,80'},0.08)",
        name="OOS 拼接曲線",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
    fig.add_annotation(
        text=f"OOS 總回報：{final_ret:+.1f}%",
        xref="paper", yref="paper", x=0.02, y=0.92, showarrow=False,
        font=dict(size=13, color=line_c),
    )
    fig.update_layout(
        height=300, margin=dict(t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_ticksuffix="%",
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _fold_table(rows: list) -> dash_table.DataTable:
    cond = [
        {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
        {"if": {"filter_query": "{IS 均回報%} > 0", "column_id": "IS 均回報%"},
         "color": "#26a69a"},
        {"if": {"filter_query": "{IS 均回報%} < 0", "column_id": "IS 均回報%"},
         "color": "#ef5350"},
        {"if": {"filter_query": "{OOS 均回報%} > 0", "column_id": "OOS 均回報%"},
         "color": "#26a69a", "fontWeight": "bold"},
        {"if": {"filter_query": "{OOS 均回報%} < 0", "column_id": "OOS 均回報%"},
         "color": "#ef5350", "fontWeight": "bold"},
        # 強制平倉數醒目標示：>0 用黃字提醒「這欄有被排除的交易」
        {"if": {"filter_query": "{強制平倉數} > 0", "column_id": "強制平倉數"},
         "color": "#f9a825", "fontWeight": "bold"},
    ]
    for i, r in enumerate(rows):
        d = r["_deg_raw"]
        if d is None:
            continue
        c = "#26a69a" if d < WF_ROBUST_MAX_DEGRADATION else ("#f9a825" if d < WF_WARNING_MAX_DEGRADATION else "#ef5350")
        cond.append({"if": {"row_index": i, "column_id": "退化率%"},
                     "color": c, "fontWeight": "bold"})

    table_data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    return dash_table.DataTable(
        columns=FOLD_COLS,
        data=table_data,
        sort_action="native",
        page_action="none",
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=cond,
        style_cell=_CELL,
        style_table={"overflowX": "auto"},
    )


# ══════════════════════════════════════════════════════════════════
# 🔬 逐 Fold 交易明細（AUDIT-G 🟡-4：從 Streamlit 版移植回 Dash）
# 每個 Fold 一個 Accordion 項，內含三張表：
#   1. 策略出場交易（oos_trades）
#   2. 期末強制平倉明細（oos_forced_trades，未計入指標）
#   3. 延伸追蹤明細（oos_extended_trades，含「真實出場 / 仍持倉」狀態）
# 資料 dict 全都有，純前端補畫——補回「是哪個 Fold、哪幾筆被強制平倉/延伸」的鑑識資訊。
# ══════════════════════════════════════════════════════════════════
_FOLD_DETAIL_BASE_COLS = [
    "買入日期", "賣出日期", "買入價", "賣出價",
    "回報%", "盈虧(HKD)", "持倉天數", "賣出原因",
]


def _trades_datatable(trades: list, is_portfolio: bool, extra_status: bool = False):
    """把一個 trade list 攤成 DataTable；extra_status=True 時補「狀態」欄（延伸追蹤用）。"""
    if not trades:
        return None

    base_cols = (["ticker"] if is_portfolio else []) + _FOLD_DETAIL_BASE_COLS
    # 只保留至少有一筆出現過的欄位
    avail = [c for c in base_cols if any(c in t for t in trades)]

    rows = []
    for t in trades:
        row = {c: t.get(c) for c in avail}
        if extra_status:
            row["狀態"] = "⏳ 延伸後仍持倉" if t.get("_still_held_at_end") else "✅ 真實出場"
        rows.append(row)

    columns = [{"name": ("代碼" if c == "ticker" else c), "id": c} for c in avail]
    if extra_status:
        columns.append({"name": "狀態", "id": "狀態"})

    cond = [
        {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
        {"if": {"filter_query": "{回報%} > 0", "column_id": "回報%"},
         "color": "#26a69a", "fontWeight": "bold"},
        {"if": {"filter_query": "{回報%} < 0", "column_id": "回報%"},
         "color": "#ef5350", "fontWeight": "bold"},
        {"if": {"filter_query": "{盈虧(HKD)} > 0", "column_id": "盈虧(HKD)"},
         "color": "#26a69a"},
        {"if": {"filter_query": "{盈虧(HKD)} < 0", "column_id": "盈虧(HKD)"},
         "color": "#ef5350"},
    ]
    return dash_table.DataTable(
        columns=columns,
        data=rows,
        sort_action="native",
        page_size=20,
        style_header=_HDR,
        style_data=_DAT,
        style_data_conditional=cond,
        style_cell=_CELL,
        style_table={"overflowX": "auto"},
    )


def _per_fold_detail_section(wf_results: list, is_portfolio: bool):
    items = []
    for r in wf_results:
        fold_n = r.get("fold", 0)

        # 熊市跳過的 Fold：給一行說明，無交易表
        if r.get("skipped_bear"):
            title = (
                f"⏭️ Fold {fold_n}｜"
                f"{r['oos_start'].strftime('%Y-%m-%d')} → {r['oos_end'].strftime('%Y-%m-%d')}"
                f"｜{r.get('filter_reason', '⛔ 熊市')} 跳過"
            )
            items.append(dbc.AccordionItem(
                [dbc.Alert(
                    f"{r.get('filter_reason', '⛔ 熊市')}：本 Fold 因制度過濾跳過，無交易。",
                    color="secondary", className="py-2 mb-0",
                )],
                title=title,
            ))
            continue

        im       = r.get("is_metrics")  or {}
        om       = r.get("oos_metrics") or {}
        valid    = r.get("valid_oos")
        forced_n = r.get("forced_exit_count", 0)
        ext_n    = r.get("extended_count", 0)
        oos_n    = r.get("oos_trade_count", 0)

        title = (
            f"{'✅' if valid else '⚠️'} Fold {fold_n}"
            f"｜OOS {r['oos_start'].strftime('%Y-%m-%d')} → {r['oos_end'].strftime('%Y-%m-%d')}"
            f"｜IS {im.get('平均每筆回報%', 0):+.2f}% → OOS {om.get('平均每筆回報%', 0):+.2f}%"
            + (f"｜策略出場 {oos_n} 筆" if valid else f"｜⚠️ 僅 {oos_n} 筆OOS")
            + (f"｜強制 {forced_n} 延伸 {ext_n}" if forced_n > 0 else "")
        )

        body = []
        if not valid:
            body.append(dbc.Alert(
                f"⚠️ 此 Fold OOS 僅 {oos_n} 筆策略出場，排除在評分之外。",
                color="warning", className="py-2 mb-2",
            ))
        if forced_n > 0:
            body.append(html.Small(
                f"ℹ️ 本 Fold 有 {forced_n} 筆期末強制平倉（不計入指標）"
                + (f"，其中 {ext_n} 筆已延伸追蹤到真實結果" if ext_n else "")
                + "。",
                className="text-muted d-block mb-2", style={"fontSize": "0.78rem"},
            ))
        if is_portfolio and r.get("n_stocks"):
            body.append(html.Small(
                f"本 Fold 實際跑 {r['n_stocks']} 隻股票",
                className="text-muted d-block mb-2", style={"fontSize": "0.78rem"},
            ))

        # 1. 策略出場
        body.append(html.Small("📗 策略出場交易",
                               className="fw-bold d-block mt-1 mb-1"))
        t_strat = _trades_datatable(r.get("oos_trades", []), is_portfolio)
        body.append(t_strat if t_strat is not None else html.Small(
            "本 Fold 無策略出場交易", className="text-muted d-block mb-2"))

        # 2. 期末強制平倉明細
        forced_list = r.get("oos_forced_trades", [])
        if forced_list:
            body.append(html.Small(
                f"📋 期末強制平倉明細（{len(forced_list)} 筆，因 Fold 邊界截斷，未計入指標）",
                className="fw-bold d-block mt-3 mb-1", style={"color": "#f9a825"},
            ))
            body.append(_trades_datatable(forced_list, is_portfolio))

        # 3. 延伸追蹤明細
        ext_list = r.get("oos_extended_trades", [])
        if ext_list:
            es      = _extended_summary(ext_list)
            closed  = es.get("closed", 0)
            still   = es.get("still_held", 0)
            avg_r   = es.get("avg_return", 0.0)
            body.append(html.Small(
                f"🔍 延伸追蹤明細（{len(ext_list)} 筆；真實出場 {closed} 筆"
                f"，均 {'+' if avg_r >= 0 else ''}{avg_r:.2f}%；仍持倉 {still} 筆）",
                className="fw-bold d-block mt-3 mb-1", style={"color": "#42a5f5"},
            ))
            body.append(html.Small(
                "原本在 Fold 邊界被強制平倉的交易，用全期數據繼續持有到真實 sell 信號"
                "（或 365 日上限）。純診斷用途，不計入上方 WF 指標。",
                className="text-muted d-block mb-1", style={"fontSize": "0.76rem"},
            ))
            body.append(_trades_datatable(ext_list, is_portfolio, extra_status=True))

        items.append(dbc.AccordionItem(body, title=title))

    if not items:
        return html.Div()

    return html.Div([
        html.H6("🔬 逐 Fold 交易記錄（鑑識用：策略出場 / 強制平倉 / 延伸追蹤明細）",
                className="mb-2"),
        html.Small(
            "展開任一 Fold 可看該 Fold 的逐筆交易；強制平倉 / 延伸追蹤表只在該 Fold 有對應資料時出現。",
            className="text-muted d-block mb-2", style={"fontSize": "0.78rem"},
        ),
        dbc.Accordion(items, start_collapsed=True, always_open=False, flush=False),
    ], className="mb-3")


_WF_STOCK_COLS = [
    {"name": "代碼",         "id": "代碼"},
    {"name": "OOS平均每筆%",  "id": "平均每筆%"},
    {"name": "OOS勝率%",      "id": "勝率%"},
    {"name": "OOS交易數",     "id": "交易次數"},
    {"name": "Profit F",      "id": "Profit Factor"},
    {"name": "最大回撤%",     "id": "最大回撤%"},
    {"name": "最大連輸",      "id": "最大連輸"},
    {"name": "平均持倉天",    "id": "平均持倉天"},
]

_WF_STOCK_COND = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#1f1f1f"},
    {"if": {"filter_query": "{平均每筆%} > 0", "column_id": "平均每筆%"},
     "color": "#26a69a", "fontWeight": "bold"},
    {"if": {"filter_query": "{平均每筆%} < 0", "column_id": "平均每筆%"},
     "color": "#ef5350", "fontWeight": "bold"},
    {"if": {"filter_query": "{Profit Factor} >= 1.5", "column_id": "Profit Factor"},
     "color": "#26a69a"},
    {"if": {"filter_query": "{最大回撤%} < -20", "column_id": "最大回撤%"},
     "color": "#ef5350"},
]


def _per_stock_oos_rows(wf_results: list, trade_size: float) -> list:
    try:
        from collections import defaultdict
        by_ticker = defaultdict(list)
        for r in wf_results:
            if not r.get("valid_oos"):
                continue
            for t in r.get("oos_trades", []):
                tk = t.get("ticker")
                if tk:
                    by_ticker[tk].append(t)

        rows = []
        for tk, trades in by_ticker.items():
            ordered = sorted(trades, key=lambda x: (x.get("_sell_date") is None, x.get("_sell_date")))
            cap, eq_rows = trade_size, []
            for t in ordered:
                cap *= (1 + t["回報%"] / 100)
                eq_rows.append({"date": t["_sell_date"], "equity": cap})
            if eq_rows:
                eq_df = (pd.DataFrame(eq_rows)
                         .drop_duplicates("date", keep="last")
                         .set_index("date")[["equity"]])
            else:
                eq_df = pd.DataFrame()

            m = calc_bt_metrics(trades, eq_df, trade_size)
            if not m:
                continue
            pf = m["Profit Factor"]
            rows.append({
                "代碼":          tk,
                "平均每筆%":     round(m["平均每筆回報%"], 2),
                "勝率%":         round(m["勝率%"], 1),
                "交易次數":      m["交易次數"],
                "Profit Factor": "∞" if pf == float("inf") else round(pf, 2),
                "最大回撤%":     round(m["最大回撤%"], 2),
                "最大連輸":      m["最大連輸"],
                "平均持倉天":    round(m["平均持倉天數"], 1),
                "_avg_raw":      m["平均每筆回報%"],
            })
        rows.sort(key=lambda x: -x["_avg_raw"])
        return rows
    except Exception:
        print("[WF] _per_stock_oos_rows ERROR:\n" + traceback.format_exc(), flush=True)
        raise


def _per_stock_section(wf_results: list, trade_size: float):
    rows = _per_stock_oos_rows(wf_results, trade_size)
    if not rows:
        return html.Div()
    n    = len(rows)
    pos  = sum(1 for r in rows if r["_avg_raw"] > 0)
    avg  = sum(r["_avg_raw"] for r in rows) / n
    data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    return html.Div([
        html.H6("🏆 全倉 OOS 逐股結果", className="mb-2"),
        dbc.Alert(
            f"📊 共回測 {n} 隻｜🟢 正回報 {pos}｜🔴 負回報 {n - pos}｜"
            f"平均每筆 {avg:+.2f}%（僅統計有效 Fold 的策略出場交易，已排除期末強制平倉）",
            color="secondary", className="py-2 mb-2",
        ),
        dash_table.DataTable(
            columns=_WF_STOCK_COLS,
            data=data,
            sort_action="native",
            page_size=30,
            style_header=_HDR,
            style_data=_DAT,
            style_data_conditional=_WF_STOCK_COND,
            style_cell={"textAlign": "center", "padding": "5px 12px",
                        "fontFamily": "monospace", "fontSize": "0.85rem"},
            style_cell_conditional=[{"if": {"column_id": "代碼"}, "textAlign": "left"}],
            style_table={"overflowX": "auto"},
        ),
        html.Small(
            "ℹ️ 「最大回撤%」為各股 OOS 交易複利重建的近似值，"
            "與 WF 引擎本身的固定倉位非複利口徑不同，僅供排序與體感參考，"
            "請勿當作嚴謹回撤數字。",
            className="text-muted d-block mt-2",
            style={"fontSize": "0.78rem"},
        ),
    ], className="mb-3")


# ── 數據載入 + WF 執行 ────────────────────────────────────────────────
def _run_wf(mode, strategy, ticker, total_period, is_mo, oos_mo, trade_size, slippage_ui,
            max_positions=0, progress_cb=None, commission_ui=None,
            custom_buy=None, custom_sell=None, use_pit=False, bear_filter=False):
    if strategy == CUSTOM_KEY:
        if not custom_buy:
            return None, False, "⚠️ 請至少勾選一個買入訊號"
        if not custom_sell:
            return None, False, "⚠️ 請至少勾選一個賣出訊號"
        buy_sigs        = tuple(f"b{i+1}" in (custom_buy  or []) for i in range(len(BUY_LABELS)))
        sell_sigs       = tuple(f"s{i+1}" in (custom_sell or []) for i in range(8))
        min_hold        = None
        cooldown        = None
        seasonal_filter = False
    else:
        preset = STRATEGY_PRESETS.get(strategy)
        if not preset:
            return None, False, "⚠️ 找不到策略"
        buy_sigs        = preset["buy"]
        sell_sigs       = preset["sell"]
        min_hold        = preset.get("min_hold_days")
        cooldown        = preset.get("cooldown_days")
        seasonal_filter = preset.get("seasonal_filter", False)
    ts        = float(trade_size or 100_000)
    slip            = float(slippage_ui or 0.10) / 100
    commission_pct  = float(commission_ui or 0.26) / 100
    is_mo           = int(is_mo  or 12)
    oos_mo          = int(oos_mo or 6)
    max_pos   = int(max_positions or 0)

    if mode == "single":
        ticker_clean = (ticker or "0700.HK").strip().upper()
        df = get_cached(ticker_clean, total_period)
        if df.empty:
            return None, False, f"❌ 無法獲取 {ticker_clean} 數據"
        min_bars = (is_mo + oos_mo) * 21 + MIN_BARS_FOR_INDICATORS
        if len(df) < min_bars:
            return None, False, (
                f"⚠️ {ticker_clean} 數據不足（{len(df)} 根K線，"
                f"需至少 {min_bars}）。請選擇更長週期。"
            )
        try:
            results = run_walk_forward(
                df, buy_sigs, sell_sigs,
                is_months=is_mo, oos_months=oos_mo,
                trade_size=ts, slippage=slip,
                commission_pct=commission_pct,
                min_hold_days=min_hold,
                cooldown_days=cooldown,
                progress_cb=progress_cb,
                seasonal_filter=seasonal_filter,
            )
        except Exception as e:
            return None, False, f"❌ WF 失敗：{str(e)[:80]}"
        return results, False, None

    else:  # portfolio
        stock_data = {}
        for t in load_stocks():
            df_t = get_cached(t, total_period)
            if not df_t.empty and len(df_t) >= MIN_BARS_FOR_INDICATORS:
                stock_data[t] = df_t
        if len(stock_data) < 5:
            return None, True, (
                f"⚠️ 投資組合模式需要至少 5 隻股票的緩存數據"
                f"（目前 {len(stock_data)} 隻，週期 {total_period}）。"
                f"請先用「⬇️ 下載數據」下載對應年期（{total_period}）數據。"
            )
        try:
            results = run_portfolio_walk_forward(
                stock_data, buy_sigs, sell_sigs,
                is_months=is_mo, oos_months=oos_mo,
                trade_size=ts, slippage=slip,
                commission_pct=commission_pct,
                min_hold_days=min_hold,
                cooldown_days=cooldown,
                max_concurrent_positions=max_pos if max_pos > 0 else None,
                progress_cb=progress_cb,
                seasonal_filter=seasonal_filter,
                use_pit_universe=use_pit,
                bear_filter=bear_filter,
            )
        except Exception as e:
            return None, True, f"❌ 投資組合 WF 失敗：{str(e)[:80]}"
        return results, True, None


def _run_wf_thread(job_id, mode, strategy, ticker, total_period, is_mo, oos_mo, trade_size, slippage, max_positions, commission=None, custom_buy=None, custom_sell=None, use_pit=False, bear_filter=False):
    import traceback
    short = job_id[:8]
    print(f"[WF] Thread start  job={short} mode={mode} ticker={ticker}")
    try:
        def progress_cb(fold, total_folds, current):
            existing = _job_get(job_id) or {}
            existing.update({
                "fold": fold,
                "total_folds": total_folds,
                "current": current or "",
            })
            _job_set(job_id, existing)
            print(f"[WF] Progress  job={short} fold={fold}/{total_folds} cur={current}")

        wf_results, is_portfolio, err = _run_wf(
            mode, strategy, ticker, total_period,
            is_mo, oos_mo, trade_size, slippage,
            max_positions=max_positions,
            commission_ui=commission,
            custom_buy=custom_buy,
            custom_sell=custom_sell,
            progress_cb=progress_cb,
            use_pit=use_pit,
            bear_filter=bear_filter,
        )
        n = len(wf_results) if wf_results else 0
        print(f"[WF] Thread done   job={short} results={n} err={err}")
        _job_set(job_id, {
            "status":       "done",
            "result":       wf_results,
            "is_portfolio": is_portfolio,
            "error":        err,
            "created_at":   (_job_get(job_id) or {}).get("created_at", time.time()),
            "params": {
                "strategy":      strategy,
                "ticker":        ticker or "0700.HK",
                "is_mo":         is_mo,
                "oos_mo":        oos_mo,
                "trade_size":    trade_size,
                "max_positions": max_positions,
                "use_pit":       use_pit,
                "bear_filter":   bear_filter,
            },
        })
    except Exception as e:
        print(f"[WF] Thread ERROR  job={short}: {e}\n{traceback.format_exc()}")
        _job_set(job_id, {
            "status": "done", "result": None,
            "is_portfolio": False,
            "error": f"❌ 執行失敗：{e}", "params": {},
            "created_at": (_job_get(job_id) or {}).get("created_at", time.time()),
        })


# ── Layout ───────────────────────────────────────────────────────────
def _param_col(label, input_id, **kwargs):
    return dbc.Col([
        html.Label(label, className="small text-muted mb-1 d-block"),
        dbc.Input(id=input_id, type="number", size="sm", **kwargs),
    ], xs=6, md=2, className="mb-2")


layout = html.Div([
    html.H4("🔬 Walk-Forward 驗證", className="mb-3"),

    # 策略
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id="wf-strategy",
                options=STRATEGY_OPTIONS,
                value=DEFAULT_STRATEGY,
                clearable=False,
                style={"color": "#111"},
            ),
            md=8, className="mb-2",
        ),
    ], className="mb-1"),

    # 自訂策略面板（選擇 CUSTOM_KEY 才顯示）
    html.Div(
        id="wf-custom-panel",
        style={"display": "none"},
        children=[
            html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col([
                    html.Label(
                        "買入訊號（AND 邏輯：全部勾選條件須同時成立）",
                        className="small text-muted mb-1 d-block",
                    ),
                    dbc.Checklist(
                        id="wf-custom-buy",
                        options=[
                            {"label": f" {BUY_LABELS[i]}", "value": f"b{i+1}"}
                            for i in range(len(BUY_LABELS))
                        ],
                        value=[],
                        className="small",
                        inputStyle={"cursor": "pointer"},
                        labelStyle={
                            "display": "block",
                            "marginBottom": "3px",
                            "cursor": "pointer",
                        },
                    ),
                ], md=6),
                dbc.Col([
                    html.Label(
                        "賣出訊號（OR 邏輯：任一觸發即賣出）",
                        className="small text-muted mb-1 d-block",
                    ),
                    dbc.Checklist(
                        id="wf-custom-sell",
                        options=[
                            {"label": f" {SELL_LABELS[i]}", "value": f"s{i+1}"}
                            for i in range(8)
                        ],
                        value=[],
                        className="small",
                        inputStyle={"cursor": "pointer"},
                        labelStyle={
                            "display": "block",
                            "marginBottom": "3px",
                            "cursor": "pointer",
                        },
                    ),
                ], md=6),
            ], className="mb-2"),
            html.Hr(className="my-2"),
        ],
    ),

    # 參數列
    dbc.Row([
        dbc.Col([
            html.Label("模式", className="small text-muted mb-1 d-block"),
            dbc.RadioItems(
                id="wf-mode",
                options=[
                    {"label": "單股", "value": "single"},
                    {"label": "投資組合", "value": "portfolio"},
                ],
                value="single",
                inline=True,
            ),
        ], xs=12, md=2, className="mb-2"),

        dbc.Col([
            html.Label("股票代碼（單股）", className="small text-muted mb-1 d-block"),
            dbc.Input(id="wf-ticker", value="0700.HK", type="text", size="sm"),
        ], id="wf-ticker-col", xs=6, md=2, className="mb-2"),

        dbc.Col([
            html.Label("總數據週期", className="small text-muted mb-1 d-block"),
            dbc.RadioItems(
                id="wf-total-period",
                options=PERIOD_OPTIONS,
                value="3y",
                inline=True,
            ),
            html.Small(
                "💡 建議先批量下載對應年期數據",
                id="wf-portfolio-hint",
                className="text-warning mt-1 d-block",
                style={"display": "none"},
            ),
        ], xs=12, md=2, className="mb-2"),

        _param_col("IS 窗口（月）", "wf-is-mo",  value=12, min=3,  step=3),
        _param_col("OOS 窗口（月）","wf-oos-mo", value=6,  min=1,  step=1),
    ], className="mb-1"),

    dbc.Row([
        _param_col("每筆金額 (HKD)", "wf-trade-size",  value=100000, step=10000),
        _param_col("純滑點%",        "wf-slippage",    value=0.10,   step=0.01, min=0),
        _param_col("手續費%（雙邊）",  "wf-commission",  value=0.26,   step=0.01, min=0),
        dbc.Col([
            html.Label("同時持倉上限 (0=不限)", className="small text-muted mb-1 d-block"),
            dbc.Input(id="wf-max-positions", type="number", size="sm",
                      value=0, min=0, step=1),
            html.Small(
                "限制任意時間點的同時持倉總數，超過上限的新訊號當日跳過",
                className="text-warning",
                style={"fontSize": "0.75rem"},
            ),
        ], id="wf-max-pos-col", xs=6, md=2, className="mb-2",
           style={"display": "none"}),
        dbc.Col([
            html.Label(" ", className="small text-muted mb-1 d-block"),
            dbc.Switch(
                id="wf-use-pit",
                label="🧬 PIT 股票池（修正生存者偏差）",
                value=True,
            ),
        ], id="wf-pit-col", xs=12, md=3, className="mb-2",
           style={"display": "none"}),
        dbc.Col([
            html.Label(" ", className="small text-muted mb-1 d-block"),
            dbc.Switch(
                id="wf-bear-filter",
                label="🛡️ 熊市過濾（跳過熊市 Fold）",
                value=False,
            ),
        ], id="wf-bear-filter-col", xs=12, md=3, className="mb-2",
           style={"display": "none"}),
        dbc.Col(
            dbc.Button("🔬 開始驗證", id="wf-btn",
                       color="primary", size="sm", className="w-100 mt-4"),
            xs=6, md=2, className="mb-2",
        ),
    ], className="mb-3"),

    html.Small(id="wf-status", className="text-muted d-block mb-2"),

    dcc.Store(id="wf-job-store", data=None),
    dcc.Store(id="wf-done-store", data=None),
    dcc.Interval(id="wf-progress-interval", interval=800, n_intervals=0, disabled=True),
    html.Div(id="wf-progress-section", className="mb-3"),

    html.Div(id="wf-result"),
], className="p-3")


# ── Callback：策略切換 → 顯示/隱藏自訂面板 ───────────────────────────
@callback(
    Output("wf-custom-panel", "style"),
    Input("wf-strategy",      "value"),
)
def cb_toggle_custom_panel(strategy):
    return {"display": "block"} if strategy == CUSTOM_KEY else {"display": "none"}


# ── Callback：模式切換 → 股票輸入框 ──────────────────────────────────
@callback(
    Output("wf-ticker-col",       "style"),
    Output("wf-total-period",     "options"),
    Output("wf-portfolio-hint",   "style"),
    Output("wf-max-pos-col",      "style"),
    Output("wf-pit-col",          "style"),
    Output("wf-bear-filter-col",  "style"),
    Input("wf-mode",              "value"),
)
def cb_mode_change(mode):
    if mode == "portfolio":
        portfolio_opts = [
            {"label": "2年（緩存）", "value": "2y"},
            {"label": "3年（緩存）", "value": "3y"},
            {"label": "5年（緩存）", "value": "5y"},
        ]
        return {"display": "none"}, portfolio_opts, {}, {}, {}, {}
    return {}, PERIOD_OPTIONS, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}


# ── Callback：開始驗證（啟動 thread）────────────────────────────────
@callback(
    Output("wf-status",            "children"),
    Output("wf-result",            "children"),
    Output("wf-job-store",         "data"),
    Output("wf-progress-interval", "disabled"),
    Output("wf-progress-section",  "children"),
    Output("wf-done-store",        "data",      allow_duplicate=True),
    Input("wf-btn",                "n_clicks"),
    State("wf-strategy",           "value"),
    State("wf-mode",               "value"),
    State("wf-ticker",             "value"),
    State("wf-total-period",       "value"),
    State("wf-is-mo",              "value"),
    State("wf-oos-mo",             "value"),
    State("wf-trade-size",         "value"),
    State("wf-slippage",           "value"),
    State("wf-commission",         "value"),
    State("wf-max-positions",      "value"),
    State("wf-custom-buy",         "value"),
    State("wf-custom-sell",        "value"),
    State("wf-use-pit",            "value"),
    State("wf-bear-filter",       "value"),
    prevent_initial_call=True,
)
def cb_run_wf(n_clicks, strategy, mode, ticker, total_period,
              is_mo, oos_mo, trade_size, slippage, commission, max_positions,
              custom_buy, custom_sell, use_pit, bear_filter):
    job_id = str(uuid.uuid4())
    _job_set(job_id, {
        "status": "running", "fold": 0, "total_folds": 0,
        "current": "初始化...", "created_at": time.time(),
    })
    print(f"[WF] cb_run_wf    job={job_id[:8]} mode={mode} ticker={ticker} strategy={strategy}")

    threading.Thread(
        target=_run_wf_thread,
        args=(job_id, mode, strategy, ticker, total_period, is_mo, oos_mo, trade_size, slippage,
              int(max_positions or 0), commission),
        kwargs={"custom_buy": custom_buy, "custom_sell": custom_sell,
                "use_pit": bool(use_pit or False), "bear_filter": bool(bear_filter or False)},
        daemon=True,
    ).start()

    init_bar = html.Div([
        html.Small("🔬 初始化資料中...", className="text-muted mb-1 d-block"),
        dbc.Progress(value=2, striped=True, animated=True,
                     color="info", style={"height": "22px"}),
    ])
    print(f"[WF] cb_run_wf RET status_msg='⏳ 驗證進行中...' job={job_id[:8]}", flush=True)
    return "⏳ 驗證進行中...", [], job_id, False, init_bar, None


# ── Callback：輪詢進度（輕量，偵測 done 後寫 store，不做重渲染）──────
@callback(
    Output("wf-progress-section",  "children",  allow_duplicate=True),
    Output("wf-progress-interval", "disabled",  allow_duplicate=True),
    Output("wf-status",            "children",  allow_duplicate=True),
    Output("wf-done-store",        "data"),
    Input("wf-progress-interval",  "n_intervals"),
    State("wf-job-store",          "data"),
    prevent_initial_call=True,
)
def cb_poll_progress(n_intervals, job_id):
    short = (job_id[:8] + "...") if job_id else "None"
    print(f"[WF] cb_poll       n={n_intervals} job={short} total_jobs={_job_count()}", flush=True)

    if not job_id:
        return no_update, True, no_update, no_update

    job = _job_get(job_id)
    if job is None:
        return no_update, False, no_update, no_update

    status = job.get("status")
    print(f"[WF] cb_poll       status={status}", flush=True)

    if status == "consumed":
        return no_update, True, no_update, no_update

    if status == "running":
        fold    = job.get("fold", 0)
        total   = job.get("total_folds", 0)
        current = job.get("current", "初始化...")
        pct     = max(2, int(fold / total * 100)) if total > 0 else 2

        if total > 0 and fold > 0:
            label_text = f"正在跑 Fold {fold}/{total}" + (f"，處理 {current}..." if current else "...")
        else:
            label_text = f"初始化資料中... {current}" if current else "初始化資料中..."

        progress_ui = html.Div([
            html.Small(label_text, className="text-muted mb-1 d-block"),
            dbc.Progress(value=pct, label=f"{pct}%" if pct > 5 else "",
                         striped=True, animated=True,
                         color="info", style={"height": "22px"}),
        ])
        return progress_ui, False, "⏳ 驗證進行中...", no_update

    # status == "done"：停 interval，把重渲染交給 cb_render_results
    print(f"[WF] cb_poll DONE  job={short} → hand off to cb_render_results", flush=True)
    done_bar = html.Div([
        html.Small("✅ 計算完成，整理結果中...", className="text-success mb-1 d-block"),
        dbc.Progress(value=100, color="success", style={"height": "22px"}),
    ])
    return done_bar, True, "⏳ 整理結果中...", {"job_id": job_id, "n": n_intervals}


# ── Callback：渲染結果（只吃 done-store，觸發一次，不被 Interval supersede）──
@callback(
    Output("wf-result",           "children",  allow_duplicate=True),
    Output("wf-status",           "children",  allow_duplicate=True),
    Output("wf-progress-section", "children",  allow_duplicate=True),
    Input("wf-done-store",        "data"),
    prevent_initial_call=True,
)
def cb_render_results(done_data):
    if not done_data or not done_data.get("job_id"):
        return no_update, no_update, no_update

    job_id   = done_data["job_id"]
    job_data = _job_get(job_id) or {}
    if job_data.get("status") != "done":
        return no_update, no_update, no_update

    _job_set(job_id, {"status": "consumed",
                      "created_at": job_data.get("created_at", time.time())})

    wf_results   = job_data.get("result")
    is_portfolio = job_data.get("is_portfolio", False)
    err          = job_data.get("error")
    params       = job_data.get("params", {})
    strategy     = params.get("strategy", "")
    ticker       = params.get("ticker", "0700.HK")
    is_mo        = params.get("is_mo", 12)
    oos_mo       = params.get("oos_mo", 6)
    trade_size   = params.get("trade_size", 100_000)
    max_pos      = params.get("max_positions", 0)
    use_pit      = params.get("use_pit", False)

    if err:
        return dbc.Alert(err, color="warning", className="mt-2"), err, []
    if not wf_results:
        msg = "⚠️ 沒有產生任何 Fold，請檢查數據週期或策略設定"
        return dbc.Alert(msg, color="warning", className="mt-2"), msg, []

    try:
        rows     = _build_rows(wf_results)
        ts       = float(trade_size or 100_000)
        is_mo_v  = int(is_mo  or 12)
        oos_mo_v = int(oos_mo or 6)
        n_folds  = len(rows)
        mode_lbl = "投資組合" if is_portfolio else (ticker or "0700.HK").strip().upper()

        verdict     = _verdict_section(rows, is_portfolio, max_pos=max_pos, use_pit=use_pit)
        bar_section = html.Div([
            html.H6("📊 IS vs OOS 平均每筆回報%", className="mb-1"),
            dcc.Graph(figure=_bar_chart(rows), config={"displayModeBar": False}),
        ], className="mb-3")
        deg_section = html.Div([
            html.H6("📉 退化率趨勢（灰=無效 Fold／IS≈0）", className="mb-1"),
            dcc.Graph(figure=_deg_chart(rows), config={"displayModeBar": False}),
        ], className="mb-3")
        oos_section = html.Div([
            html.H6("📈 OOS 拼接資金曲線（僅有效 Fold）", className="mb-1"),
            dcc.Graph(figure=_oos_equity_chart(wf_results, ts),
                      config={"displayModeBar": False}),
        ], className="mb-3")
        # ★ 補回延伸追蹤 + survivorship bias 警示（遷移時漏掉的守門員）
        extended_section = _extended_section(wf_results, rows)
        fold_section = html.Div([
            html.H6(f"📑 逐 Fold 詳細數據（共 {n_folds} 個 Fold）", className="mb-1"),
            _fold_table(rows),
        ], className="mb-3")
        # ★ AUDIT-G 🟡-4：逐 Fold 交易明細（策略出場 / 強制平倉 / 延伸追蹤三表）
        per_fold_detail = _per_fold_detail_section(wf_results, is_portfolio)
        stock_section = _per_stock_section(wf_results, ts) if is_portfolio else html.Div()

        status_str = (f"✅ {mode_lbl} | {strategy} | "
                      f"IS {is_mo_v}月 × OOS {oos_mo_v}月 | {n_folds} 個 Fold")
        done_bar = html.Div([
            html.Small(f"✅ 驗證完成：{n_folds} 個 Fold", className="text-success mb-1 d-block"),
            dbc.Progress(value=100, color="success", style={"height": "22px"}),
        ])
        result_children = [*verdict, bar_section, deg_section,
                           oos_section, extended_section,
                           stock_section, fold_section, per_fold_detail]
        print(f"[WF] cb_render_results OK  folds={n_folds} children={len(result_children)}", flush=True)
        return result_children, status_str, done_bar

    except Exception as e:
        print(f"[WF] cb_render_results ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return (dbc.Alert([html.Strong("❌ 結果渲染失敗"), html.Br(), html.Code(str(e))],
                          color="danger", className="mt-2"),
                str(e), [])
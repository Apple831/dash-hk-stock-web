"""
paper_ledger 本地單元測試（不碰 GitHub，用假 trades + mock price_fn/sig_fn）。

執行：python scripts/test_paper_ledger.py
驗證對齊 WF 的關鍵不變量：
  1. T+1 + 假期：pending_buy 無更晚 bar 不成交；有更晚 bar 才成交且含 +0.0023 成本。
  2. min_hold：未滿 5 交易日（bar 數）即使 s2=真也不出場。
  3. 滿 5 + s2 → pending_sell（T+1）→ 下一交易日開盤平倉，return_pct 含雙邊成本、hold_bars=days+1。
  4. 去重：同 ticker+同策略已有 open/pending_buy 不重複開；不同策略可並存；id 冪等。
  5. summarize：by_resonance / by_strategy 分組正確；空集合不 crash。
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paper_ledger as pl

# ── 迷你測試框架 ──────────────────────────────────────────────────────────────
_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ✅ {msg}")
    else:
        _FAIL += 1
        print(f"  ❌ {msg}")


def approx(a, b, tol=1e-6) -> bool:
    return abs(a - b) < tol


def make_price_fn(table: dict):
    """table: {ticker: {'date': date, 'open': float}}"""
    return lambda ticker: table.get(ticker)


def make_sig_fn(table: dict):
    """table: {ticker: {'date': date, 's2': bool, 'dates': [date,...]}}"""
    return lambda ticker: table.get(ticker)


# ══════════════════════════════════════════════════════════════════════════════
def test_pending_buy_t1_and_holiday():
    print("\n[Test 1] pending_buy：假期不成交 / 次日開盤才成交（含 +0.0023 成本）")
    trades = [pl._new_trade("0700.HK|💎 S1|2026-05-29", "0700.HK", "💎 S1", 1, "2026-05-29")]

    # (a) 最新 bar 日期 == signal_date（同日 / 假期無更晚 bar）→ 不成交
    price_fn = make_price_fn({"0700.HK": {"date": date(2026, 5, 29), "open": 10.0}})
    pl.process_pending_buys(trades, price_fn)
    check(trades[0]["status"] == "pending_buy", "無更晚 bar → 仍為 pending_buy（未洩漏未來）")
    check(trades[0]["entry_px"] is None, "未成交 → entry_px 仍為 None")

    # (b) 出現嚴格更晚的 bar（次一交易日）→ 用該日開盤成交
    price_fn = make_price_fn({"0700.HK": {"date": date(2026, 6, 1), "open": 10.0}})
    pl.process_pending_buys(trades, price_fn)
    check(trades[0]["status"] == "open", "有更晚 bar → 成交 status=open")
    check(approx(trades[0]["entry_px"], 10.023), f"entry_px = 10*(1+0.0023) = 10.023（實際 {trades[0]['entry_px']}）")
    check(trades[0]["entry_date"] == "2026-06-01", "entry_date = 成交當日（次日開盤）")


def test_min_hold_blocks_sell():
    print("\n[Test 2] open：未滿 5 交易日即使 s2=真也不出場")
    trades = [{
        "id": "0700.HK|💎 S1|2026-05-29", "ticker": "0700.HK", "strategy": "💎 S1",
        "resonance_n": 1, "status": "open", "signal_date": "2026-05-29",
        "entry_date": "2026-06-01", "entry_px": 10.023, "sell_signal_date": None,
        "exit_date": None, "exit_px": None, "return_pct": None, "hold_bars": None,
        "exit_reason": None, "min_hold_days": 5, "trade_size": pl.TRADE_SIZE,
    }]
    # 進場後只過了 3 根 bar（< 5），s2=真
    sig_fn = make_sig_fn({"0700.HK": {
        "date": date(2026, 6, 4), "s2": True,
        "dates": [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4)],
    }})
    price_fn = make_price_fn({"0700.HK": {"date": date(2026, 6, 4), "open": 11.0}})
    pl.process_open_positions(trades, sig_fn, price_fn)
    check(trades[0]["status"] == "open", "bars_held=3 < 5 → 不轉 pending_sell")


def test_sell_t1_and_return():
    print("\n[Test 3] 滿 5 + s2 → pending_sell（T+1）→ 下一交易日平倉，return_pct 含雙邊成本")
    trades = [{
        "id": "0700.HK|💎 S1|2026-05-29", "ticker": "0700.HK", "strategy": "💎 S1",
        "resonance_n": 1, "status": "open", "signal_date": "2026-05-29",
        "entry_date": "2026-06-01", "entry_px": 10.023, "sell_signal_date": None,
        "exit_date": None, "exit_px": None, "return_pct": None, "hold_bars": None,
        "exit_reason": None, "min_hold_days": 5, "trade_size": pl.TRADE_SIZE,
    }]
    # 觸發日 today=06-08，進場後實際 5 根 bar（06-02..06-08），s2=真
    sig_fn = make_sig_fn({"0700.HK": {
        "date": date(2026, 6, 8), "s2": True,
        "dates": [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3),
                  date(2026, 6, 4), date(2026, 6, 5), date(2026, 6, 8)],
    }})
    # 觸發當天的 price_fn 日期 == sell_signal_date → 不可同日平倉（T+1 對稱）
    price_same_day = make_price_fn({"0700.HK": {"date": date(2026, 6, 8), "open": 12.0}})
    pl.process_open_positions(trades, sig_fn, price_same_day)
    check(trades[0]["status"] == "pending_sell", "s2 觸發 → pending_sell（當天不平）")
    check(trades[0]["sell_signal_date"] == "2026-06-08", "sell_signal_date = 觸發日")
    check(trades[0]["hold_bars"] == 6, f"hold_bars = days_held(5)+1 = 6（實際 {trades[0]['hold_bars']}）")

    # 次一交易日 06-09 開盤平倉
    price_next = make_price_fn({"0700.HK": {"date": date(2026, 6, 9), "open": 12.0}})
    pl.process_open_positions(trades, sig_fn, price_next)
    check(trades[0]["status"] == "closed", "下一交易日 → 平倉 closed")
    check(approx(trades[0]["exit_px"], 11.9724), f"exit_px = 12*(1-0.0023) = 11.9724（實際 {trades[0]['exit_px']}）")
    check(approx(trades[0]["return_pct"], 19.4493, tol=1e-3),
          f"return_pct = (11.9724-10.023)/10.023*100 ≈ 19.4493（實際 {trades[0]['return_pct']}）")
    check(trades[0]["exit_reason"] == "策略訊號(s2)", "exit_reason = 策略訊號(s2)")


def test_dedup_and_idempotency():
    print("\n[Test 4] 去重：同策略同股不重複開、不同策略可並存、id 冪等")
    trades = [{
        "id": "0700.HK|💎 S1|2026-05-20", "ticker": "0700.HK", "strategy": "💎 S1",
        "resonance_n": 1, "status": "open", "signal_date": "2026-05-20",
        "entry_date": "2026-05-21", "entry_px": 10.0, "sell_signal_date": None,
        "exit_date": None, "exit_px": None, "return_pct": None, "hold_bars": None,
        "exit_reason": None, "min_hold_days": 5, "trade_size": pl.TRADE_SIZE,
    }]
    hits = [{"ticker": "0700.HK", "presets": ["💎 S1", "💎 S2"], "n": 2}]

    pl.record_new_signals(trades, hits, "2026-05-31")
    s1_new = [t for t in trades if t["strategy"] == "💎 S1" and t["status"] == "pending_buy"]
    s2_new = [t for t in trades if t["strategy"] == "💎 S2" and t["status"] == "pending_buy"]
    check(len(s1_new) == 0, "(0700,S1) 已有 open → 不重複開")
    check(len(s2_new) == 1, "(0700,S2) 不同策略 → 新增 pending_buy 並存")
    check(s2_new and s2_new[0]["resonance_n"] == 2, "新單 resonance_n = hit['n'] = 2")

    # 同一天再跑一次（cron 重跑）→ id 已存在，不應再新增
    before = len(trades)
    pl.record_new_signals(trades, hits, "2026-05-31")
    check(len(trades) == before, "同 signal_date 重跑 → id 冪等，不重複建單")


def test_summarize():
    print("\n[Test 5] summarize：分組統計 + 空集合安全")
    def closed(strategy, n, ret, hold):
        return {"id": f"x{ret}", "ticker": "T", "strategy": strategy, "resonance_n": n,
                "status": "closed", "return_pct": ret, "hold_bars": hold}
    trades = [
        closed("💎 S1", 1, 10.0, 6),
        closed("💎 S1", 2, -5.0, 8),
        closed("💎 S2", 1, 3.0, 5),
        {"id": "o", "ticker": "T", "strategy": "💎 S1", "resonance_n": 1, "status": "open"},
        {"id": "p", "ticker": "T", "strategy": "💎 S2", "resonance_n": 1, "status": "pending_buy"},
    ]
    s = pl.summarize(trades)
    check(s["closed_n"] == 3, f"closed_n=3（實際 {s['closed_n']}）")
    check(s["open_n"] == 1, f"open_n=1（實際 {s['open_n']}）")
    check(s["pending_n"] == 1, f"pending_n=1（實際 {s['pending_n']}）")
    check(approx(s["total_return_pct"], 8.0), f"total_return_pct=8.0（實際 {s['total_return_pct']}）")
    check(approx(s["avg_return_pct"], 2.6667, tol=1e-3), f"avg_return_pct≈2.6667（實際 {s['avg_return_pct']}）")
    check(approx(s["win_rate"], 66.7, tol=0.05), f"win_rate=66.7（實際 {s['win_rate']}）")
    check(approx(s["avg_hold_days"], 6.3, tol=0.05), f"avg_hold_days=6.3（實際 {s['avg_hold_days']}）")

    br = s["by_resonance"]
    check(br[1]["n"] == 2 and approx(br[1]["win_rate"], 100.0) and approx(br[1]["avg_ret"], 6.5),
          f"by_resonance[1] = n2/勝率100/均6.5（實際 {br[1]}）")
    check(br[2]["n"] == 1 and approx(br[2]["win_rate"], 0.0) and approx(br[2]["avg_ret"], -5.0),
          f"by_resonance[2] = n1/勝率0/均-5.0（實際 {br[2]}）")

    bs = s["by_strategy"]
    check(bs["💎 S1"]["n"] == 2 and approx(bs["💎 S1"]["win_rate"], 50.0) and approx(bs["💎 S1"]["avg_ret"], 2.5),
          f"by_strategy[S1] = n2/勝率50/均2.5（實際 {bs['💎 S1']}）")
    check(bs["💎 S2"]["n"] == 1 and approx(bs["💎 S2"]["win_rate"], 100.0) and approx(bs["💎 S2"]["avg_ret"], 3.0),
          f"by_strategy[S2] = n1/勝率100/均3.0（實際 {bs['💎 S2']}）")

    empty = pl.summarize([])
    check(empty["closed_n"] == 0 and empty["total_return_pct"] == 0.0 and empty["win_rate"] == 0.0,
          "空帳本 summarize 不 crash、全回 0")
    print("  範例 Telegram 尾巴：", pl.format_ledger_summary(s))


def main():
    print("=" * 70)
    print("paper_ledger 本地測試")
    print("=" * 70)
    test_pending_buy_t1_and_holiday()
    test_min_hold_blocks_sell()
    test_sell_t1_and_return()
    test_dedup_and_idempotency()
    test_summarize()
    print("\n" + "=" * 70)
    print(f"結果：{_PASS} 通過 / {_FAIL} 失敗")
    print("=" * 70)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

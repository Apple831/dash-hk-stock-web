"""
scripts/audit_g_recheck.py — AUDIT-G 收尾複查 / 一次性遷移工具

複查兩件事（皆用 Unicode code point 比對，避開 glyph 肉眼難辨問題）：
  N3：core/config.py 是否殘留舊字「吞噷」(U+5677)。整檔正名為「吞噬」後應為 0。
  N2：data/paper_trades.json 是否有 strategy 仍用舊字「吞噷」的 b14 紀錄；
      若其中有 open / pending，會與新字「吞噬」訊號去重失效（同股同策略開出第二筆）。

預設只「報告」(dry-run)，不改任何檔。
加 --fix-ledger 才會把 paper_trades.json 內舊字 strategy 就地改成新字並寫回。
（config.py 永遠由 Ivan 整檔重寫，本工具只「讀」config.py 檢查，絕不改它。）

執行（repo 根目錄）：
  python scripts/audit_g_recheck.py
  python scripts/audit_g_recheck.py --fix-ledger
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PY   = ROOT / "core" / "config.py"
LEDGER_JSON = ROOT / "data" / "paper_trades.json"

OLD = "\u5677"   # 噷  舊（罕用字，錯）
NEW = "\u566c"   # 噬  新（正字，對）

_OPEN_LIKE = ("open", "pending_buy", "pending_sell")


def check_config() -> int:
    """N3：config.py 不該再有 U+5677。回傳殘留個數（-1 = 找不到檔）。"""
    print("── N3：core/config.py 吞噷/吞噬 一致性 ──")
    if not CONFIG_PY.exists():
        print(f"  ⚠️ 找不到 {CONFIG_PY}（請在 repo 根目錄執行）")
        return -1
    text  = CONFIG_PY.read_text(encoding="utf-8")
    old_n = text.count(OLD)
    new_n = text.count(NEW)
    print(f"  舊字「吞噷」(U+5677)：{old_n} 個")
    print(f"  正字「吞噬」(U+566C)：{new_n} 個")
    if old_n == 0:
        print("  ✅ 無殘留舊字，整檔已一致為「吞噬」")
    else:
        print("  🔴 仍有殘留舊字！逐行列出（key 用舊字會讓 daily_scan 靜默漏推 b14）：")
        for i, line in enumerate(text.splitlines(), 1):
            if OLD in line:
                print(f"    L{i}: {line.strip()}")
    return old_n


def check_ledger(do_fix: bool) -> int:
    """N2：paper_trades.json 內 strategy 仍用舊字的紀錄。回傳命中數（-1 = 讀取失敗）。"""
    print("\n── N2：data/paper_trades.json b14 舊字殘留 ──")
    if not LEDGER_JSON.exists():
        print(f"  ℹ️ 找不到 {LEDGER_JSON}（本地無帳本副本則略過；"
              f"可從 repo data/paper_trades.json pull 下來再跑）")
        return 0
    try:
        trades = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️ 讀取失敗：{type(e).__name__}: {e}")
        return -1
    if not isinstance(trades, list):
        print("  ⚠️ 格式異常（預期 JSON 陣列）")
        return -1

    hits = [t for t in trades if OLD in str(t.get("strategy", ""))]
    if not hits:
        print(f"  ✅ {len(trades)} 筆紀錄無舊字 strategy，無去重旁路風險")
        return 0

    print(f"  ⚠️ 有 {len(hits)} 筆 strategy 仍用舊字「吞噷」：")
    open_like = 0
    for t in hits:
        st   = t.get("status", "")
        is_open = st in _OPEN_LIKE
        open_like += int(is_open)
        flag = "  ← open/pending：與新訊號去重會失效" if is_open else ""
        print(f"    {t.get('ticker','?')} | {t.get('strategy','?')} | {st}{flag}")

    if open_like:
        print(f"  🔴 其中 {open_like} 筆為 open/pending：今天 b14 對同股觸發會被當成不同策略，開出第二筆。")
    else:
        print("  🟡 全為 closed：僅影響 by_strategy 顯示（新舊各一列），無去重風險。")

    if do_fix:
        for t in trades:
            s = str(t.get("strategy", ""))
            if OLD in s:
                t["strategy"] = s.replace(OLD, NEW)
        LEDGER_JSON.write_text(
            json.dumps(trades, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✅ 已就地把 {len(hits)} 筆 strategy 的舊字改成「吞噬」並寫回。")
        print("     請 git commit + push data/paper_trades.json（下次 daily_scan 讀新檔）。")
    else:
        print("  ▶ 加 --fix-ledger 可一次性把這些舊字 strategy 改成「吞噬」。")
    return len(hits)


def main() -> int:
    do_fix = "--fix-ledger" in sys.argv
    print("=" * 60)
    print("AUDIT-G 收尾複查（N2 帳本去重 / N3 config 吞噷殘留）")
    print("=" * 60)
    n3 = check_config()
    n2 = check_ledger(do_fix)
    print("\n" + "=" * 60)
    if n3 == 0 and n2 == 0:
        print("🟢 兩項皆乾淨：N3 config 無殘留、N2 帳本無舊字。")
        return 0
    print("🟡/🔴 見上方明細（N3>0 或 N2>0）。")
    return 1


if __name__ == "__main__":
    sys.exit(main())

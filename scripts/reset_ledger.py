"""
reset_ledger.py -- 實盤 Paper-Trading 帳本 reset（V22.2 Phase 4 路線 A 收尾）

為什麼要 reset：
  • 既有持倉是用「舊的純 s2 邏輯」開立的，且實盤白名單已清空（LIVE_PRESET_KEYS=set()），
    這些舊單在新口徑下不該繼續累積。
  • benchmark 已從「頂部 WF OOS」轉為「真實出場%（延伸追蹤）」，舊紀錄口徑不一致。
  → 清空帳本，從乾淨狀態重起（未來若有策略復活再開始記錄）。

安全設計：
  • 用 GitHub Contents API（複用 paper_ledger 同一條讀寫路徑），不手改 JSON。
  • reset 前先把現有帳本「完整備份到本地」一份（萬一要回溯）。
  • 需手動輸入 RESET 確認才執行（防誤觸）。
  • GH_TOKEN / GH_REPO 必須在環境變數中（與 daily_scan / Render 同）。

使用：
  cd 專案根目錄
  set GH_TOKEN=...    （PowerShell: $env:GH_TOKEN="..."）
  set GH_REPO=Apple831/dash-hk-stock-web
  python scripts/reset_ledger.py
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paper_ledger as pl


def _status_breakdown(trades: list) -> str:
    from collections import Counter
    c = Counter(t.get("status", "?") for t in trades)
    return " ｜ ".join(f"{k}: {v}" for k, v in sorted(c.items())) or "（空）"


def main() -> int:
    print("═" * 70)
    print("  實盤帳本 RESET — V22.2 Phase 4 路線 A")
    print("═" * 70)

    # 1. 環境檢查
    if not pl.is_enabled():
        print("\n❌ 未偵測到 GH_TOKEN / GH_REPO 環境變數，無法存取帳本。")
        print("   請先設定（與 daily_scan / Render 同一組）：")
        print("     PowerShell: $env:GH_TOKEN=\"...\"; $env:GH_REPO=\"Apple831/dash-hk-stock-web\"")
        return 1

    _, repo = pl._gh_env()
    print(f"\n目標：{repo} / {pl.LEDGER_PATH}")

    # 2. 讀現有帳本
    trades, sha = pl.load_ledger()
    print(f"\n現有帳本：{len(trades)} 筆")
    print(f"  狀態分佈：{_status_breakdown(trades)}")
    if sha is None and not trades:
        print("\nℹ️ 帳本已是空的（或不存在），無須 reset。")
        return 0

    # 3. 本地備份（時間戳）
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data",
        f"paper_trades.backup.{ts}.json",
    )
    try:
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已備份現有帳本到本地：{os.path.normpath(backup_path)}")
    except Exception as e:
        print(f"\n⚠️ 本地備份失敗（{type(e).__name__}: {e}）。")
        ans = input("   無備份仍要繼續 reset？(yes/no) ").strip().lower()
        if ans != "yes":
            print("已取消。")
            return 1

    # 4. 確認
    print("\n" + "─" * 70)
    print("⚠️ 即將把 GitHub 上的帳本清空為 []（不可逆，但已本地備份）。")
    confirm = input("   輸入大寫 RESET 確認執行，其他任意鍵取消：").strip()
    if confirm != "RESET":
        print("已取消，帳本未變動。")
        return 0

    # 5. 寫入空帳本（複用 paper_ledger 的 Contents API）
    msg = f"chore(ledger): reset for V22.2 Phase 4 route A downgrade ({ts})"
    ok = pl.save_ledger([], sha, msg)
    if not ok:
        print("\n❌ reset 失敗（save_ledger 回 False，見上方 log）。帳本未變動。")
        return 1

    # 6. 驗證
    new_trades, _ = pl.load_ledger()
    if not new_trades:
        print(f"\n✅ 帳本已清空（commit: {msg}）。")
        print(f"   舊帳本備份：{os.path.normpath(backup_path)}")
        print("   下一步：確認 config.LIVE_PRESET_KEYS 仍為 set()（無策略會在 reset 後立刻重開倉）。")
        return 0
    else:
        print(f"\n⚠️ reset 後仍讀到 {len(new_trades)} 筆，請手動檢查 GitHub 上的檔案狀態。")
        return 1


if __name__ == "__main__":
    sys.exit(main())

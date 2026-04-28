# ══════════════════════════════════════════════════════════════════
# config.py -- 策略組合預設 & 全局常量
# ══════════════════════════════════════════════════════════════════
#
# V18 更新（2026-04-27）-- 來自 V17.0 策略複審報告：
#
# 🔴-2 配套：對照組與 BIAS 策略移到 LEGACY_PRESETS（不參與制度矩陣 / 共振掃描）
#   • cooldown 已在 backtest.py 解耦為獨立參數，預設不冷卻
#   • 對照組 [無MIN對照] / [對照] / [BIAS-勿實盤] 不再參與實盤掃描，純歷史紀錄
#   • 主要對外名 STRATEGY_PRESETS 仍保留，現等於 ACTIVE_PRESETS（向後相容）
#
# 新增策略欄位：cooldown_days（可選，獨立於 min_hold_days）
#   • 不設 → 沿用 min_hold_days（v17 行為，向後相容）
#   • 設為 0 → 完全不冷卻（對照組原語意）
#   • 設為其他正整數 → 該值天數冷卻
#   • 「⚡ 突破確認」設為 5 -- 強牛市可連續突破時加倉（不被 30 天冷卻擋掉）
#
# ⚠️ 重要：本檔策略 desc 內的 WF / 延伸 / 退化率數字皆來自 V17 之前的引擎，
#         在 V18 修復後（cooldown 解耦、持倉天數 +1、equity 時序）數字會變動。
#         必須重跑 WF 才能信任。建議在重跑前把 desc 視為「V17 歷史數字」。
#
# 每個策略 dict 欄位：
#   desc           - UI 顯示的策略說明
#   buy            - 11 個買入信號的 tuple (b1~b11)
#   sell           - 8 個賣出信號的 tuple (s1~s8)
#   min_hold_days  - (可選) 策略級最小持倉天數
#   cooldown_days  - (可選) 同股加倉冷卻期（V18 新增）
#
# buy  tuple 順序：b1  b2  b3  b4  b5  b6  b7  b8  b9  b10  b11
# sell tuple 順序：s1  s2  s3  s4  s5  s6  s7  s8

# ══════════════════════════════════════════════════════════════════
# ACTIVE_PRESETS -- 實盤候選 / 推薦策略
# 用於：制度矩陣全跑、共振掃描、Tab 推薦清單
# ══════════════════════════════════════════════════════════════════

ACTIVE_PRESETS = {

    # ── 1. 💎+s2 M30 三重出場版【實盤主力冠軍】───────────────────
    "💎+s2 M30 三重出場版【實盤冠軍】": {
        "desc": "【🏆 實盤主力冠軍】b6 (RSI<30) 進場，s2+s6+s8 三重出場（布林上軌 / MACD死叉 / KDJ高位死叉），最少持倉30天。"
                "V17 數字：WF +7.67% / 延伸 +12.68% / 樣本 2126 / 勝率 69.2% / 退化率 -2.5%。"
                "⚠️ V18 修復後（持倉天數 +1、equity T+1 時序）需重跑驗證。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        # cooldown 不設 → 沿用 min_hold_days = 30（v17 行為）
    },

    # ── 2. 💎+ M30 RSI 進雙出 MIN30 ──────────────────────────────
    "💎+ M30 RSI進雙出MIN30": {
        "desc": "【實盤候選】b6 進場，s6+s8 雙出場，MIN30。V17 數字：WF +6.80% / 延伸 +15.07% / 樣本 2339 / 勝率 68.6%。"
                "比 💎M30 略強，可作冠軍進取版。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 3. 💎M30 純粹均值回歸 MIN30 ──────────────────────────────
    "💎M30 純粹均值回歸MIN30": {
        "desc": "【實盤候選】RSI<30 買入，MACD死叉出，最少持倉30天。V17 數字：WF +6.56% / 延伸 +15.89% / 樣本 2379 / 勝率 69.7%。"
                "經典基準策略，邏輯最簡單。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 4. 🔄🔄M30 均值回歸長持 MIN30 ────────────────────────────
    "🔄🔄M30 均值回歸長持MIN30": {
        "desc": "【實盤組合】布林下軌+RSI超賣，MACD死叉出，最少持倉30天。V17 數字：WF +5.42% / 延伸 +15.00% / 樣本 871。"
                "比 💎M30 更挑剔但同等強，可分散搭配。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 5. ⚡ 突破確認（強牛市專用，V18 解鎖加倉）─────────────────
    "⚡ 突破確認": {
        "desc": "【強牛市專用】突破放量+趨勢確認，跌破MA20或放量急跌出。V17 數字：WF +1.21% / 延伸 +7.11%。"
                "🆕 V18：cooldown 從 30 改為 5 天，強牛市連續突破可加倉（V17 數字基於可加倉舊版，V18 重跑數字應該回升）。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False),
        "sell": (True,  False, False, True,  False, False, False, False),
        # 🔴-2 V18：突破策略需要連續加倉，cooldown 改 5（一週），不被 30 天綁死
        "cooldown_days": 5,
    },

    # ── 6. 🔄+ MACD+趨勢 MIN30 ──────────────────────────────────
    "🔄+ MACD+趨勢MIN30": {
        "desc": "【趨勢市備用】MACD金叉+趨勢確認，MACD死叉出，MIN30。V17 數字：WF +4.80% / 延伸 +4.92%。"
                "WF≈延伸無 bias，數字真實可信。",
        "buy":  (False, False, False, False, False, False, True,  True,  False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 7. 💎K+ M30 雙超賣雙出 MIN30 ─────────────────────────────
    "💎K+ M30 雙超賣雙出MIN30 [精選]": {
        "desc": "【🎯 精選股策略】b6+b11 進場，s6+s8 雙出場，MIN30。V17 數字：WF +5.73% / 延伸 +21.76% / 樣本 133。"
                "完整 KDJ 強化版，樣本少但延伸極高。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 8. 💎KK30 RSI+KDJ 雙超賣 MIN30 ───────────────────────────
    "💎KK30 RSI+KDJ雙超賣MIN30 [精選]": {
        "desc": "【🎯 精選股策略】b6+b11 進場，MACD死叉出，MIN30。V17 數字：WF +5.08% / 延伸 +21.99% / 樣本 133。"
                "雙重超賣確認，適合資金有限時。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

}


# ══════════════════════════════════════════════════════════════════
# LEGACY_PRESETS -- 對照組 / 已驗證 BIAS（純歷史紀錄）
# 不參與：制度矩陣、共振掃描推薦
# 仍可在 Tab 的「自定義」/「預設」下拉選單中手動選擇查看
# ══════════════════════════════════════════════════════════════════

LEGACY_PRESETS = {

    # ── 對照組：沒有 MIN 限制（V18 cooldown_days=0 恢復原語意）────

    "💎 純粹均值回歸 [對照]": {
        "desc": "【📚 LEGACY 對照組】純粹的 b6/s6，無 MIN 限制。V17 數字：WF +4.91% / 延伸 +12.55%。"
                "🆕 V18：cooldown_days=0（恢復原語意，與 💎M30 對照證明 MIN30 alpha）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎+s2 三重出場 [無MIN對照]": {
        "desc": "【📚 LEGACY 對照組】b6/s2+s6+s8 無 MIN。V17 數字：WF +3.81% / 延伸 +10.64% / 樣本 885。"
                "🆕 V18：cooldown_days=0（恢復原語意）。對照冠軍 💎+s2 M30 證明 MIN30 alpha。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "cooldown_days": 0,
    },

    "💎M20 純粹均值回歸MIN20 [對照]": {
        "desc": "【📚 LEGACY MIN 參數對照】b6/s6 MIN20。V17 數字：WF +3.52% / 延伸 +16.47%。"
                "證實 MIN30 才是最優參數。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 20,
    },

    "🔄基準 純MACD週期 [對照]": {
        "desc": "【📚 LEGACY 對照】純 b7/s6 無任何過濾。V17 數字：WF +0.42% / 延伸 +8.80%。"
                "🆕 V18：cooldown_days=0。對比🔄M30 量化 MIN30 alpha 約 +4.18%。",
        "buy":  (False, False, False, False, False, False, True,  False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎K30 純KDJ超賣MIN30 [已驗證]": {
        "desc": "【📚 LEGACY 已驗證失敗】WF +1.50% / 延伸 +10.46%。KDJ 單獨進場效果遠不如 RSI。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, True),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 已驗證 BIAS（教訓紀錄，勿實盤）────────────────────────────

    "📈 均值回歸 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS 警示】WF +10.33% 看似最高，但延伸僅 +3.81%（49.8% 勝率）。"
                "Survivorship bias 案例：高 OOS 數字只統計『跑完全程』的贏家。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False),
        "sell": (False, True,  False, False, True,  False, False, False),
        "cooldown_days": 0,
    },

    "🏗️M30 底部形態MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】底部突破+MACD金叉 MIN30。WF +6.53% 但延伸僅 +2.19%（49.1% 勝率）。"
                "MIN30 強行抓底部假突破，底部形態類不適合 MIN。",
        "buy":  (False, False, False, True,  False, False, True,  False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡+ 突破確認長持MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b1+b8 + MACD死叉 + MIN30。WF +6.20% / 延伸僅 +3.82%。WF 數字過於樂觀。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "💎++ M30 趨勢過濾版 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY 嚴重過擬合】b6+b8 進場，s6+s8 雙出場，MIN30。WF 僅 +0.22% / 退化率 90.5% / 樣本暴跌至 126。"
                "教訓：b6（RSI<30）通常出現在下跌中，此時 b8 不成立，邏輯互斥。",
        "buy":  (False, False, False, False, False, True,  False, True,  False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

}


# ══════════════════════════════════════════════════════════════════
# 對外名稱（向後相容）
# ══════════════════════════════════════════════════════════════════
# STRATEGY_PRESETS 仍存在，預設等於 ACTIVE + LEGACY 的合併（讓 UI 下拉選單看得到全部，
# 但 _ALL = ACTIVE + LEGACY，兩者由各 Tab 自行判斷如何使用）。
# tab_regime_matrix 和 tab_multi_scan 會 import 各自需要的子集。

STRATEGY_PRESETS = {**ACTIVE_PRESETS, **LEGACY_PRESETS}

PRESET_NAMES  = ["✏️ 自定義"] + list(STRATEGY_PRESETS.keys())
PRESET_CUSTOM = "✏️ 自定義"

BUY_LABELS = [
    "①突破放量", "②MA5金叉", "③底背離", "④底部突破",
    "⑤布林下軌", "⑥RSI超賣", "⑦MACD金叉", "⑧趨勢確認",
    "⑨52週新高", "⑩縮量回調", "⑪KDJ超賣金叉",
]
SELL_LABELS = [
    "⑫頭部破MA20", "⑬布林上軌", "⑭縮量頂部", "⑮放量急跌",
    "⑯RSI超買", "⑰MACD死叉", "⑱三日陰線", "⑲KDJ高位死叉",
]

B_NAMES = ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9", "b10", "b11"]
S_NAMES = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]

# TradingView Screener
TV_URL = "https://scanner.tradingview.com/hongkong/scan"
TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Origin":  "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}

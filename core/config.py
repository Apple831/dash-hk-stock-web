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
#
# V18 WF 已重跑（2026-05-09）：desc 內 "V18 數字" 為 1y 引擎結果
#   is_months=12, oos_months=6, trade_size=100000, slippage=0.001
#   股票池：180 隻
#
# V18-5Y WF 重跑（2026-05-09）：desc 內 "V18-5Y 數字" 為 5 年 Close 成交引擎結果
#   is_months=18, oos_months=6, trade_size=100000, slippage=0.001
#   股票池：180 隻（5 年歷史，平均 1164 K 線；10 隻數據不足 < 750 根仍納入）
#
# V18-5Y-Open WF 重跑（2026-05-09）：desc 內 "V18-5Y-Open 數字" 為 Open 成交引擎結果
#   is_months=18, oos_months=6, trade_size=100000, slippage=0.001
#   股票池：170 隻（< 750 根排除）
#
# V18-5Y 複審（2026-05-09）：
#   • 🔄+ MACD+趨勢MIN30 移至 LEGACY（IS +0.22%，退化 -194.2%，IS 靠運氣非 alpha）
#   • REGIME_RECOMMENDATIONS 強牛市 / 弱牛市 的 MACD+趨勢 改為 💎M30
#
# V18-5Y-Open 複審（2026-05-10）：
#   • 💎K+ M30 / 💎KK30 移至 LEGACY（退化率 > -278%，OOS 非策略 alpha）
#   • ACTIVE_PRESETS 剩 5 個策略
#
# V18-5Y-Open 複審（2026-05-10，第二次）：
#   • ⚡ 突破確認 移至 LEGACY（5Y avgIS=-0.21%，手續費拆分後 IS 轉負，無真實 alpha）
#   • ACTIVE_PRESETS 剩 4 個策略
#
# V18 新訊號（2026-05-10）：
#   • b9 重新定義為「相對強弱」——恆指大跌後個股抗跌 + 恆指MA5金叉MA20
#   • 新增「🔬 相對強弱測試」策略，待 WF 驗證
#
# V18 新訊號（2026-05-10，第三次）：
#   • b12 定義為「資金流向」——MA20下方大量（2-8倍均量）陽燭
#   • 新增「🔬 資金流向測試」策略，待 WF 驗證
#   • SELL_LABELS 由 ⑫-⑲ 改為 ⑬-⑳（避免與 b12 的 ⑫ 衝突）
#   • 所有 buy tuple 由 11 元素擴充為 12 元素
#
# V18 季節性測試（2026-05-10）：
#   • 新增 seasonal_filter 欄位（bool）：True 時 run_backtest 限定 1/4/10 月入場
#   • 新增「🔬 冠軍+季節性」與「🔬 均值回歸+季節性」兩個測試策略
#
# 每個策略 dict 欄位：
#   desc            - UI 顯示的策略說明
#   buy             - 12 個買入信號的 tuple (b1~b12)
#   sell            - 8 個賣出信號的 tuple (s1~s8)
#   min_hold_days   - (可選) 策略級最小持倉天數
#   cooldown_days   - (可選) 同股加倉冷卻期（V18 新增）
#   seasonal_filter - (可選) True = 限定 1/4/10 月入場（V18 季節性測試新增）
#
# buy  tuple 順序：b1  b2  b3  b4  b5  b6  b7  b8  b9  b10  b11  b12
# sell tuple 順序：s1  s2  s3  s4  s5  s6  s7  s8

# ══════════════════════════════════════════════════════════════════
# ACTIVE_PRESETS -- 實盤候選 / 推薦策略（共 8 個）
# 用於：制度矩陣全跑、共振掃描、Tab 推薦清單
# ══════════════════════════════════════════════════════════════════

ACTIVE_PRESETS = {

    # ── 1. 💎+s2 M30 三重出場版【實盤主力冠軍】───────────────────
    "💎+s2 M30 三重出場版【實盤冠軍】": {
        "desc": "【🏆 實盤主力冠軍】b6 (RSI<30) 進場，s2+s6+s8 三重出場（布林上軌 / MACD死叉 / KDJ高位死叉），最少持倉30天。"
                "V18 數字：OOS +13.64% / 退化 -85.2% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +5.86% / 退化 -84.2% / 正Fold 100%。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        # cooldown 不設 → 沿用 min_hold_days = 30（v17 行為）
    },

    # ── 2. 💎+ M30 RSI 進雙出 MIN30 ──────────────────────────────
    "💎+ M30 RSI進雙出MIN30": {
        "desc": "【實盤候選】b6 進場，s6+s8 雙出場，MIN30。V18 數字：OOS +13.70% / 退化 -91.3% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +7.06% / 退化 -43.1% / 正Fold 100%。"
                "比 💎M30 略強，可作冠軍進取版。"
                "✅ Open版 OOS +7.06%，改Open後升幅最大（+1.79%），進取版首選。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 3. 💎M30 純粹均值回歸 MIN30 ──────────────────────────────
    "💎M30 純粹均值回歸MIN30": {
        "desc": "【實盤候選】RSI<30 買入，MACD死叉出，最少持倉30天。V18 數字：OOS +13.94% / 退化 -131.7% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +5.15% / 退化 -20.2% / 正Fold 60%。"
                "✅ Open版退化率最低（-20.2%），全部策略中最可信，邏輯最簡單，首選實盤基準。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 4. 🔄🔄M30 均值回歸長持 MIN30 ────────────────────────────
    "🔄🔄M30 均值回歸長持MIN30": {
        "desc": "【實盤組合】布林下軌+RSI超賣，MACD死叉出，最少持倉30天。V18 數字：OOS +9.30% / 退化 -252.1% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +6.12% / 退化 -83.6% / 正Fold 100%。"
                "比 💎M30 更挑剔但同等強，可分散搭配。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 5. 🔬 相對強弱測試（V18 新訊號，待 WF 驗證）──────────────
    "🔬 相對強弱測試": {
        "desc": "【🧪 測試中】V18 新訊號：b9 相對強弱——恆指15日跌>5%，個股跌幅<恆指×0.5，恆指MA5金叉MA20。"
                "sell 沿用冠軍三重出場（s2+s6+s8），最少持倉30天，待 WF 驗證。",
        "buy":  (False, False, False, False, False, False, False, False, True, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 6. 🔬 資金流向測試（V18 新訊號，待 WF 驗證）──────────────
    "🔬 資金流向測試": {
        "desc": "【🧪 測試中】V18 新訊號：b12 資金流向——股價在MA20下方，成交量為均量2-8倍，陽線收盤。"
                "sell 沿用冠軍三重出場（s2+s6+s8），最少持倉30天，待 WF 驗證。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, True),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 7. 🔬 冠軍+季節性（V18 季節性測試，待 WF 驗證）──────────
    "🔬 冠軍+季節性": {
        "desc": "V18 季節性測試：冠軍策略限定1/4/10月入場，待 WF 驗證",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    # ── 8. 🔬 均值回歸+季節性（V18 季節性測試，待 WF 驗證）───────
    "🔬 均值回歸+季節性": {
        "desc": "V18 季節性測試：均值回歸限定1/4/10月入場，待 WF 驗證",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
        "seasonal_filter": True,
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
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎+s2 三重出場 [無MIN對照]": {
        "desc": "【📚 LEGACY 對照組】b6/s2+s6+s8 無 MIN。V17 數字：WF +3.81% / 延伸 +10.64% / 樣本 885。"
                "🆕 V18：cooldown_days=0（恢復原語意）。對照冠軍 💎+s2 M30 證明 MIN30 alpha。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "cooldown_days": 0,
    },

    "💎M20 純粹均值回歸MIN20 [對照]": {
        "desc": "【📚 LEGACY MIN 參數對照】b6/s6 MIN20。V17 數字：WF +3.52% / 延伸 +16.47%。"
                "證實 MIN30 才是最優參數。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 20,
    },

    "🔄基準 純MACD週期 [對照]": {
        "desc": "【📚 LEGACY 對照】純 b7/s6 無任何過濾。V17 數字：WF +0.42% / 延伸 +8.80%。"
                "🆕 V18：cooldown_days=0。對比🔄M30 量化 MIN30 alpha 約 +4.18%。",
        "buy":  (False, False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎K30 純KDJ超賣MIN30 [已驗證]": {
        "desc": "【📚 LEGACY 已驗證失敗】WF +1.50% / 延伸 +10.46%。KDJ 單獨進場效果遠不如 RSI。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, True,  False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── V18-5Y 複審移入 LEGACY ──────────────────────────────────
    "🔄+ MACD+趨勢MIN30 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-09】MACD金叉+趨勢確認，MACD死叉出，MIN30。"
                "V18 數字：OOS +7.37% / 退化 -10.5% / 正Fold 67%。"
                "V18-5Y 數字：OOS +4.14% / 退化 -194.2% / 正Fold 67%。"
                "5Y 下 IS 僅 +0.22%，IS 表現靠運氣非策略 alpha，移出實盤候選。",
        "buy":  (False, False, False, False, False, False, True,  True,  False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── V18-5Y-Open 複審移入 LEGACY ─────────────────────────────
    # ⚡ 突破確認：IS avgIS -0.21%（手續費拆分後轉負），無真實 alpha，2026-05-10 降級
    "⚡ 突破確認 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】強牛市突破策略。"
                "V18 數字：OOS +2.79% / 退化 -78.3% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +1.62% / 退化 -215.1% / 正Fold 83%。"
                "5Y 手續費拆分後 avgIS=-0.21%（IS 轉負），無真實 alpha，降級至 LEGACY。"
                "🆕 V18：cooldown_days=5 保留（連續突破加倉邏輯）。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False),
        "sell": (True,  False, False, True,  False, False, False, False),
        "cooldown_days": 5,
    },

    "💎K+ M30 雙超賣雙出MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】退化率 -313.7%（> -300% 門檻），5Y OOS 靠運氣非策略 alpha，移出實盤候選。"
                "V18 數字：OOS +15.03% / 退化 -728.6% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +15.67% / 退化 -313.7% / 正Fold 100%。"
                "完整 KDJ 強化版，OOS 遠超 IS（市場配合時表現極佳，但 IS 靠運氣）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "💎KK30 RSI+KDJ雙超賣MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】退化率 -278.5%（> -300% 近邊界且精選股樣本稀少），5Y OOS 靠運氣非策略 alpha，移出實盤候選。"
                "V18 數字：OOS +13.68% / 退化 -535.2% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +15.17% / 退化 -278.5% / 正Fold 100%。"
                "雙重超賣確認，適合資金有限時觀察用。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 已驗證 BIAS（教訓紀錄，勿實盤）────────────────────────────

    "📈 均值回歸 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS 警示】WF +10.33% 看似最高，但延伸僅 +3.81%（49.8% 勝率）。"
                "Survivorship bias 案例：高 OOS 數字只統計『跑完全程』的贏家。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, True,  False, False, False),
        "cooldown_days": 0,
    },

    "🏗️M30 底部形態MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】底部突破+MACD金叉 MIN30。WF +6.53% 但延伸僅 +2.19%（49.1% 勝率）。"
                "MIN30 強行抓底部假突破，底部形態類不適合 MIN。",
        "buy":  (False, False, False, True,  False, False, True,  False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡+ 突破確認長持MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b1+b8 + MACD死叉 + MIN30。WF +6.20% / 延伸僅 +3.82%。WF 數字過於樂觀。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "💎++ M30 趨勢過濾版 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY 嚴重過擬合】b6+b8 進場，s6+s8 雙出場，MIN30。WF 僅 +0.22% / 退化率 90.5% / 樣本暴跌至 126。"
                "教訓：b6（RSI<30）通常出現在下跌中，此時 b8 不成立，邏輯互斥。",
        "buy":  (False, False, False, False, False, True,  False, True,  False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

}


# ══════════════════════════════════════════════════════════════════
# REGIME_RECOMMENDATIONS -- 8 制度 → 推薦策略對照表
# 弱熊市 / 強熊市 設為空 list，視為實盤禁區
# ══════════════════════════════════════════════════════════════════

REGIME_RECOMMENDATIONS = {
    "強牛市":  [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎M30 純粹均值回歸MIN30",
    ],
    "弱牛市":  [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎M30 純粹均值回歸MIN30",
    ],
    "牛市警惕": [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎M30 純粹均值回歸MIN30",
    ],
    "熊市觀察": [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎M30 純粹均值回歸MIN30",
    ],
    "弱熊市":  [],   # 實盤禁區
    "強熊市":  [],   # 實盤禁區
    "震盪市":  [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎+ M30 RSI進雙出MIN30",
        "💎M30 純粹均值回歸MIN30",
        "🔄🔄M30 均值回歸長持MIN30",
    ],
    "轉折期":  [
        "💎+s2 M30 三重出場版【實盤冠軍】",
        "💎M30 純粹均值回歸MIN30",
    ],
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
    "⑨相對強弱", "⑩縮量回調", "⑪KDJ超賣金叉", "⑫資金流向",
]
SELL_LABELS = [
    "⑬頭部破MA20", "⑭布林上軌", "⑮縮量頂部", "⑯放量急跌",
    "⑰RSI超買", "⑱MACD死叉", "⑲三日陰線", "⑳KDJ高位死叉",
]

B_NAMES = ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9", "b10", "b11", "b12"]
S_NAMES = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]

# TradingView Screener
TV_URL = "https://scanner.tradingview.com/hongkong/scan"
TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Origin":  "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}

# ── 系統常數 ────────────────────────────────────────────────────────────────
MIN_BARS_FOR_INDICATORS = 62        # MA60 + 2 根 warmup

REGIME_HISTORY_BARS = 120           # banner 最多回看天數

# Walk-Forward 評估門檻（上次人工調整後確認的數值，勿輕易修改）
WF_ROBUST_MAX_DEGRADATION   = 40.0  # % 退化率 < 40 = 健康
WF_ROBUST_MIN_OOS_POS_RATE  = 60.0  # % OOS 正回報 fold 比率
WF_WARNING_MAX_DEGRADATION  = 65.0  # %
WF_WARNING_MIN_OOS_POS_RATE = 50.0  # %
WF_MIN_IS_RETURN_FOR_CALC   = 0.5   # % IS 絕對值 < 0.5 不計退化率

# ── 交易成本常數 ─────────────────────────────────────────────────────────────
# 港股單邊真實成本：印花稅 0.1% + 交易費 0.005% + 結算費 0.002% + 佣金約 0.03% ≈ 0.13%
COMMISSION_PCT = 0.0026   # 雙邊手續費（單邊 0.13% × 2）
SLIPPAGE_PCT   = 0.001    # 單邊滑點（市場衝擊成本，買賣各扣一次）

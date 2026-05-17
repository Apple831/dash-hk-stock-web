# ══════════════════════════════════════════════════════════════════
# config.py -- 策略組合預設 & 全局常量
# ══════════════════════════════════════════════════════════════════
#
# V19 PIT 驗證結果（2026-05-17）：
#   • 💎 b17 ROC超跌反彈 PIT WF 通過（OOS +8.73% / 退化 -141.8% / 正Fold 7/7）
#   • 💎 b18 Z-Score資金流向 PIT WF 通過（OOS +7.09% / 退化 -118.9% / 正Fold 6/6）
#   • 🔬 b18+b6 Z-Score超賣 維持待觀察（Fold2/7 各僅1筆，樣本不足）
#   • ACTIVE_PRESETS 現共 17 個策略（9個💎 + 8個🔬）
#
# V18 更新（2026-04-27）-- 來自 V17.0 策略複審報告：
#
# 🔴-2 配套：對照組與 BIAS 策略移到 LEGACY_PRESETS（不參與制度矩陣 / 共振掃描）
#   • cooldown 已在 backtest.py 解耦為獨立參數，預設不冷卻
#   • 對照組 [無MIN對照] / [對照] / [BIAS-勿實盤] 不再參與實盤掃描，純歷史紀錄
#   • 主要對外名 STRATEGY_PRESETS 仍保留,現等於 ACTIVE_PRESETS（向後相容）
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
#   • b12 定義為「資金流向」——MA20下方大量（2-8倍均量）陽燭
#   • 新增「🔬 資金流向測試」策略，待 WF 驗證
#   • SELL_LABELS 由 ⑫-⑲ 改為 ⑬-⑳（避免與 b12 的 ⑫ 衝突）
#   • 所有 buy tuple 由 11 元素擴充為 12 元素
#
# V18 季節性測試（2026-05-10）：
#   • 新增 seasonal_filter 欄位（bool）：True 時 run_backtest 限定 1/4/10 月入場
#   • 新增「🔬 冠軍+季節性」與「🔬 均值回歸+季節性」兩個測試策略
#
# V18 b9 相對強弱複審（2026-05-10）：
#   • 「🔬 相對強弱測試」及所有含 b9 的策略移至 LEGACY
#   • 原因：熊市過濾後訊號過少，AND 邏輯疊加全部❌，放棄
#   • ACTIVE_PRESETS 剩 7 個策略
#
# V18 三組信號測試（2026-05-14）：
#   • 🔬 b12+b6 / 🔬 b11+b5 / 🔬 b3+b7+b8，待 scripts/test_new_strategies.py WF 驗證
#
# V18 WF 驗證結果（2026-05-14）：
#   • 💎 b12+b6 資金流向超賣 PIT OOS +14.07% 5/5正Fold，升格為 💎 策略，加入 ACTIVE_PRESETS
#
# V18 PIT 複審（2026-05-15）：
#   • 💎+s2 M30 冠軍 / 💎M30 / 🔄🔄M30 移至 LEGACY（PIT OOS 正Fold 率 43%，接近隨機）
#   • ACTIVE_PRESETS 剩 8 個策略
#   • REGIME_RECOMMENDATIONS 全清空，僅震盪市/轉折期保留 💎 b12+b6
#
# V18 新訊號（2026-05-15）：
#   • b13 縮量反轉 / b14 低位吞噬 / b15 長下影線
#   • 所有 buy tuple 由 12 元素擴充為 15 元素
#   • 新增三個測試策略 🔬 b13 縮量反轉 / 🔬 b14 低位吞噬 / 🔬 b15 長下影線
#
# V18 PIT 複審（2026-05-15，第二次）：
#   • b13 / b14 / b15 完成 PIT WF 驗證，全部 OOS > IS、正Fold 7/7 / 有效7/7
#   • 🔬 b13 縮量反轉 / 🔬 b14 低位吞噬 / 🔬 b15 長下影線 升格為 💎
#   • REGIME_RECOMMENDATIONS 補充新 💎 策略至各制度
#
# V19 雙確認測試策略（2026-05-15）：
#   • 新增四個 🔬 雙信號 AND 組合，待 PIT WF 驗證
#   • 🔬 b15+b6 下影線+超賣 / 🔬 b14+b6 吞噬+超賣
#   • 🔬 b13+b6 縮量反轉+超賣 / 🔬 b15+b12 下影線+資金流向
#   • 均使用 s2（布林上軌）出場，MIN5
#   • ACTIVE_PRESETS 共 15 個策略
#
# V19 b16 新訊號（2026-05-15）：
#   • b16 長下影線+資金流入（b15 形態 + 放量確認，量門檻放寬：1.5x-12x）
#   • 取代 🔬 b15+b12 下影線+資金流向（AND 邏輯，量門檻 2x-8x）
#   • 所有 buy tuple 由 15 元素擴充為 16 元素
#
# V19 b16 定稿（2026-05-15）：
#   • "🔬 b16 下影線資金流入" 取代 "🔬 b16 長下影線+資金流入"（名稱精簡、desc 更新）
#   • "🔬 b14+b6 吞噬+超賣" 移至 LEGACY（樣本歸零，AND 條件過嚴，2026-05-15 放棄）
#   • ACTIVE_PRESETS 共 14 個策略
#
# V19 PIT 驗證結果（2026-05-16）：
#   • 💎 b15+b6 下影線+超賣 PIT WF 通過（IS +8.15% / OOS +7.99% / 退化 -30.2% / 正Fold 7/7）
#   • 🔬 b13+b6 縮量反轉+超賣 維持待觀察（Fold7 OOS=0筆，樣本萎縮趨勢）
#   • REGIME_RECOMMENDATIONS 全面加入 💎 b15+b6
#
# V19 PIT 驗證結果（2026-05-15，b16）：
#   • 💎 b16 下影線資金流入 PIT WF 通過（IS +6.43% / OOS +7.30% / 退化 -101.7% / 正Fold 7/7）
#   • 升格為 💎，加入 REGIME_RECOMMENDATIONS 弱牛市/牛市警惕/熊市觀察/轉折期
#
# V19 新訊號（2026-05-17）：
#   • b17 5日ROC超跌反彈（ROC5 < -8%，RSI<45，MA20下方，陽燭）
#   • b18 Z-Score資金流向（vol_z 2-5倍標準差，MA20下方，陽燭）
#   • 所有 buy tuple 由 16 元素擴充為 18 元素
#   • 新增三個測試策略 🔬 b17 ROC超跌反彈 / 🔬 b18 Z-Score資金流向 / 🔬 b18+b6 Z-Score超賣
#
# 每個策略 dict 欄位：
#   desc            - UI 顯示的策略說明
#   buy             - 18 個買入信號的 tuple (b1~b18)
#   sell            - 8 個賣出信號的 tuple (s1~s8)
#   min_hold_days   - (可選) 策略級最小持倉天數
#   cooldown_days   - (可選) 同股加倉冷卻期（V18 新增）
#   seasonal_filter - (可選) True = 限定 1/4/10 月入場（V18 季節性測試新增）
#
# buy  tuple 順序：b1 b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 b13 b14 b15 b16 b17 b18
# sell tuple 順序：s1  s2  s3  s4  s5  s6  s7  s8
#
# ══════════════════════════════════════════════════════════════════
# ACTIVE_PRESETS -- 實盤候選 / 推薦策略（共 17 個）
# 用於：制度矩陣全跑、共振掃描、Tab 推薦清單
# ══════════════════════════════════════════════════════════════════

ACTIVE_PRESETS = {

    # V19 PIT 驗證完成（2026-05-15）：
    # 6 個策略通過 PIT Walk-Forward（IS=12月, OOS=6月, 5年, 183隻）
    # 最高回報：💎 b12+b6 OOS +14.07%（5/5 正Fold）
    # 最穩定：💎 b15+b6 OOS +7.99%（7/7 正Fold，全程無負）
    # 舊均值回歸系列（💎+s2 M30 / 💎M30 / 🔄🔄M30）已降級 LEGACY（PIT OOS 正Fold 43%）

    # ── 1. 💎+ M30 RSI 進雙出 MIN30 ──────────────────────────────
    "💎+ M30 RSI進雙出MIN30": {
        "desc": "【實盤候選】b6 進場，s6+s8 雙出場，MIN30。V18 數字：OOS +13.70% / 退化 -91.3% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +7.06% / 退化 -43.1% / 正Fold 100%。"
                "比 💎M30 略強，可作冠軍進取版。"
                "✅ Open版 OOS +7.06%，改Open後升幅最大（+1.79%），進取版首選。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 2. 🔬 資金流向測試（V18 新訊號，待 WF 驗證）──────────────
    "🔬 資金流向測試": {
        "desc": "【🧪 測試中】V18 新訊號：b12 資金流向——股價在MA20下方，成交量為均量2-8倍，陽線收盤。"
                "sell 沿用冠軍三重出場（s2+s6+s8），最少持倉30天，待 WF 驗證。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── 3. 🔬 冠軍+季節性（V18 季節性測試，待 WF 驗證）──────────
    "🔬 冠軍+季節性": {
        "desc": "V18 季節性測試：冠軍策略限定1/4/10月入場，待 WF 驗證",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    # ── 4. 🔬 均值回歸+季節性（V18 季節性測試，待 WF 驗證）───────
    "🔬 均值回歸+季節性": {
        "desc": "V18 季節性測試：均值回歸限定1/4/10月入場，待 WF 驗證",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    # ── 5. 🔬 b12+b6 資金流向超賣（V18 信號測試）──────────────────
    "🔬 b12+b6 資金流向超賣": {
        "desc": "【🧪 測試中】b6（RSI<30）+ b12（資金流向 MA20下方大量陽燭）AND 進場，"
                "s2（布林上軌）出場，MIN5。短週期反彈試驗，待 WF 驗證。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 6. 🔬 b11+b5 KDJ超賣布林雙確認（V18 信號測試）─────────────
    "🔬 b11+b5 KDJ超賣布林雙確認": {
        "desc": "【🧪 測試中】b5（布林下軌）+ b11（KDJ超賣金叉）AND 進場，"
                "s8（KDJ高位死叉）出場，MIN5。雙重超賣確認試驗，待 WF 驗證。",
        "buy":  (False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, False, False, True),
        "min_hold_days": 5,
    },

    # ── 7. 🔬 b3+b7+b8 底背離趨勢確認（V18 信號測試）─────────────
    "🔬 b3+b7+b8 底背離趨勢確認": {
        "desc": "【🧪 測試中】b3（底背離）+ b7（MACD金叉）+ b8（趨勢確認）AND 進場，"
                "s5（RSI超買）+ s6（MACD死叉）OR 出場，MIN10。底背離+趨勢三重確認，待 WF 驗證。",
        "buy":  (False, False, True,  False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, True,  True,  False, False),
        "min_hold_days": 10,
    },

    # ── 8. 💎 b12+b6 資金流向超賣（WF 驗證通過）────────────────────
    "💎 b12+b6 資金流向超賣": {
        "desc": "WF驗證 PIT OOS+14.07% 5/5正Fold｜b12資金流向+b6RSI超賣雙確認｜出場布林上軌。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 9. 💎 b13 縮量反轉（PIT WF 驗證通過，2026-05-15）───────────
    "💎 b13 縮量反轉": {
        "desc": "【💎 PIT 驗證通過】縮量後放量陽線：前2天量萎縮後今天放量陽線，RSI<40，MA20下方。"
                "s2布林上軌出場，MIN5。"
                "PIT WF（2026-05-15）：IS +6.62% / OOS +7.49% / 退化 -96% / 正Fold 7/7 / 有效7/7。"
                "2022大熊市 OOS +7.69%，全程無負 Fold，統計樣本充足。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 10. 💎 b14 低位吞噬（PIT WF 驗證通過，2026-05-15）──────────
    "💎 b14 低位吞噬": {
        "desc": "【💎 PIT 驗證通過】低位半吞噬形態：昨陰今陽吞噬過半+放量+MA20下方。"
                "s2布林上軌出場，MIN5。"
                "PIT WF（2026-05-15）：IS +3.43% / OOS +5.64% / 退化 -219.4% / 正Fold 7/7 / 有效7/7。"
                "最穩定策略，OOS 均高於 IS，2022熊市 OOS +4.26%。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 11. 💎 b15 長下影線（PIT WF 驗證通過，2026-05-15）──────────
    "💎 b15 長下影線": {
        "desc": "【💎 PIT 驗證通過】長下影線：下影線>實體2倍+收高+MA20下方。"
                "s2布林上軌出場，MIN5。"
                "PIT WF（2026-05-15）：IS +3.91% / OOS +5.82% / 退化 -106.4% / 正Fold 7/7 / 有效7/7。"
                "樣本最多（每Fold OOS 184-571筆），統計顯著性最高，2022熊市 OOS +2.77%。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 12. 💎 b15+b6 下影線+超賣（PIT WF 驗證通過，2026-05-16）────
    "💎 b15+b6 下影線+超賣": {
        "desc": "【💎 PIT 驗證通過】b15（長下影線）AND b6（RSI<30）雙確認。"
                "PIT WF（2026-05-15）：IS +8.15% / OOS +7.99% / 退化 -30.2% / 正Fold 7/7 / 有效7/7。"
                "所有策略中最穩定：全程無負Fold，2022大熊市 OOS +8.33%，OOS持續貼近IS無過擬合跡象。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, True,  False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 13. 🔬 b13+b6 縮量反轉+超賣（V19 雙確認測試）──────────────
    "🔬 b13+b6 縮量反轉+超賣": {
        "desc": "【🧪 待觀察】b13 AND b6 雙確認。"
                "PIT WF（2026-05-15）：OOS +8.86% / 正Fold 5/5 / 有效5/7。"
                "警告：Fold7 OOS=0筆（訊號近期消失），Fold2僅2筆，樣本萎縮趨勢，暫不升格。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 14. 💎 b16 下影線資金流入（PIT WF 驗證通過，2026-05-15）─────
    "💎 b16 下影線資金流入": {
        "desc": "【💎 PIT 驗證通過】b16：長下影線+放量陽燭（量1.5-12x）整合訊號。"
                "PIT WF（2026-05-15）：IS +6.43% / OOS +7.30% / 退化 -101.7% / 正Fold 7/7 / 有效7/7。"
                "2022大熊市 OOS +8.33%，恐慌拋售後拉回形態在高波動環境自然有效。",
        "buy":  (False, False, False, False, False, False, False, False, False, False,
                 False, False, False, False, False, True,  False, False),
        "sell": (False, True, False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 15. 💎 b17 ROC超跌反彈（PIT WF 驗證通過，2026-05-17）────────
    "💎 b17 ROC超跌反彈": {
        "desc": "【💎 PIT 驗證通過】b17：5日ROC < -8%（急跌），收盤<MA20，RSI<45，陽燭。"
                "與b6互補，捕捉急跌但RSI未到30的反彈機會。"
                "PIT WF（2026-05-17）：IS +5.96% / OOS +8.73% / 退化 -141.8% / 正Fold 7/7 / 有效7/7。"
                "全程無負Fold，Fold7 OOS +8.94%，近期訊號健康，樣本充足（每Fold 41-453筆）。"
                "s2布林上軌出場，MIN5。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, False, False, True, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 16. 💎 b18 Z-Score資金流向（PIT WF 驗證通過，2026-05-17）────
    "💎 b18 Z-Score資金流向": {
        "desc": "【💎 PIT 驗證通過】b18：成交量 Z-Score > 2.0（超過2個標準差），"
                "收盤<MA20，陽燭。b12固定倍數的升級版，自動適應個股量能波動率。"
                "PIT WF（2026-05-17）：IS +5.85% / OOS +7.09% / 退化 -118.9% / 正Fold 6/6 / 有效6/7。"
                "Fold4 IS≈0退化率無效屬正常，排除後全Fold OOS正數，Fold7 OOS +8.51%。"
                "s2布林上軌出場，MIN5。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, False, False, False, True),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── 17. 🔬 b18+b6 Z-Score超賣（2026-05-17 新增，待 WF 驗證）────
    "🔬 b18+b6 Z-Score超賣": {
        "desc": "【🧪 測試中】b18（Z-Score資金流向）AND b6（RSI<30）雙確認。"
                "對標 💎 b12+b6，驗證 Z-Score 量能定義是否優於固定倍數。"
                "s2布林上軌出場，MIN5。待 PIT WF 驗證。",
        "buy":  (False, False, False, False, False, True,  False, False,
                 False, False, False, False, False, False, False, False, False, True),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

}


# ══════════════════════════════════════════════════════════════════
# LEGACY_PRESETS -- 對照組 / 已驗證 BIAS / 已放棄策略（純歷史紀錄）
# 不參與：制度矩陣、共振掃描推薦
# 仍可在 Tab 的「自定義」/「預設」下拉選單中手動選擇查看
# ══════════════════════════════════════════════════════════════════

LEGACY_PRESETS = {

    # ── 對照組：沒有 MIN 限制（V18 cooldown_days=0 恢復原語意）────

    "💎 純粹均值回歸 [對照]": {
        "desc": "【📚 LEGACY 對照組】純粹的 b6/s6，無 MIN 限制。V17 數字：WF +4.91% / 延伸 +12.55%。"
                "🆕 V18：cooldown_days=0（恢復原語意，與 💎M30 對照證明 MIN30 alpha）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎+s2 三重出場 [無MIN對照]": {
        "desc": "【📚 LEGACY 對照組】b6/s2+s6+s8 無 MIN。V17 數字：WF +3.81% / 延伸 +10.64% / 樣本 885。"
                "🆕 V18：cooldown_days=0（恢復原語意）。對照冠軍 💎+s2 M30 證明 MIN30 alpha。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "cooldown_days": 0,
    },

    "💎M20 純粹均值回歸MIN20 [對照]": {
        "desc": "【📚 LEGACY MIN 參數對照】b6/s6 MIN20。V17 數字：WF +3.52% / 延伸 +16.47%。"
                "證實 MIN30 才是最優參數。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 20,
    },

    "🔄基準 純MACD週期 [對照]": {
        "desc": "【📚 LEGACY 對照】純 b7/s6 無任何過濾。V17 數字：WF +0.42% / 延伸 +8.80%。"
                "🆕 V18：cooldown_days=0。對比🔄M30 量化 MIN30 alpha 約 +4.18%。",
        "buy":  (False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎K30 純KDJ超賣MIN30 [已驗證]": {
        "desc": "【📚 LEGACY 已驗證失敗】WF +1.50% / 延伸 +10.46%。KDJ 單獨進場效果遠不如 RSI。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── V18-5Y 複審移入 LEGACY ──────────────────────────────────
    "🔄+ MACD+趨勢MIN30 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-09】MACD金叉+趨勢確認，MACD死叉出，MIN30。"
                "V18 數字：OOS +7.37% / 退化 -10.5% / 正Fold 67%。"
                "V18-5Y 數字：OOS +4.14% / 退化 -194.2% / 正Fold 67%。"
                "5Y 下 IS 僅 +0.22%，IS 表現靠運氣非策略 alpha，移出實盤候選。",
        "buy":  (False, False, False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False),
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
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (True,  False, False, True,  False, False, False, False),
        "cooldown_days": 5,
    },

    "💎K+ M30 雙超賣雙出MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】退化率 -313.7%（> -300% 門檻），5Y OOS 靠運氣非策略 alpha，移出實盤候選。"
                "V18 數字：OOS +15.03% / 退化 -728.6% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +15.67% / 退化 -313.7% / 正Fold 100%。"
                "完整 KDJ 強化版，OOS 遠超 IS（市場配合時表現極佳，但 IS 靠運氣）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "💎KK30 RSI+KDJ雙超賣MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】退化率 -278.5%（> -300% 近邊界且精選股樣本稀少），5Y OOS 靠運氣非策略 alpha，移出實盤候選。"
                "V18 數字：OOS +13.68% / 退化 -535.2% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +15.17% / 退化 -278.5% / 正Fold 100%。"
                "雙重超賣確認，適合資金有限時觀察用。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── b9 相對強弱：熊市過濾後訊號過少，AND邏輯疊加全部❌，2026-05-10 放棄 ──
    "🔬 相對強弱測試 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】V18 新訊號：b9 相對強弱——恆指15日跌>5%，個股跌幅<恆指×0.5，恆指MA5金叉MA20。"
                "熊市過濾後訊號過少，AND 邏輯疊加全部❌，放棄。",
        "buy":  (False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+冠軍買入_冠軍出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】相對強弱疊加冠軍買入，冠軍出場。"
                "熊市過濾後訊號過少，AND 邏輯疊加全部❌，放棄。",
        "buy":  (False, False, False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+冠軍買入_均值回歸出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】相對強弱疊加冠軍買入，均值回歸出場。"
                "熊市過濾後訊號過少，AND 邏輯疊加全部❌，放棄。",
        "buy":  (False, False, False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔬 b9+均值回歸買入_冠軍出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】相對強弱疊加均值回歸買入，冠軍出場。"
                "熊市過濾後訊號過少，AND 邏輯疊加全部❌，放棄。",
        "buy":  (False, False, False, False, True,  True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+均值回歸買入_均值回歸出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】相對強弱疊加均值回歸買入，均值回歸出場。"
                "熊市過濾後訊號過少，AND 邏輯疊加全部❌，放棄。",
        "buy":  (False, False, False, False, True,  True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 已驗證 BIAS（教訓紀錄，勿實盤）────────────────────────────

    "📈 均值回歸 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS 警示】WF +10.33% 看似最高，但延伸僅 +3.81%（49.8% 勝率）。"
                "Survivorship bias 案例：高 OOS 數字只統計『跑完全程』的贏家。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, True,  False, False, False),
        "cooldown_days": 0,
    },

    "🏗️M30 底部形態MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】底部突破+MACD金叉 MIN30。WF +6.53% 但延伸僅 +2.19%（49.1% 勝率）。"
                "MIN30 強行抓底部假突破，底部形態類不適合 MIN。",
        "buy":  (False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡+ 突破確認長持MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b1+b8 + MACD死叉 + MIN30。WF +6.20% / 延伸僅 +3.82%。WF 數字過於樂觀。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "💎++ M30 趨勢過濾版 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY 嚴重過擬合】b6+b8 進場，s6+s8 雙出場，MIN30。WF 僅 +0.22% / 退化率 90.5% / 樣本暴跌至 126。"
                "教訓：b6（RSI<30）通常出現在下跌中，此時 b8 不成立，邏輯互斥。",
        "buy":  (False, False, False, False, False, True,  False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── V18 PIT 複審移入 LEGACY ──────────────────────────────────
    "💎+s2 M30 三重出場版【實盤冠軍】": {
        "desc": "【🏆 實盤主力冠軍】b6 (RSI<30) 進場，s2+s6+s8 三重出場（布林上軌 / MACD死叉 / KDJ高位死叉），最少持倉30天。"
                "V18 數字：OOS +13.64% / 退化 -85.2% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +5.86% / 退化 -84.2% / 正Fold 100%。"
                "PIT 驗證（2026-05-15）：OOS +1.23% / 正Fold 3/7 / 固定池高估 ~5%，移出實盤候選。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        # cooldown 不設 → 沿用 min_hold_days = 30（v17 行為）
    },

    "💎M30 純粹均值回歸MIN30": {
        "desc": "【實盤候選】RSI<30 買入，MACD死叉出，最少持倉30天。V18 數字：OOS +13.94% / 退化 -131.7% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +5.15% / 退化 -20.2% / 正Fold 60%。"
                "✅ Open版退化率最低（-20.2%），全部策略中最可信，邏輯最簡單，首選實盤基準。"
                "PIT 驗證（2026-05-15）：OOS -0.42% / 正Fold 3/7 / 固定池高估 ~5%，移出實盤候選。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔄🔄M30 均值回歸長持MIN30": {
        "desc": "【實盤組合】布林下軌+RSI超賣，MACD死叉出，最少持倉30天。V18 數字：OOS +9.30% / 退化 -252.1% / 正Fold 100%。"
                "V18-5Y-Open 數字：OOS +6.12% / 退化 -83.6% / 正Fold 100%。"
                "比 💎M30 更挑剔但同等強，可分散搭配。"
                "PIT 驗證（2026-05-15）：OOS +0.43% / 正Fold 3/7 / 固定池高估 ~5%，移出實盤候選。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── V19 雙確認：AND條件過嚴，樣本歸零，2026-05-15 放棄 ────────
    "🔬 b14+b6 吞噬+超賣": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b14（低位吞噬）AND b6（RSI<30）雙確認。"
                "樣本歸零（10隻×1年共0筆），AND條件過嚴，2026-05-15放棄。"
                "s2布林上軌出場，MIN5。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False,
                 False, False, False, True,  False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

}


# ══════════════════════════════════════════════════════════════════
# REGIME_RECOMMENDATIONS -- 8 制度 → 推薦策略對照表
# 弱熊市 / 強熊市 設為空 list，視為實盤禁區
# ══════════════════════════════════════════════════════════════════

REGIME_RECOMMENDATIONS = {
    "強牛市":   [
        "💎 b15+b6 下影線+超賣",
        "💎 b13 縮量反轉",
        "💎 b14 低位吞噬",
        "💎 b15 長下影線",
        "💎 b17 ROC超跌反彈",
    ],
    "弱牛市":   [
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
        "💎 b13 縮量反轉",
        "💎 b14 低位吞噬",
        "💎 b17 ROC超跌反彈",
    ],
    "牛市警惕": [
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
        "💎 b17 ROC超跌反彈",
    ],
    "熊市觀察": [
        "💎 b12+b6 資金流向超賣",
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
        "💎 b18 Z-Score資金流向",
    ],
    "弱熊市":   [],   # 實盤禁區
    "強熊市":   [],   # 實盤禁區
    "震盪市":   [
        "💎 b12+b6 資金流向超賣",
        "💎 b15+b6 下影線+超賣",
        "💎 b14 低位吞噬",
        "💎 b15 長下影線",
        "💎 b18 Z-Score資金流向",
    ],
    "轉折期":   [
        "💎 b15+b6 下影線+超賣",
        "💎 b12+b6 資金流向超賣",
        "💎 b16 下影線資金流入",
        "💎 b17 ROC超跌反彈",
        "💎 b18 Z-Score資金流向",
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
    "⑬縮量反轉", "⑭低位吞噬", "⑮長下影線", "⑯下影線資金流入",
    "⑰ROC超跌反彈", "⑱Z-Score資金流向",
]
SELL_LABELS = [
    "⑬頭部破MA20", "⑭布林上軌", "⑮縮量頂部", "⑯放量急跌",
    "⑰RSI超買", "⑱MACD死叉", "⑲三日陰線", "⑳KDJ高位死叉",
]

B_NAMES = ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8",
           "b9", "b10", "b11", "b12", "b13", "b14", "b15", "b16",
           "b17", "b18"]
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

# ── 制度分類常數 ─────────────────────────────────────────────────────────────
BEAR_LABELS_HARD = {"弱熊市", "強熊市"}   # 實盤禁區，掃描完全停止
BEAR_LABELS_SOFT = {"熊市觀察"}            # 觀察區，允許保守策略

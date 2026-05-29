# ══════════════════════════════════════════════════════════════════
# config.py -- 策略組合預設 & 全局常量
# ══════════════════════════════════════════════════════════════════
#
# V22.1 形態+形態 AND 升格（2026-05-28）-- 來自 verify + PIT WF 雙重驗證：
#
#   依 V22 戰略方向「探索形態事件 + 形態事件 AND」，verify_pattern_combos.py
#   篩掉子集冗餘組合（b12+b18 保留72%、b15+b16 保留100% 都是子集包含），
#   再對 4 個跨類別候選跑 PIT WF（12+6，11 Fold，165 隻 PIT 池），結果：
#
#     候選          OOS      增量        正Fold  末Fold  判定
#     b12+b15      +7.73%   +0.70/b12   10/11   15筆   ✅ 主力升格
#     b15+b17      +9.04%   +0.92/b17   10/11   8筆    💎 輔助（樣本薄輕倉）
#     b13+b15      +7.91%   +1.59/b13   11/11   5筆    💎 輔助（樣本薄輕倉）
#     b13+b17      +6.01%   -2.11/b17   8/11    5筆    🔴 淘汰（b13 稀釋 b17）
#
#   ACTIVE_PRESETS 由 8 支增為 11 支。
#
#   ── V22.1 新洞察：b15 是「最佳組合催化劑」────────────────────────
#   所有含 b15（純下影線形態，不含任何指標閾值）的組合 OOS 全 > 7.7%，
#   唯一不含 b15 的 b13+b17 墊底（+6.01%）。原因：b13（RSI<40）與 b17（RSI<45）
#   彼此組合時 RSI 條件冗餘、互相稀釋；b15 純價格形態，貢獻全新維度，跟誰組都加值。
#   → 衍生鐵則 5：純形態訊號是最佳組合基底；兩個含指標的形態互組會冗餘稀釋。
#
# ──────────────────────────────────────────────────────────────────
# V22 ACTIVE 精簡（2026-05-28）-- 來自 HANDOVER18 PIT WF 全策略複審：
#
#   全策略 PIT Walk-Forward 驗證了專案級鐵則：
#     『港股 PIT 環境下，「形態事件類」訊號有 alpha，「指標閾值類」訊號沒有。』
#
#   ── 衍生鐵則 ───────────────────────────────────────────────────
#   1. b6（RSI<30）作為進場核心無 alpha：所有 b6 變體 PIT 下平均 ~+2%，是雜訊。
#   2. b6 雙確認是樣本陷阱：Fold7 樣本平均砍 80-100%，表頭虛高。
#   3. 趨勢追蹤（b1 突破、b7 MACD 金叉）在港股中小型股 PIT 下穩定虧損或趨近零。
#   4. AND 邏輯超過 2 個條件，或形態類疊指標類 AND，都會把訊號掐死。
#   5. （V22.1 新增）純形態訊號（b15）是最佳組合基底；含指標的形態互組會冗餘稀釋。
#
#   ── V22 升降清單 ───────────────────────────────────────────────
#   移入 LEGACY（8 支）：🔬 資金流向測試 / 🔬 冠軍+季節性 / 🔬 均值回歸+季節性 /
#     🔬 b11+b5 / 🔬 b3+b7+b8 / 🔬 b13+b6 / 🔬 b17+b6 / 🔬 b18+b6
#   刪除（1 支）：🔬 b12+b6 資金流向超賣（測試版，與 💎 b12+b6 重複）
#
# ──────────────────────────────────────────────────────────────────
# 歷史變更（保留作為審計軌跡）
# ──────────────────────────────────────────────────────────────────
#
# V21 PIT 複審（2026-05-23）：💎+ M30 RSI進雙出MIN30 移至 LEGACY（b6 家族）
#
# V20 標籤重構（2026-05-17）：BUY_LABELS 改 Ⓑ 前綴、SELL_LABELS 改 Ⓢ 前綴
#
# V19 新訊號（2026-05-15 → 2026-05-17）：
#   b13 縮量反轉 / b14 低位吞噷 / b15 長下影線 / b16 下影線資金流入
#   b17 ROC超跌反彈 / b18 Z-Score資金流向；buy tuple 12→18 元素
#
# V18 新訊號（2026-05-10 → 2026-05-14）：
#   b12 資金流向；季節性過濾 is_seasonal()；b9 相對強弱 DEPRECATED
#
# V18 修復（2026-04-27）：
#   🔴-2 cooldown_days 解耦；🟡-2 T+1 持倉天數；🟡-7 港股 lot size 取整
#
# 欄位說明：
#   desc / buy(18) / sell(8) / min_hold_days / cooldown_days / seasonal_filter
#
# buy  tuple 順序：b1 b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 b13 b14 b15 b16 b17 b18
# sell tuple 順序：s1  s2  s3  s4  s5  s6  s7  s8
#
# ══════════════════════════════════════════════════════════════════
# ACTIVE_PRESETS -- 實盤候選 / 推薦策略（共 11 支，全部 PIT 驗證通過）
# 用於：制度矩陣全跑、共振掃描、Tab 推薦清單、daily_scan 推播
#
#   分組：
#   ① 純單訊號形態主力（6）：b13 b14 b15 b16 b17 b18
#   ② 形態+形態雙確認（3，V22.1）：b12+b15 主力 / b13+b15 b15+b17 輔助輕倉
#   ③ 含 b6 輔助（2）：b12+b6 b15+b6
# ══════════════════════════════════════════════════════════════════

ACTIVE_PRESETS = {

    # ════════════════════════════════════════════════════════════
    # ① 純單訊號形態主力（V22 全 7/7 正、樣本厚）
    # ════════════════════════════════════════════════════════════

    "💎 b13 縮量反轉": {
        "desc": "【💎 PIT 驗證通過｜主力】縮量後放量陽線："
                "前2天量萎縮後今天放量陽線，RSI<40，MA20下方。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +6.62% / OOS +7.49% / 退化 -96% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +6.32%，每 Fold 26-265 筆，2022 熊市 OOS +7.69%。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b14 低位吞噷": {
        "desc": "【💎 PIT 驗證通過｜主力】低位半吞噷形態："
                "昨陰今陽吞噬過半 + 放量 + MA20 下方。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +3.43% / OOS +5.64% / 退化 -219.4% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +5.12%，每 Fold 47-162 筆，OOS 均高於 IS、最穩定。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b15 長下影線": {
        "desc": "【💎 PIT 驗證通過｜主力｜最佳組合催化劑】長下影線："
                "下影>實體2倍+收高+MA20下方。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +3.91% / OOS +5.82% / 退化 -106.4% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +5.56%，每 Fold 168-541 筆（樣本最厚），"
                "純價格形態無指標閾值，是 V22.1 形態+形態組合的最佳基底。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b16 下影線資金流入": {
        "desc": "【💎 PIT 驗證通過｜主力】b16：長下影線+放量陽燭（量1.5-12x）整合訊號。"
                "s2 布林上軌出場，MIN5。"
                "PIT WF：IS +6.43% / OOS +7.30% / 退化 -101.7% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +7.18%，每 Fold 22-92 筆，2022 熊市 OOS +8.33%。",
        "buy":  (False, False, False, False, False, False, False, False, False, False,
                 False, False, False, False, False, True,  False, False),
        "sell": (False, True, False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b17 ROC超跌反彈": {
        "desc": "【💎 PIT 驗證通過｜主力】b17：5日ROC < -8%（急跌），"
                "收盤 < MA20，RSI<45，陽燭。與 b6 互補，捕捉急跌但 RSI 未到 30 的反彈。"
                "s2 布林上軌出場，MIN5。"
                "PIT WF：IS +5.96% / OOS +8.73% / 退化 -141.8% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +8.12%（11 Fold），每 Fold 39-419 筆，全程無負 Fold。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, False, False, True, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b18 Z-Score資金流向": {
        "desc": "【💎 PIT 驗證通過｜主力】b18：成交量 Z-Score > 2.0（超過2個標準差），"
                "收盤 < MA20，陽燭。b12 固定倍數的升級版，自動適應個股量能波動率。"
                "s2 布林上軌出場，MIN5。"
                "PIT WF：IS +5.85% / OOS +7.09% / 退化 -118.9% / 正Fold 6/6。"
                "V21 重跑（2026-05-28）：OOS +6.26%，每 Fold 59-196 筆。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, False, False, False, True),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ════════════════════════════════════════════════════════════
    # ② 形態+形態雙確認（V22.1 升格，2026-05-28）
    # ════════════════════════════════════════════════════════════

    "💎 b12+b15 資金流向+下影線": {
        "desc": "【💎 PIT 驗證通過｜主力｜V22.1 形態+形態】"
                "b12（資金流向 MA20下方大量陽燭）AND b15（長下影線）跨類別雙確認。"
                "s2 布林上軌出場，MIN5。"
                "PIT WF（2026-05-28，11 Fold，165 隻 PIT 池）："
                "IS +7.09% / OOS +7.73% / 退化 -9.0% / 正Fold 10/11 / 末Fold 15 筆。"
                "增量 +0.70% vs b12 單訊號，末 Fold 樣本厚，乾淨升格。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, True,  False, False, True,  False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b13+b15 縮量反轉+下影線": {
        "desc": "【💎 PIT 驗證通過｜⚠️ 輔助：樣本薄，輕倉｜V22.1 形態+形態】"
                "b13（縮量反轉）AND b15（長下影線）雙形態確認。s2 布林上軌出場，MIN5。"
                "PIT WF（2026-05-28，11 Fold）："
                "IS +6.21% / OOS +7.91% / 退化 -27.4% / 正Fold 11/11（完美）/ 末Fold 5 筆。"
                "增量 +1.59% vs b13。正Fold 全場唯一 11/11，但末 Fold 僅 5 筆，**實盤輕倉**。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, True,  False, True,  False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b15+b17 下影線+急跌": {
        "desc": "【💎 PIT 驗證通過｜⚠️ 輔助：樣本薄，輕倉｜V22.1 形態+形態】"
                "b15（長下影線）AND b17（ROC急跌）跨類別雙確認。s2 布林上軌出場，MIN5。"
                "PIT WF（2026-05-28，11 Fold）："
                "IS +7.70% / OOS +9.04%（全場最高）/ 退化 -17.4% / 正Fold 10/11 / 末Fold 8 筆。"
                "增量 +0.92% vs b17，OOS 全候選最高，但末 Fold 僅 8 筆，**實盤輕倉**。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, True,  False, True,  False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ════════════════════════════════════════════════════════════
    # ③ 含 b6 輔助（雙確認，數字會飄 / 樣本薄，輕倉）
    # ════════════════════════════════════════════════════════════

    "💎 b12+b6 資金流向超賣": {
        "desc": "【💎 PIT 驗證通過｜⚠️ 輔助：數字會飄，別重倉】"
                "b6（RSI<30）+ b12（資金流向）AND 進場，s2 布林上軌出場，MIN5。"
                "PIT V21 重跑（2026-05-28）：OOS +7.03%（前次跑 +14.62%）/ 正Fold 4/5。"
                "兩次跑差距 ~50%，Fold2/F3/F7 各個位數樣本，**實盤僅作輔助、不要重倉**。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b15+b6 下影線+超賣": {
        "desc": "【💎 PIT 驗證通過｜⚠️ 輔助：樣本薄，輕倉】"
                "b15（長下影線）AND b6（RSI<30）雙確認。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +8.15% / OOS +7.99% / 退化 -30.2% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +7.21% / 正Fold 6/7。"
                "⚠️ Fold2 與 Fold7 各僅 7 筆，**實盤建議輕倉**。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, True,  False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

}


# ══════════════════════════════════════════════════════════════════
# LEGACY_PRESETS -- 對照組 / 已驗證 BIAS / 已放棄策略（純歷史紀錄）
# 不參與：制度矩陣、共振掃描推薦、daily_scan 推播
# 仍可在 Tab 的「自定義」/「預設」下拉選單中手動選擇查看
# ══════════════════════════════════════════════════════════════════

LEGACY_PRESETS = {

    # ══════════════════════════════════════════════════════════════
    # V22.1 淘汰（2026-05-28，形態+形態 PIT WF 後）
    # ══════════════════════════════════════════════════════════════

    "🔬 b13+b17 縮量反轉+急跌 [LEGACY]": {
        "desc": "【📚 LEGACY V22.1 淘汰 2026-05-28】b13 AND b17 雙確認。"
                "PIT WF（2026-05-28，11 Fold）：OOS +6.01% / 正Fold 8/11 / 末Fold 5 筆。"
                "淘汰原因：OOS +6.01% **低於** b17 單訊號 +8.12%（增量 -2.11%）。"
                "印證 V22.1 衍生鐵則 5：b13（RSI<40）與 b17（RSI<45）RSI 條件冗餘，"
                "b13 稀釋了 b17，不如直接用 b17 單訊號。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, True,  False, False, False, True,  False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ══════════════════════════════════════════════════════════════
    # V22 新進 LEGACY（2026-05-28，PIT 全策略複審）
    # ══════════════════════════════════════════════════════════════

    # ── b6 雙確認家族：Fold7 樣本砍 80-100%，表頭虛高 ──────────────

    "🔬 b17+b6 ROC急跌+超賣 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b17 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +8.76% / 正Fold 5/7 / Fold7=6 筆。"
                "降級原因：對照單訊號 b17 同期 39 筆，加 b6 後砍 84%，符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False,
                 False, False, False, False, False, False, False, False, True, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "🔬 b18+b6 Z-Score超賣 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b18 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +7.98% / 正Fold 5/6 / Fold7=1 筆。"
                "降級原因：對照 b18 同期 59 筆，加 b6 後砍 98%（剩 1 筆），符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False,
                 False, False, False, False, False, False, False, False, False, True),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "🔬 b13+b6 縮量反轉+超賣 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b13 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +8.67% / 有效6/7 / Fold7=0 筆。"
                "降級原因：Fold7 訊號完全消失，Fold2 僅 2 筆，符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── b6 + 三重出場 / 季節性家族：b6 進場無 alpha 已確認 ──────────

    "🔬 資金流向測試 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b12 資金流向 + s2+s6+s8 三重出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +2.41% / 正Fold 3/6。"
                "降級原因：與 💎 b12+b6 重疊，三重出場 + MIN30 無真實 alpha 增量。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 冠軍+季節性 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】冠軍（b6/s2+s6+s8）+ 季節性（1/4/10月），MIN30。"
                "PIT V21（2026-05-28）：OOS +4.16% / 正Fold 5/6 / Fold5=3 筆。"
                "降級原因：b6 家族雜訊，符合衍生鐵則 1。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    "🔬 均值回歸+季節性 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】純均值回歸（b6/s6）+ 季節性，MIN30。"
                "PIT V21（2026-05-28）：OOS +3.18% / 正Fold 4/6。降級原因：b6 家族雜訊。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    # ── AND 過嚴歸零家族：符合衍生鐵則 4 ─────────────────────────

    "🔬 b11+b5 KDJ超賣布林雙確認 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b5 AND b11 AND 進場，s8 出場，MIN5。"
                "PIT V21（2026-05-28）：**無交易**（雙指標 AND 歸零）。符合衍生鐵則 4。",
        "buy":  (False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, False, False, True),
        "min_hold_days": 5,
    },

    "🔬 b3+b7+b8 底背離趨勢確認 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b3 AND b7 AND b8，s5+s6 出場，MIN10。"
                "PIT V21（2026-05-28）：**無交易**（三條件 AND 歸零）。符合衍生鐵則 3、4。",
        "buy":  (False, False, True,  False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, True,  True,  False, False),
        "min_hold_days": 10,
    },

    # ══════════════════════════════════════════════════════════════
    # 對照組 / 歷史 LEGACY（之前批次移入）
    # ══════════════════════════════════════════════════════════════

    "💎 純粹均值回歸 [對照]": {
        "desc": "【📚 LEGACY 對照組】純 b6/s6，無 MIN。"
                "PIT V21（2026-05-28）：OOS +2.16% / 正Fold 3/6（b6 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎+s2 三重出場 [無MIN對照]": {
        "desc": "【📚 LEGACY 對照組】b6/s2+s6+s8 無 MIN。"
                "PIT V21（2026-05-28）：OOS +0.32% / 正Fold 3/6（b6 雜訊最低端）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "cooldown_days": 0,
    },

    "💎M20 純粹均值回歸MIN20 [對照]": {
        "desc": "【📚 LEGACY MIN 參數對照】b6/s6 MIN20。"
                "PIT V21（2026-05-28）：OOS +2.05% / 正Fold 3/6（b6 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 20,
    },

    "🔄基準 純MACD週期 [對照]": {
        "desc": "【📚 LEGACY 對照】純 b7/s6 無過濾。"
                "PIT V21（2026-05-28）：OOS **-0.94%** / 正Fold 2/6。符合衍生鐵則 3。",
        "buy":  (False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎K30 純KDJ超賣MIN30 [已驗證]": {
        "desc": "【📚 LEGACY 已驗證失敗】b11 KDJ超賣 MIN30。"
                "PIT V21（2026-05-28）：OOS **-1.18%** / 正Fold 3/7。指標閾值類無 alpha。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔄+ MACD+趨勢MIN30 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-09】MACD金叉+趨勢確認，MACD死叉出，MIN30。"
                "PIT V21（2026-05-28）：OOS **-0.43%** / 正Fold 4/6。符合衍生鐵則 3。",
        "buy":  (False, False, False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡ 突破確認 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】強牛市突破策略。"
                "PIT V21（2026-05-28）：OOS **-1.25%** / 正Fold 3/7。符合衍生鐵則 3。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (True,  False, False, True,  False, False, False, False),
        "cooldown_days": 5,
    },

    "💎K+ M30 雙超賣雙出MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b6+b11 KDJ 雙超賣 + 雙出場 MIN30。"
                "PIT V21（2026-05-28）：OOS +0.53% / 正Fold 3/5（b6/KDJ 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "💎KK30 RSI+KDJ雙超賣MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b6+b11 RSI+KDJ 雙超賣 MIN30。"
                "PIT V21（2026-05-28）：OOS **-1.48%** / 正Fold 3/6。雙指標疊加仍雜訊。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── b9 相對強弱：DEPRECATED 永久 False ───────────────────────

    "🔬 相對強弱測試 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 相對強弱單訊號。b9 已 DEPRECATED 永久 False。",
        "buy":  (False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+冠軍買入_冠軍出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+冠軍買入_均值回歸出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔬 b9+均值回歸買入_冠軍出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, True,  True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+均值回歸買入_均值回歸出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, True,  True,  False, False, True,  False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 已驗證 BIAS（教訓紀錄，勿實盤）────────────────────────────

    "📈 均值回歸 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS 警示】b5+b6/s2+s5。"
                "PIT V21（2026-05-28）：OOS +7.64% / 正Fold 6/7。"
                "⚠️ 數字高但比延伸追蹤 +3.81% 高，可能 survivorship bias 殘留，**勿復活**。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, True,  False, False, False),
        "cooldown_days": 0,
    },

    "🏗️M30 底部形態MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b4+b7 + MIN30。"
                "PIT V21（2026-05-28）：OOS +1.63% / 正Fold 3/7。MIN30 強行抓底部假突破。",
        "buy":  (False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡+ 突破確認長持MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b1+b8 + MACD死叉 + MIN30。"
                "PIT V21（2026-05-28）：OOS +0.38% / 正Fold 4/7（趨近零）。符合衍生鐵則 3。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "💎++ M30 趨勢過濾版 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY 嚴重過擬合】b6+b8 進場，s6+s8 雙出場，MIN30。"
                "PIT V21（2026-05-28）：OOS **-1.01%** / 正Fold 2/6（OOS 虧損）。"
                "教訓：b6（RSI<30）通常在下跌中，此時 b8 不成立，邏輯互斥。",
        "buy":  (False, False, False, False, False, True,  False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── V18 PIT 複審移入 LEGACY（b6 進場 MIN30 家族）─────────────

    "💎+s2 M30 三重出場版【實盤冠軍】": {
        "desc": "【📚 LEGACY 移入 2026-05-15，前實盤冠軍】b6 進場，s2+s6+s8 三重出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +4.39% / 正Fold 5/6（2022-23 熊市虧損）。"
                "b6 家族最強變體，但數字會飄，不再實盤。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "💎M30 純粹均值回歸MIN30": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b6 進場，s6 出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +2.83% / 正Fold 4/6（b6 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔄🔄M30 均值回歸長持MIN30": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b5+b6 進場，s6 出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +3.95% / 正Fold 4/6（b6 雜訊區間略高端）。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── V19 雙確認：AND 過嚴，2026-05-15 放棄 ────────────────────

    "🔬 b14+b6 吞噷+超賣 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b14 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +7.18% / 有效4/4 / Fold7=0 筆。符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False,
                 False, False, False, True,  False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── V21 PIT 複審移入 LEGACY（2026-05-23）──────────────────────

    "+ M30 RSI進雙出MIN30 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-23】b6 進場，s6+s8 雙出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +1.03% / 正Fold 4/7（接近隨機）。"
                "2022-23 熊市 Fold1-3 連虧，末 Fold 僅 38 筆，b6 家族同源同症，符合衍生鐵則 1。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

}


# ══════════════════════════════════════════════════════════════════
# REGIME_RECOMMENDATIONS -- 8 制度 → 推薦策略對照表（V22.1 更新）
# 弱熊市 / 強熊市 設為空 list，視為實盤禁區
#
# V22.1 變更（2026-05-28）：
#   • 牛市（強/弱）：保持純單訊號形態（訊號多、簡單）
#   • 謹慎制度（牛市警惕/熊市觀察/震盪市/轉折期）：加入新的形態+形態雙確認
#     b15+b17（OOS 最高）出現在最多制度，b12+b15（樣本厚）入熊市觀察
# ══════════════════════════════════════════════════════════════════

REGIME_RECOMMENDATIONS = {
    "強牛市": [
        "💎 b15 長下影線",
        "💎 b17 ROC超跌反彈",
        "💎 b13 縮量反轉",
        "💎 b14 低位吞噷",
        "💎 b16 下影線資金流入",
    ],
    "弱牛市": [
        "💎 b15 長下影線",
        "💎 b17 ROC超跌反彈",
        "💎 b16 下影線資金流入",
        "💎 b13 縮量反轉",
        "💎 b14 低位吞噷",
    ],
    "牛市警惕": [
        "💎 b15+b17 下影線+急跌",
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
        "💎 b17 ROC超跌反彈",
    ],
    "熊市觀察": [
        "💎 b12+b15 資金流向+下影線",
        "💎 b12+b6 資金流向超賣",
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
        "💎 b18 Z-Score資金流向",
    ],
    "弱熊市":   [],   # 實盤禁區
    "強熊市":   [],   # 實盤禁區
    "震盪市": [
        "💎 b15+b17 下影線+急跌",
        "💎 b12+b15 資金流向+下影線",
        "💎 b13+b15 縮量反轉+下影線",
        "💎 b15+b6 下影線+超賣",
        "💎 b18 Z-Score資金流向",
    ],
    "轉折期": [
        "💎 b15+b17 下影線+急跌",
        "💎 b13+b15 縮量反轉+下影線",
        "💎 b12+b6 資金流向超賣",
        "💎 b16 下影線資金流入",
        "💎 b18 Z-Score資金流向",
    ],
}


# ══════════════════════════════════════════════════════════════════
# 對外名稱（向後相容）
# ══════════════════════════════════════════════════════════════════
# STRATEGY_PRESETS = ACTIVE + LEGACY 合併（讓 UI 下拉選單看得到全部），
# 各 Tab 自行判斷如何使用：
#   • 制度矩陣 / 共振掃描 / daily_scan → 用 ACTIVE_PRESETS
#   • 回測 / WF / Monte Carlo / 個股分析 → 用 STRATEGY_PRESETS（含 LEGACY）
# ══════════════════════════════════════════════════════════════════

STRATEGY_PRESETS = {**ACTIVE_PRESETS, **LEGACY_PRESETS}

PRESET_NAMES  = ["✏️ 自定義"] + list(STRATEGY_PRESETS.keys())
PRESET_CUSTOM = "✏️ 自定義"

BUY_LABELS = [
    "Ⓑ1 突破放量",      "Ⓑ2 MA5金叉",      "Ⓑ3 底背離",       "Ⓑ4 底部突破",
    "Ⓑ5 布林下軌",      "Ⓑ6 RSI超賣",      "Ⓑ7 MACD金叉",    "Ⓑ8 趨勢確認",
    "Ⓑ9 相對強弱(停用)", "Ⓑ10 縮量回調",    "Ⓑ11 KDJ超賣金叉", "Ⓑ12 資金流向",
    "Ⓑ13 縮量反轉",     "Ⓑ14 低位吞噷",    "Ⓑ15 長下影線",    "Ⓑ16 下影線資金流入",
    "Ⓑ17 ROC超跌反彈",  "Ⓑ18 Z-Score資金流向",
]
SELL_LABELS = [
    "Ⓢ1 頭部破MA20", "Ⓢ2 布林上軌", "Ⓢ3 縮量頂部", "Ⓢ4 放量急跌",
    "Ⓢ5 RSI超買",   "Ⓢ6 MACD死叉", "Ⓢ7 三日陰線",  "Ⓢ8 KDJ高位死叉",
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
# ── 實盤倉位提示 ─────────────────────────────────────────────────────────────
# 樣本薄 / 數字會飄的輔助策略：daily_scan 推播時加「⚠️輕倉」標記，
# 提醒實盤勿重倉。依 HANDOVER19 第五點標註。
LIGHT_POSITION_PRESETS = {
    "💎 b13+b15 縮量反轉+下影線",   # 末 Fold 5 筆，樣本薄
    "💎 b15+b17 下影線+急跌",        # 末 Fold 8 筆，樣本薄
    "💎 b15+b6 下影線+超賣",         # Fold2/Fold7 各 7 筆，樣本薄
    "💎 b12+b6 資金流向超賣",        # 兩次跑差 ~50%，數字會飄
}
# ══════════════════════════════════════════════════════════════════
# config.py -- 策略組合預設 & 全局常量
# ══════════════════════════════════════════════════════════════════
#
# V22.3 b19 深度ROC紙上復活 + 熊市豁免（2026-06-12）-- 來自 Phase 5 b17 救援三輪審計：
#
#   Phase 5 軌跡（混合真實回報為唯一裁決，HANDOVER28 §3）：
#     • Phase 5a 出場格點 7 格全敗，證三鐵則：b17 右尾驅動（止盈必死）、左尾也回歸
#       （任何價格型截尾出場有害）、時間窗 T10→T20 收斂（出場面天花板 ≈ +1.0%）。
#     • Phase 5b 制度×ROC 9 格：ROC 深度 -8→-10→-12 = 混合 +0.97→+2.49→+3.29 單調
#       高原；-10×全制度 為唯一同時過「混合≥+2.0% / 正Fold≥60% / 樣本≥500」三門的格
#       （混合 +2.49% / 正Fold 7/11 / n=1811）。
#     • Phase 5c 勝出格確認：剔除 2022 後其餘年份加權仍 ≈ +1.8%（非單一事件依賴）；
#       逐制度 alpha 核心在恐慌環境（強熊市 +8.54% 最肥、震盪市 -2.80% 最毒），與
#       indicators.py GATE 移除註解的既有發現（均值回歸在高波動環境更有效）獨立復現。
#
#   ⚠️ 口徑分裂（關鍵）：勝出格 +2.49% 含「強/弱熊市」時段，而 daily_scan 熊市閘門
#     （BEAR_LABELS_HARD）預設封鎖此時段 → 不開例外則線上真實預期僅 +1.48%（交易層）
#     / +0.93%（進場閘層），不過門。故本次處置為「紙上復活 + 熊市豁免」：
#       • 新增 b19（roc5<-10 深度版，indicators.py，獨立計算、不動 b17）。
#       • 新增 ACTIVE preset「💎 b19 深度ROC超跌反彈」，帶 max_hold_days=20（時間出場，
#         與回測完全對齊、無止損 T+1 偏差；出場仍含 s2 右尾保留器）。
#       • LIVE_PRESET_KEYS 加入 b19（路線 A 後首支復活；推播 + 紙上帳本向前驗證）。
#       • 新增 BEAR_EXEMPT_PRESETS：daily_scan 對此集合內策略豁免熊市閘門（per-strategy，
#         單常數模式，仿 LIGHT_POSITION_PRESETS）。b19 是唯一成員。
#       • b19 同列 LIGHT_POSITION_PRESETS（事件集中：強熊市 266 筆≈2-3 episode，
#         有效獨立事件數個位數 → 實盤輕倉，待帳本累積 30+ 已平倉再評真錢定倉）。
#       • REGIME_RECOMMENDATIONS：熊市觀察/弱熊市/強熊市補入 b19（其恐慌環境主場）。
#   ⚠️ 帳本須 reset 並與本次 config 同步（避免新舊口徑混帳；b19 為新策略，舊帳本無其紀錄，
#      但 LIVE 白名單由空轉非空，reset 後 b19 從乾淨狀態開始向前記錄）。
#   ⚠️ b17 buy/sell tuple、b15+b17 等既有組合一字未動（b19 為獨立新訊號，互不牽連）。
#   ⚠️ buy tuple 由 18 元素統一補位為 19（b1–b19）；sell 仍 8 元素。
#
# ──────────────────────────────────────────────────────────────────
# V22.2 Phase 4 全面降級（2026-06-11）-- survivorship 誠實口徑審計（Phase 1-4）：
#
#   背景：全 11 支 ACTIVE 的頂部 OOS（+6~10%）經查全部含生存者偏差（s2 布林上軌
#   出場在不漲的股票上永不觸發 → 強制平倉被排除在 OOS metrics 外，表頭虛高 -10~-21pp）。
#
#   Phase 1-4 結論（benchmark 改用「真實出場%／延伸追蹤」）：
#     • s2 / s2+s5 皆為「獲利了結型出場」，對「買了不漲」的長抱輸家無能為力（救不回）。
#     • 改用止損(stop10) / 時間(time20) 風險出場可修掉 survivorship，但「修好」後
#       真實回報全部落在打平帶（0 ~ +1%），無一支站上 +2% 實盤門檻。
#     • b17 看似 +2.64%（止損）為 cohort 選擇偏誤；混合真實回報僅 +0.38%(止損)/
#       +0.97%(時間)，平均 +0.68% → 同樣打平。（V22.3 補：深度過濾後 b19 才站上門檻。）
#     • b12+b6：止損都清不乾淨（真實 -2.41% / 勝率 25.7% / 差距 -5pp）→ 確認無 alpha。
#
#   處置（路線 A：全部降，無實盤）：
#     • 新增 LIVE_PRESET_KEYS = set()（空實盤白名單）；daily_scan 改讀此白名單，
#       不再用 💎 前綴判定 → 實盤推播清空。可逆：未來通過驗證把 key 加回 set 即復活。
#       （V22.3：b19 通過驗證，已加回。）
#     • b12+b6 由 ACTIVE 降入 LEGACY（確認死亡，非僅降級）。
#     • 其餘 10 支 key/💎 維持不變（避免 ~40 處引用的高風險遷移）；💎 原意「PIT 驗證
#       通過」技術上仍真（headline 確過），誠實口徑打平一事由本註解 + 帳本 benchmark 說明。
#     • 同步：LIGHT_POSITION_PRESETS / REGIME_RECOMMENDATIONS 移除 b12+b6。
#     • 帳本須 reset（舊持倉以純 s2 邏輯開立、benchmark 已轉真實出場%，口徑不一致）。
#
# ──────────────────────────────────────────────────────────────────
# V22.2-b 清理（2026-06-03）-- 來自 AUDIT-G 數據流掃描 🟡-6 / 🟡-7：
#   ⑥ 錯字統一：b14 相關全檔正名為「吞噬」（原誤植字已修正，含 b14 策略 key、BUY_LABELS、descs、
#      REGIME_RECOMMENDATIONS、LIGHT_POSITION_PRESETS、LEGACY）。所有消費端皆從本檔
#      dict 讀 key，故 live 比對不受影響；僅 paper_trades.json 既有舊名紀錄會在帳本頁
#      by_strategy 顯示新舊各一列（純顯示，不影響平倉）。
#   ⑦ 幽靈常數清理：
#      • 刪 PRESET_NAMES（全 app 無 import，純死碼）。PRESET_CUSTOM 仍被
#        backtest/buy_scan/sell_scan 使用，保留。
#      • 刪 BEAR_LABELS_SOFT（無任何消費端）。「熊市觀察允許保守策略」的語意
#        現由 REGIME_RECOMMENDATIONS["熊市觀察"] 實際表達，常數本身是誤導性死碼。
#
# ──────────────────────────────────────────────────────────────────
# V22.2 制度推薦補位 + b14 溫和降權（2026-05-31）-- 來自 HANDOVER21：
#
#   ① REGIME_RECOMMENDATIONS 補三個缺口（防呆冠軍表 vs 現行推薦的落差，
#      皆為已在 ACTIVE 的厚樣本/非輕倉策略，僅補入推薦清單，不動 tuple）：
#        • 熊市觀察 ← 💎 b17 ROC超跌反彈（+10.41% / 170筆 / 6fold）
#        • 轉折期   ← 💎 b12+b15 資金流向+下影線（+17.39% / 15筆 / 5fold，盯末Fold）
#        • 牛市警惕 ← 💎 b13 縮量反轉（+10.86% / 109筆 / 6fold）
#
#   ② b14 低位吞噬 溫和降權（MC 連四輪證據最弱：Sharpe 0.176 全場最低、
#      回撤 -37%/-88.7%、回報墊底；但 PIT WF 7/7 正 Fold、OOS +5.12%，
#      有 alpha 只是高波動 → 降權不誤殺）：
#        • 加入 LIGHT_POSITION_PRESETS（daily_scan 推播帶「⚠️輕倉」、
#          regime_matrix 冠軍表排除其冠軍資格）
#        • 強牛市 REGIME_RECs 把 b14 退到最末位（弱牛市本就在末位）
#        • 仍留在 ACTIVE、仍會被掃描/推播
#
# ──────────────────────────────────────────────────────────────────
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
#   b13 縮量反轉 / b14 低位吞噬 / b15 長下影線 / b16 下影線資金流入
#   b17 ROC超跌反彈 / b18 Z-Score資金流向；buy tuple 12→18 元素
#
# V18 新訊號（2026-05-10 → 2026-05-14）：
#   b12 資金流向；季節性過濾 is_seasonal()；b9 相對強弱 DEPRECATED
#
# V18 修復（2026-04-27）：
#   🔴-2 cooldown_days 解耦；🟡-2 T+1 持倉天數；🟡-7 港股 lot size 取整
#
# 欄位說明：
#   desc / buy(19) / sell(8) / min_hold_days / cooldown_days / seasonal_filter
#   （可選風險出場）stop_loss_pct / max_hold_days / take_profit_pct
#
# buy  tuple 順序：b1 b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 b13 b14 b15 b16 b17 b18 b19
# sell tuple 順序：s1  s2  s3  s4  s5  s6  s7  s8
#
# ══════════════════════════════════════════════════════════════════
# ACTIVE_PRESETS -- 實盤候選 / 推薦策略（共 11 支；V22.3 新增 b19 深度ROC）
# 用於：制度矩陣全跑、共振掃描、Tab 推薦清單、daily_scan 推播
# ⚠️ V22.3：實盤白名單 LIVE_PRESET_KEYS 含 b19（紙上向前驗證中）；其餘 10 支僅供分析/回測。
#
#   分組：
#   ① 純單訊號形態主力（7）：b13 b14 b15 b16 b17 b18 b19
#   ② 形態+形態雙確認（3，V22.1）：b12+b15 主力 / b13+b15 b15+b17 輔助輕倉
#   ③ 含 b6 輔助（1）：b15+b6   （b12+b6 已降 LEGACY）
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
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b14 低位吞噬": {
        "desc": "【💎 PIT 驗證通過｜⚠️ V22.2 降權：輕倉】低位半吞噬形態："
                "昨陰今陽吞噬過半 + 放量 + MA20 下方。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +3.43% / OOS +5.64% / 退化 -219.4% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +5.12%，每 Fold 47-162 筆，OOS 均高於 IS、最穩定。"
                "⚠️ MC 連四輪證據最弱（Sharpe 0.176 全場最低、回撤 -37%/-88.7%、回報墊底）→ "
                "V22.2 加輕倉旗標、牛市推薦退末位；有 alpha 但高波動，實盤勿重倉。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b15 長下影線": {
        "desc": "【💎 PIT 驗證通過｜主力｜最佳組合催化劑】長下影線："
                "下影>實體2倍+收高+MA20下方。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +3.91% / OOS +5.82% / 退化 -106.4% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +5.56%，每 Fold 168-541 筆（樣本最厚），"
                "純價格形態無指標閾值，是 V22.1 形態+形態組合的最佳基底。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b16 下影線資金流入": {
        "desc": "【💎 PIT 驗證通過｜主力】b16：長下影線+放量陽燭（量1.5-12x）整合訊號。"
                "s2 布林上軌出場，MIN5。"
                "PIT WF：IS +6.43% / OOS +7.30% / 退化 -101.7% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +7.18%，每 Fold 22-92 筆，2022 熊市 OOS +8.33%。",
        "buy":  (False, False, False, False, False, False, False, False, False, False,
                 False, False, False, False, False, True,  False, False, False),
        "sell": (False, True, False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b17 ROC超跌反彈": {
        "desc": "【💎 PIT 驗證通過｜主力】b17：5日ROC < -8%（急跌），"
                "收盤 < MA20，RSI<45，陽燭。與 b6 互補，捕捉急跌但 RSI 未到 30 的反彈。"
                "s2 布林上軌出場，MIN5。"
                "PIT WF：IS +5.96% / OOS +8.73% / 退化 -141.8% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +8.12%（11 Fold），每 Fold 39-419 筆，全程無負 Fold。"
                "⚠️ V22.2 誠實口徑：混合真實回報僅 +0.68%（頂部 OOS 含生存者偏差）。"
                "V22.3：深度版見 b19（roc5<-10 + 熊市豁免才站上 +2% 門檻）。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, False, False, True, False, False),
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
                 False, False, False, False, False, False, False, False, False, True, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "💎 b19 深度ROC超跌反彈": {
        "desc": "【💎 V22.3 紙上復活｜實盤白名單｜⚠️ 輕倉 + 熊市豁免】"
                "b17 深度版：5日ROC < -10%（更深急跌），收盤 < MA20，RSI<45，陽燭。"
                "出場：s2 布林上軌 + 超時20日（時間出場與回測對齊，無止損 T+1 偏差），MIN5。"
                "Phase 5 證據（混合真實回報）：ROC 深度 -8→-10→-12 = +0.97→+2.49→+3.29 單調高原；"
                "-10 為唯一過三門格（混合 +2.49% / 正Fold 7/11 / n=1811）。"
                "剔除 2022 後其餘年份仍 ≈ +1.8%（非單一事件）。"
                "⚠️ alpha 核心在恐慌環境（強熊市 +8.54% 最肥、震盪市 -2.80% 最毒）→ "
                "須配 BEAR_EXEMPT_PRESETS 熊市豁免才拿得到 +2.49%（剔硬熊僅 +1.48%）。"
                "⚠️ 事件集中（強熊市 266 筆 ≈ 2-3 episode）→ 輕倉，待帳本累積 30+ 已平倉再評真錢定倉。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, False, False, False, False, False, False, True),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
        "max_hold_days": 20,
    },

    "💎 b17+b6 ROC急跌+超賣": {
        "desc": "【💎 V22.3 紙上復活｜實盤白名單｜⚠️ 輕倉】b17（ROC急跌）AND b6（RSI<30）雙確認。"
                "出場：s2 布林上軌 + 超時20日（時間出場，無止損 T+1 偏差），MIN5。"
                "V22.3 三閘：max_hold 敏感度全橫盤≥+2%（混合真實 h20 +2.67%）、正Fold 過半、"
                "MC 達 b19 級（破產 0%、Sharpe +0.300、最差回撤 -71%、n~847 最厚）。"
                "⚠️ 與 b19 同屬 ROC 家族（非獨立分散），b6 雙確認樣本偏薄 → 輕倉。",
        "buy":  (False, False, False, False, False, True,  False, False,
                 False, False, False, False, False, False, False, False, True, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
        "max_hold_days": 20,
    },

    "💎 b13+b17 縮量反轉+急跌": {
        "desc": "【💎 V22.3 紙上復活｜實盤白名單｜⚠️ 輕倉】b13（縮量反轉）AND b17（ROC急跌）雙確認。"
                "出場：s2 布林上軌 + 超時20日（時間出場，無止損 T+1 偏差），MIN5。"
                "V22.3 三閘：max_hold 敏感度全橫盤≥+2%（混合真實 h20 +3.07%）、正Fold 過半、"
                "MC 達 b19 級（破產 0%、Sharpe +0.377 最高、最差回撤 -64%）。"
                "⚠️ 與 b19 同屬 ROC 家族（非獨立分散），樣本偏薄 → 輕倉。"
                "（V22.1 曾以止損/cohort 口徑淘汰，V22.3 時間出場口徑下復活。）",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, True,  False, False, False, True,  False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
        "max_hold_days": 20,
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
                 False, False, False, True,  False, False, True,  False, False, False, False),
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
                 False, False, False, False, False, False, True,  False, True,  False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
        "max_hold_days": 20,   # V22.3 出場改時間版（敏感度全橫盤≥+2%、MC 達 b19 級）
    },

    # ════════════════════════════════════════════════════════════
    # ③ 含 b6 輔助（b15+b6；b12+b6 已於 V22.2 Phase 4 降 LEGACY）
    # ════════════════════════════════════════════════════════════

    "💎 b15+b6 下影線+超賣": {
        "desc": "【💎 PIT 驗證通過｜⚠️ 輔助：樣本薄，輕倉】"
                "b15（長下影線）AND b6（RSI<30）雙確認。s2 布林上軌出場，MIN5。"
                "PIT WF：IS +8.15% / OOS +7.99% / 退化 -30.2% / 正Fold 7/7。"
                "V21 重跑（2026-05-28）：OOS +7.21% / 正Fold 6/7。"
                "⚠️ Fold2 與 Fold7 各僅 7 筆，**實盤建議輕倉**。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, True,  False, False, False, False),
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
    "🔬 b13+b15 縮量反轉+下影線 [LEGACY]": {
        "desc": "【📚 V22.3 降級 LEGACY｜敏感度刷掉】b13 AND b15 雙確認。"
                "V22.3 max_hold 敏感度：h15→h30 混合真實 +2.31%→+0.92% 單調衰減，"
                "edge 僅在極短持有成立、放長即垮（非穩健回歸節奏）；樣本最薄（n~323）。"
                "原 V22.1 OOS +7.91% 為止損/cohort 口徑虛高，時間出場口徑下不成立。",
        "buy":  (False, False, False, False, False, False, False, False,
                 False, False, False, False, True,  False, True,  False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },


    # ══════════════════════════════════════════════════════════════
    # V22.2 Phase 4 降級（2026-06-11，survivorship 誠實口徑審計）
    # ══════════════════════════════════════════════════════════════

    "🔬 b12+b6 資金流向超賣 [LEGACY]": {
        "desc": "【📚 LEGACY V22.2 Phase 4 移入 2026-06-11】b6（RSI<30）+ b12 AND，s2 出場，MIN5。"
                "誠實口徑（止損10% + 延伸追蹤）：真實出場 -2.41% / 真實勝率 25.7% / 差距 -5.0pp，"
                "連 10% 止損都清不乾淨——b6 進的是還在崩的票，接飛刀接晚了。確認無 alpha，降 LEGACY。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ══════════════════════════════════════════════════════════════
    # V22.1 淘汰（2026-05-28，形態+形態 PIT WF 後）
    # ══════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    # V22 新進 LEGACY（2026-05-28，PIT 全策略複審）
    # ══════════════════════════════════════════════════════════════

    # ── b6 雙確認家族：Fold7 樣本砍 80-100%，表頭虛高 ──────────────

    "🔬 b18+b6 Z-Score超賣 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b18 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +7.98% / 正Fold 5/6 / Fold7=1 筆。"
                "降級原因：對照 b18 同期 59 筆，加 b6 後砍 98%（剩 1 筆），符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False,
                 False, False, False, False, False, False, False, False, False, True, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    "🔬 b13+b6 縮量反轉+超賣 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b13 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +8.67% / 有效6/7 / Fold7=0 筆。"
                "降級原因：Fold7 訊號完全消失，Fold2 僅 2 筆，符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, True,  False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── b6 + 三重出場 / 季節性家族：b6 進場無 alpha 已確認 ──────────

    "🔬 資金流向測試 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b12 資金流向 + s2+s6+s8 三重出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +2.41% / 正Fold 3/6。"
                "降級原因：與 💎 b12+b6 重疊，三重出場 + MIN30 無真實 alpha 增量。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 冠軍+季節性 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】冠軍（b6/s2+s6+s8）+ 季節性（1/4/10月），MIN30。"
                "PIT V21（2026-05-28）：OOS +4.16% / 正Fold 5/6 / Fold5=3 筆。"
                "降級原因：b6 家族雜訊，符合衍生鐵則 1。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    "🔬 均值回歸+季節性 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】純均值回歸（b6/s6）+ 季節性，MIN30。"
                "PIT V21（2026-05-28）：OOS +3.18% / 正Fold 4/6。降級原因：b6 家族雜訊。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
        "seasonal_filter": True,
    },

    # ── AND 過嚴歸零家族：符合衍生鐵則 4 ─────────────────────────

    "🔬 b11+b5 KDJ超賣布林雙確認 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b5 AND b11 AND 進場，s8 出場，MIN5。"
                "PIT V21（2026-05-28）：**無交易**（雙指標 AND 歸零）。符合衍生鐵則 4。",
        "buy":  (False, False, False, False, True,  False, False, False, False, False, True,  False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, False, False, True),
        "min_hold_days": 5,
    },

    "🔬 b3+b7+b8 底背離趨勢確認 [LEGACY]": {
        "desc": "【📚 LEGACY V22 移入 2026-05-28】b3 AND b7 AND b8，s5+s6 出場，MIN10。"
                "PIT V21（2026-05-28）：**無交易**（三條件 AND 歸零）。符合衍生鐵則 3、4。",
        "buy":  (False, False, True,  False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, True,  True,  False, False),
        "min_hold_days": 10,
    },

    # ══════════════════════════════════════════════════════════════
    # 對照組 / 歷史 LEGACY（之前批次移入）
    # ══════════════════════════════════════════════════════════════

    "💎 純粹均值回歸 [對照]": {
        "desc": "【📚 LEGACY 對照組】純 b6/s6，無 MIN。"
                "PIT V21（2026-05-28）：OOS +2.16% / 正Fold 3/6（b6 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎+s2 三重出場 [無MIN對照]": {
        "desc": "【📚 LEGACY 對照組】b6/s2+s6+s8 無 MIN。"
                "PIT V21（2026-05-28）：OOS +0.32% / 正Fold 3/6（b6 雜訊最低端）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "cooldown_days": 0,
    },

    "💎M20 純粹均值回歸MIN20 [對照]": {
        "desc": "【📚 LEGACY MIN 參數對照】b6/s6 MIN20。"
                "PIT V21（2026-05-28）：OOS +2.05% / 正Fold 3/6（b6 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 20,
    },

    "🔄基準 純MACD週期 [對照]": {
        "desc": "【📚 LEGACY 對照】純 b7/s6 無過濾。"
                "PIT V21（2026-05-28）：OOS **-0.94%** / 正Fold 2/6。符合衍生鐵則 3。",
        "buy":  (False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "cooldown_days": 0,
    },

    "💎K30 純KDJ超賣MIN30 [已驗證]": {
        "desc": "【📚 LEGACY 已驗證失敗】b11 KDJ超賣 MIN30。"
                "PIT V21（2026-05-28）：OOS **-1.18%** / 正Fold 3/7。指標閾值類無 alpha。",
        "buy":  (False, False, False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔄+ MACD+趨勢MIN30 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-09】MACD金叉+趨勢確認，MACD死叉出，MIN30。"
                "PIT V21（2026-05-28）：OOS **-0.43%** / 正Fold 4/6。符合衍生鐵則 3。",
        "buy":  (False, False, False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡ 突破確認 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】強牛市突破策略。"
                "PIT V21（2026-05-28）：OOS **-1.25%** / 正Fold 3/7。符合衍生鐵則 3。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (True,  False, False, True,  False, False, False, False),
        "cooldown_days": 5,
    },

    "💎K+ M30 雙超賣雙出MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b6+b11 KDJ 雙超賣 + 雙出場 MIN30。"
                "PIT V21（2026-05-28）：OOS +0.53% / 正Fold 3/5（b6/KDJ 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "💎KK30 RSI+KDJ雙超賣MIN30 [精選→LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b6+b11 RSI+KDJ 雙超賣 MIN30。"
                "PIT V21（2026-05-28）：OOS **-1.48%** / 正Fold 3/6。雙指標疊加仍雜訊。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, True,  False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── b9 相對強弱：DEPRECATED 永久 False ───────────────────────

    "🔬 相對強弱測試 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 相對強弱單訊號。b9 已 DEPRECATED 永久 False。",
        "buy":  (False, False, False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+冠軍買入_冠軍出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+冠軍買入_均值回歸出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔬 b9+均值回歸買入_冠軍出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, True,  True,  False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "🔬 b9+均值回歸買入_均值回歸出場 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-10】b9 已 DEPRECATED 永久 False，必然無交易。",
        "buy":  (False, False, False, False, True,  True,  False, False, True,  False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── 已驗證 BIAS（教訓紀錄，勿實盤）────────────────────────────

    "📈 均值回歸 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS 警示】b5+b6/s2+s5。"
                "PIT V21（2026-05-28）：OOS +7.64% / 正Fold 6/7。"
                "⚠️ 數字高但比延伸追蹤 +3.81% 高，可能 survivorship bias 殘留，**勿復活**。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, True,  False, False, False),
        "cooldown_days": 0,
    },

    "🏗️M30 底部形態MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b4+b7 + MIN30。"
                "PIT V21（2026-05-28）：OOS +1.63% / 正Fold 3/7。MIN30 強行抓底部假突破。",
        "buy":  (False, False, False, True,  False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "⚡+ 突破確認長持MIN30 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY BIAS】b1+b8 + MACD死叉 + MIN30。"
                "PIT V21（2026-05-28）：OOS +0.38% / 正Fold 4/7（趨近零）。符合衍生鐵則 3。",
        "buy":  (True,  False, False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "💎++ M30 趨勢過濾版 [BIAS-勿實盤]": {
        "desc": "【⚠️ LEGACY 嚴重過擬合】b6+b8 進場，s6+s8 雙出場，MIN30。"
                "PIT V21（2026-05-28）：OOS **-1.01%** / 正Fold 2/6（OOS 虧損）。"
                "教訓：b6（RSI<30）通常在下跌中，此時 b8 不成立，邏輯互斥。",
        "buy":  (False, False, False, False, False, True,  False, True,  False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    # ── V18 PIT 複審移入 LEGACY（b6 進場 MIN30 家族）─────────────

    "💎+s2 M30 三重出場版【實盤冠軍】": {
        "desc": "【📚 LEGACY 移入 2026-05-15，前實盤冠軍】b6 進場，s2+s6+s8 三重出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +4.39% / 正Fold 5/6（2022-23 熊市虧損）。"
                "b6 家族最強變體，但數字會飄，不再實盤。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, True,  False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

    "💎M30 純粹均值回歸MIN30": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b6 進場，s6 出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +2.83% / 正Fold 4/6（b6 雜訊區間）。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    "🔄🔄M30 均值回歸長持MIN30": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b5+b6 進場，s6 出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +3.95% / 正Fold 4/6（b6 雜訊區間略高端）。",
        "buy":  (False, False, False, False, True,  True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, False),
        "min_hold_days": 30,
    },

    # ── V19 雙確認：AND 過嚴，2026-05-15 放棄 ────────────────────

    "🔬 b14+b6 吞噬+超賣 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-15】b14 AND b6 雙確認。"
                "PIT V21（2026-05-28）：OOS +7.18% / 有效4/4 / Fold7=0 筆。符合衍生鐵則 2。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False,
                 False, False, False, True,  False, False, False, False, False),
        "sell": (False, True,  False, False, False, False, False, False),
        "min_hold_days": 5,
    },

    # ── V21 PIT 複審移入 LEGACY（2026-05-23）──────────────────────

    "+ M30 RSI進雙出MIN30 [LEGACY]": {
        "desc": "【📚 LEGACY 移入 2026-05-23】b6 進場，s6+s8 雙出場，MIN30。"
                "PIT V21（2026-05-28）：OOS +1.03% / 正Fold 4/7（接近隨機）。"
                "2022-23 熊市 Fold1-3 連虧，末 Fold 僅 38 筆，b6 家族同源同症，符合衍生鐵則 1。",
        "buy":  (False, False, False, False, False, True,  False, False, False, False, False, False, False, False, False, False, False, False, False),
        "sell": (False, False, False, False, False, True,  False, True),
        "min_hold_days": 30,
    },

}


# ══════════════════════════════════════════════════════════════════
# REGIME_RECOMMENDATIONS -- 8 制度 → 推薦策略對照表（V22.3 更新）
# 弱熊市 / 強熊市 設為空 list，視為實盤禁區
#
# V22.3 變更（2026-06-12）：
#   • 熊市觀察 ← 補入 💎 b19 深度ROC超跌反彈（其恐慌環境主場、+2.93%/234筆）。
#   • 弱熊市 / 強熊市 ← 補入 💎 b19（唯一在 BEAR_EXEMPT_PRESETS 內、可在硬熊推播的策略；
#     b19 alpha 核心正在此 — 強熊市 +8.54% 最肥。其餘策略仍受熊市閘門封鎖、此處不列）。
#     注意：弱熊市/強熊市仍是「一般策略」實盤禁區；此處列 b19 純為 daily_scan 熊市豁免時
#     的推薦依據，multi_scan UI 的硬熊判定（_BEAR_LABELS）仍會擋住整頁買入掃描。
#
# V22.2 變更（2026-05-31）：
#   • 牛市警惕 ← 補入 💎 b13 縮量反轉（防呆冠軍 +10.86% / 109筆 / 6fold）
#   • 熊市觀察 ← 補入 💎 b17 ROC超跌反彈（防呆冠軍 +10.41% / 170筆 / 6fold）
#   • 轉折期   ← 補入 💎 b12+b15 資金流向+下影線（防呆冠軍 +17.39% / 15筆 / 5fold）
#   • 強牛市   → b14 退到清單最末位（弱牛市本就在末位，未動）
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
        "💎 b16 下影線資金流入",
        "💎 b14 低位吞噬",          # V22.2：退到末位（MC 最弱、輕倉）
    ],
    "弱牛市": [
        "💎 b15 長下影線",
        "💎 b17 ROC超跌反彈",
        "💎 b16 下影線資金流入",
        "💎 b13 縮量反轉",
        "💎 b14 低位吞噬",          # 本就在末位，未動
    ],
    "牛市警惕": [
        "💎 b13+b17 縮量反轉+急跌",  # V22.4 矩陣領投：該制度最佳 Sharpe +0.74 / +8.3% / n90（LIVE）
        "💎 b13 縮量反轉",          # V22.2 補入（厚樣本）
        "💎 b15+b17 下影線+急跌",   # 既有 LIVE，矩陣 +6.2% 仍正 → 保留（never-pause 正 cohort）
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
        "💎 b17 ROC超跌反彈",
    ],
    "熊市觀察": [
        "💎 b17+b6 ROC急跌+超賣",   # V22.4 矩陣領投：該制度最佳 +7.0% / Sharpe +0.25 / n98；孤兒 b17+b6 歸位（軟熊非硬熊豁免限制，可推）
        "💎 b19 深度ROC超跌反彈",   # V22.3 補入（恐慌環境主場、熊市豁免）；矩陣 +2.9% 仍正 → 保留
        "💎 b17 ROC超跌反彈",       # V22.2 補入（厚樣本，原靠兩支輕倉漏列）
        "💎 b12+b15 資金流向+下影線",
        "💎 b15+b6 下影線+超賣",
        "💎 b16 下影線資金流入",
    ],
    "弱熊市":   ["💎 b13+b17 縮量反轉+急跌", "💎 b19 深度ROC超跌反彈"],   # V22.3/V22.4：熊市豁免成對；矩陣 b13+b17 +4.6%(過門檻) 排前、b19 +1.3%(正但未過,never-pause 保留)；須同列此處否則 daily_scan exempt_filtered 會靜默漏掉
    "強熊市":   ["💎 b19 深度ROC超跌反彈", "💎 b13+b17 縮量反轉+急跌"],   # V22.3：alpha 最肥（+8.54%）；b13+b17 同列熊市豁免（與 BEAR_EXEMPT_PRESETS 成對）
    # 震盪市：閘門=0（實盤禁區，gate 在 daily_scan 提前 return，永不查此表），刻意不列推薦。
    #          消費端皆 .get(label, 預設) fallback，無 dangling 風險。（V22.4 清理死碼 — 勿復原）
    "轉折期": [
        "💎 b19 深度ROC超跌反彈",      # V22.4 矩陣領投：該制度唯一過 +2%（+2.8% / n192）；轉折期整體偏弱（0.5× 定倉）
        "💎 b12+b15 資金流向+下影線",  # V22.2 補入（該制度實測最佳、是主力，原漏列）
        "💎 b15+b17 下影線+急跌",      # 既有 LIVE，矩陣 +1.7% 仍正 → 保留（never-pause 正 cohort）
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

# ══════════════════════════════════════════════════════════════════
# LIVE_PRESET_KEYS -- 實盤推播白名單（V22.2 Phase 4 新增，路線 A）
# ══════════════════════════════════════════════════════════════════
# daily_scan 只推播 key 在此集合內的策略（取代舊的「💎 前綴」判定）。
# V22.2 Phase 4 結論：全 ACTIVE 在 survivorship 誠實口徑下打平/負，無一過 +2% 實盤門檻
# → 清空白名單，停止所有實盤推播。ACTIVE_PRESETS 仍保留供分析/回測/制度矩陣使用。
#
# V22.3（2026-06-12）：b19 深度ROC 通過混合真實回報 +2.49% 三門驗證（Phase 5），
#   為路線 A 後首支復活策略。紙上向前驗證中（非真錢）；待帳本累積 30+ 已平倉再評真錢定倉。
#
# 復活方式（可逆）：未來某策略以「真實出場%／混合真實回報」通過驗證，
#   把它的完整 key（含 💎 前綴，需與 ACTIVE_PRESETS 一字不差）加入下方集合即可。
# ⚠️ 變更此集合務必同步協調帳本 reset（避免新舊口徑混在同一份帳本）。
LIVE_PRESET_KEYS: set = {
    "💎 b19 深度ROC超跌反彈",   # V22.3 紙上復活（混合真實回報 +2.49%，須配熊市豁免）
    "💎 b17+b6 ROC急跌+超賣",       # V22.3 復活（時間出場混合真實 +2.67%，MC 達 b19 級）⚠️輕倉
    "💎 b15+b17 下影線+急跌",        # V22.3 復活（混合真實 +3.53%，MC 達 b19 級）⚠️輕倉
    "💎 b13+b17 縮量反轉+急跌",     # V22.3 復活（混合真實 +3.07%，MC Sharpe 最高 +0.377）⚠️輕倉
}

# ══════════════════════════════════════════════════════════════════
# BEAR_EXEMPT_PRESETS -- 熊市閘門豁免白名單（V22.3 新增）
# ══════════════════════════════════════════════════════════════════
# daily_scan 預設在 BEAR_LABELS_HARD（強熊市/弱熊市）完全停止掃描（實盤禁區）。
# 但 b19 的 alpha 核心正在恐慌環境（強熊市混合 +8.54% 最肥）；若硬熊一律封鎖，
# 線上真實預期僅 +1.48%（剔硬熊）— 不過門。故對「此集合內的策略」豁免熊市閘門，
# 讓它們在硬熊制度仍可被掃描 / 推播 / 記帳（per-strategy 豁免，非全域解禁）。
#
# 機制（daily_scan）：硬熊制度下，一般策略全停；但若 BEAR_EXEMPT_PRESETS 非空，
#   仍對「LIVE_PRESETS ∩ BEAR_EXEMPT_PRESETS」跑掃描並推播（帶熊市風險標註）。
# ⚠️ 豁免 ≠ 無風險：熊市接深跌反彈的回撤與心理壓力是另一量級，故 b19 同列輕倉。
# 增減只需編輯本集合（單常數模式，仿 LIGHT_POSITION_PRESETS）。
BEAR_EXEMPT_PRESETS: set = {
    "💎 b19 深度ROC超跌反彈",
    "💎 b13+b17 縮量反轉+急跌",   # V22.3 熊市scope WF（2026-06-15, test_bear_scope_wf）：硬熊cohort +5.99%、剔最賺episode後 +4.40%、5/6 fold正、N_eff4.5（不劣於 b19）⚠️輕倉
}

# 🟡-7（AUDIT-G 2026-06-03）：PRESET_NAMES 已刪除（全 app 無 import，純死碼）。
# PRESET_CUSTOM 仍被 backtest / buy_scan / sell_scan 使用，保留。
PRESET_CUSTOM = "✏️ 自定義"

BUY_LABELS = [
    "Ⓑ1 突破放量",      "Ⓑ2 MA5金叉",      "Ⓑ3 底背離",       "Ⓑ4 底部突破",
    "Ⓑ5 布林下軌",      "Ⓑ6 RSI超賣",      "Ⓑ7 MACD金叉",    "Ⓑ8 趨勢確認",
    "Ⓑ9 相對強弱(停用)", "Ⓑ10 縮量回調",    "Ⓑ11 KDJ超賣金叉", "Ⓑ12 資金流向",
    "Ⓑ13 縮量反轉",     "Ⓑ14 低位吞噬",    "Ⓑ15 長下影線",    "Ⓑ16 下影線資金流入",
    "Ⓑ17 ROC超跌反彈",  "Ⓑ18 Z-Score資金流向", "Ⓑ19 深度ROC超跌反彈",
]
SELL_LABELS = [
    "Ⓢ1 頭部破MA20", "Ⓢ2 布林上軌", "Ⓢ3 縮量頂部", "Ⓢ4 放量急跌",
    "Ⓢ5 RSI超買",   "Ⓢ6 MACD死叉", "Ⓢ7 三日陰線",  "Ⓢ8 KDJ高位死叉",
]

B_NAMES = ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8",
           "b9", "b10", "b11", "b12", "b13", "b14", "b15", "b16",
           "b17", "b18", "b19"]
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
# 🟡-7（AUDIT-G 2026-06-03）：BEAR_LABELS_SOFT 已刪除（無任何消費端）。
# 「熊市觀察＝觀察區、允許保守策略」的語意現由 REGIME_RECOMMENDATIONS["熊市觀察"]
# 直接表達（該制度有一份推薦清單；不在 BEAR_LABELS_HARD 內，故掃描不會被硬停）。
BEAR_LABELS_HARD = {"弱熊市", "強熊市"}   # 實盤禁區，掃描完全停止（BEAR_EXEMPT_PRESETS 例外）
# ── 實盤倉位提示 ─────────────────────────────────────────────────────────────
# 樣本薄 / 數字會飄 / 風險偏高的輔助策略：daily_scan 推播時加「⚠️輕倉」標記，
# 提醒實盤勿重倉。依 HANDOVER19 第五點 + HANDOVER21 b14 降權標註 + V22.3 b19 事件集中。
LIGHT_POSITION_PRESETS = {
    "💎 b15+b17 下影線+急跌",        # 末 Fold 8 筆，樣本薄
    "💎 b15+b6 下影線+超賣",         # Fold2/Fold7 各 7 筆，樣本薄
    "💎 b14 低位吞噬",               # V22.2：MC 連四輪最弱（Sharpe 0.176、回撤 -88.7%），高波動降權
    "💎 b19 深度ROC超跌反彈",        # V22.3：事件集中（強熊市 266 筆≈2-3 episode），熊市接刀高波動
    "💎 b17+b6 ROC急跌+超賣",        # V22.3 復活：ROC 家族（與 b19 相關），b6 樣本薄 → 輕倉
    "💎 b13+b17 縮量反轉+急跌",      # V22.3 復活：ROC 家族（與 b19 相關），樣本薄 → 輕倉
}
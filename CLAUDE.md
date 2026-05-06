# 港股狙擊手 Dash 版 — Claude Code 工作手冊

## 專案背景
從 Streamlit V18 遷移到 Dash。核心業務邏輯在 core/ 目錄，不要改動邏輯。

## 技術棧
- Dash 2.18 + dash-bootstrap-components 1.6
- flask-caching（取代 st.cache_data）
- diskcache + DiskcacheManager（background callback 用）
- 部署目標：Render

## 核心運作邏輯
- 當系統根據我設定好的技術指標策略（例如各種買入組合），判定某隻股票符合進出場條件時，能夠自動發送交易訊號來提醒我。 透過這個 Project，我希望達成以下三個核心目的： 大幅節省時間成本： 將日常繁瑣的看盤與手動篩選股票工作自動化，減少我每天需要耗費的盯盤時間。 消除情緒交易 (Emotional Trading)： 透過系統化的客觀訊號來輔助決策，克服主觀偏見與人性弱點，做到嚴格執行交易紀律。 提升交易績效： 藉由不斷回測、優化策略組合，最終目的是實質提高整體交易的勝率 (Win Rate) 與投資回報率 (ROI)，並讓這套系統具備未來商業化的潛力。


## 目錄結構（目標）
my-hk-stock-web-dash/
├── app.py
├── core/               ← 已有，不改邏輯
│   ├── backtest.py     ← V18，不動
│   ├── indicators.py
│   ├── signals.py
│   ├── walk_forward.py
│   ├── config.py
│   ├── data.py
│   └── stocks.txt
├── pages/
├── components/
├── callbacks/
└── assets/style.css

## 注意事項
- 我需要你（Claude）在這個專案中扮演我的量化交易顧問與代碼助手，協助我審查策略邏輯、優化代碼效能，並建立穩定可靠的提醒機制。
- core/ 的檔案要移除 streamlit import，改用 flask_caching
- config.py 永遠用整個重寫，不用 str.replace
- 制度標籤用「震盪市」不是「震盪」
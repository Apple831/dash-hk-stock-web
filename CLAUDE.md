# 港股狙擊手 Dash 版 — Claude Code 工作手冊

## 專案背景
從 Streamlit V18 遷移到 Dash。核心業務邏輯在 core/ 目錄，不要改動邏輯。

## 技術棧
- Dash 2.18 + dash-bootstrap-components 1.6
- flask-caching（取代 st.cache_data）
- diskcache + DiskcacheManager（background callback 用）
- 部署目標：Render

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
- core/ 的檔案要移除 streamlit import，改用 flask_caching
- config.py 永遠用整個重寫，不用 str.replace
- 制度標籤用「震盪市」不是「震盪」
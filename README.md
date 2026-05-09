# dash-hk-stock-web

港股狙擊手 Dash 版，部署於 https://hk-stock-sniper.onrender.com

---

## 每日自動掃描 + Telegram 通知

`scripts/daily_scan.py` 由 Render cron job 每個交易日 HKT 16:30（UTC 08:30）自動執行：
掃描 `stocks.txt` 全部股票，對 `core/config.py` 的 `ACTIVE_PRESETS` 5 個策略做 AND 邏輯買入訊號判斷。
**有命中才發 Telegram；無命中靜默退出。**

### 1. 建立 Telegram Bot

1. 在 Telegram 找 [@BotFather](https://t.me/BotFather)
2. 傳 `/newbot`，依指示命名
3. 取得 token，格式類似 `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`

### 2. 取得 chat_id

1. 在 Telegram 對自己建立的 bot 傳任意一條訊息（個人通知）
   - 或：把 bot 加入 group / channel 並傳一條訊息（群組通知）
2. 開啟瀏覽器存取：
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
3. 在 JSON 找 `result[0].message.chat.id`
   - 個人聊天：正整數（例 `123456789`）
   - 群組：負整數（例 `-1001234567890`）

### 3. 在 Render 設定環境變數

`render.yaml` 已用 `sync: false` 宣告，token 不會 commit 進 git。需要在 Render Dashboard 手動填入：

1. Render Dashboard → `daily-scan` service → Environment
2. 加入：
   - `TELEGRAM_BOT_TOKEN` = 步驟 1 的 token
   - `TELEGRAM_CHAT_ID`   = 步驟 2 的 chat_id
3. 儲存後 Render 會重建 cron service

可在 Dashboard 點 **Trigger Run** 立即測試一次（不必等 16:30）。

### 4. 本機測試

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456:ABC..."
$env:TELEGRAM_CHAT_ID   = "123456789"
python scripts/daily_scan.py
```

無命中時會印 `[SCAN] ... 無命中，靜默退出` 並 exit 0；
有命中會印訊息內容並發送 Telegram；
失敗會印 traceback 並 exit 1。

### 訊息格式範例

```
🏹 港股狙擊手 每日掃描
📅 2026-05-10
🌍 制度：震盪市

🟢 買入訊號：
• 0700.HK｜💎+s2 M30 三重出場版【實盤冠軍】, 💎M30 純粹均值回歸MIN30｜RSI=28.3｜現價 412.0
• 2318.HK｜💎+ M30 RSI進雙出MIN30｜RSI=27.1｜現價 38.5
```

### Cron 排程

`render.yaml` 設定 `schedule: "30 8 * * 1-5"`（UTC 08:30 = HKT 16:30，週一到週五）。
若 Yahoo 收盤資料延遲導致 16:30 命中數偏少，可改為 `"0 9 * * 1-5"`（HKT 17:00）。

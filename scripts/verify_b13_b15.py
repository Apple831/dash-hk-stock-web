import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

from data import get_cached
from indicators import precompute_signals
from config import B_NAMES, ACTIVE_PRESETS

print("B_NAMES 數量：", len(B_NAMES))
for name, p in ACTIVE_PRESETS.items():
    if len(p["buy"]) != 16:
        print("tuple 錯誤：" + name + " = " + str(len(p["buy"])))

tickers = ["0700.HK", "9988.HK", "1810.HK", "0005.HK", "2318.HK",
           "0175.HK", "1211.HK", "2333.HK", "0941.HK", "3690.HK"]

combos = {"b15+b6": ("b15","b6"), "b13+b6": ("b13","b6"), "b16": ("b16", None)}
totals = {k: 0 for k in combos}

for ticker in tickers:
    df = get_cached(ticker, "1y")
    sigs = precompute_signals(df)
    row = ticker + ":  "
    for name, (ba, bb) in combos.items():
        if bb:
            n = int((sigs[ba] & sigs[bb]).sum())
        else:
            n = int(sigs[ba].sum())
        totals[name] += n
        row += name + "=" + str(n) + "  "
    print(row)

print("")
for name, total in totals.items():
    status = "OK" if total >= 5 else "警告"
    print(name + " 合計: " + str(total) + "  " + status)
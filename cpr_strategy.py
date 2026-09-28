"""Central Pivot Range (CPR) daily backtest on real Alpaca historical bars.

CPR (from the PREVIOUS day's High / Low / Close):
    pivot = (H + L + C) / 3
    bc    = (H + L) / 2
    tc    = 2*pivot - bc
    top   = max(tc, bc)      # top central
    bottom= min(tc, bc)      # bottom central
    width = (top - bottom) / pivot        # narrow CPR = trending day

Rule (no look-ahead — CPR uses yesterday, direction decided at today's OPEN):
    open ABOVE cpr top     -> LONG   (buy at open, exit at close)
    open BELOW cpr bottom  -> SHORT  (sell at open, cover at close)
    open INSIDE the CPR    -> no trade (rangebound)

Each trade is intraday (open -> close). A round-trip cost is applied.
Runs on free Alpaca historical data (IEX feed) — no options data needed.
"""
import json

import numpy as np
import pandas as pd
from datetime import datetime

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

KEYS = json.load(open(r"C:\Users\SHALVA\apolloprojects\quanttrading\cpr_keys.json"))
SYMBOLS = ["SPY", "QQQ", "AAPL"]
START = datetime(2022, 1, 1)
END = datetime(2026, 9, 1)
COST = 0.0002          # ~2 bps round-trip friction
NARROW_ONLY = False    # if True, only trade when CPR is narrow (below its median width)

_client = StockHistoricalDataClient(KEYS["api_key"], KEYS["api_secret"])


def fetch(symbol):
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                           start=START, end=END, feed=DataFeed.IEX)
    bars = _client.get_stock_bars(req).df
    if bars is None or bars.empty:
        return None
    df = bars.xs(symbol, level=0) if isinstance(bars.index, pd.MultiIndex) else bars
    return df[["open", "high", "low", "close"]].copy()


def cpr_backtest(df):
    ph, pl, pc = df["high"].shift(1), df["low"].shift(1), df["close"].shift(1)
    pivot = (ph + pl + pc) / 3
    bc = (ph + pl) / 2
    tc = 2 * pivot - bc
    top = np.maximum(tc, bc)
    bot = np.minimum(tc, bc)
    width = (top - bot) / pivot

    o, c = df["open"], df["close"]
    narrow = width < width.median() if NARROW_ONLY else True

    long_sig = (o > top) & narrow
    short_sig = (o < bot) & narrow

    ret = pd.Series(0.0, index=df.index)
    ret[long_sig] = (c - o) / o
    ret[short_sig] = (o - c) / o
    traded = long_sig | short_sig
    ret[traded] = ret[traded] - COST

    out = df.assign(ret=ret, traded=traded,
                    side=np.where(long_sig, "L", np.where(short_sig, "S", "-")))
    return out.dropna(subset=["ret"])


def stats(df):
    t = df[df["traded"]]
    n = len(t)
    if n == 0:
        return None
    wins = t.loc[t["ret"] > 0, "ret"]
    losses = t.loc[t["ret"] <= 0, "ret"]
    equity = (1 + t["ret"]).cumprod()
    dd = (equity / equity.cummax() - 1).min()
    gl = -losses.sum()
    pf = wins.sum() / gl if gl > 0 else float("inf")
    bh = df["close"].iloc[-1] / df["open"].iloc[0] - 1
    return {
        "trades": n,
        "win_rate": len(wins) / n * 100,
        "total_return_pct": (equity.iloc[-1] - 1) * 100,
        "profit_factor": pf,
        "avg_win_pct": wins.mean() * 100 if len(wins) else 0.0,
        "avg_loss_pct": losses.mean() * 100 if len(losses) else 0.0,
        "max_dd_pct": dd * 100,
        "buyhold_pct": bh * 100,
    }


def main():
    print(f"\nCPR daily backtest   {START.date()} -> {END.date()}   "
          f"cost {COST*1e4:.0f}bps   narrow-only={NARROW_ONLY}\n")
    hdr = (f"{'symbol':<7}{'trades':>8}{'win%':>8}{'totRet%':>10}{'PF':>7}"
           f"{'avgW%':>8}{'avgL%':>8}{'maxDD%':>9}{'B&H%':>9}")
    print(hdr)
    print("-" * len(hdr))
    for s in SYMBOLS:
        df = fetch(s)
        if df is None or len(df) < 40:
            print(f"{s:<7} no / insufficient data")
            continue
        st = stats(cpr_backtest(df))
        if not st:
            print(f"{s:<7} no trades")
            continue
        print(f"{s:<7}{st['trades']:>8}{st['win_rate']:>8.1f}{st['total_return_pct']:>10.2f}"
              f"{st['profit_factor']:>7.2f}{st['avg_win_pct']:>8.2f}{st['avg_loss_pct']:>8.2f}"
              f"{st['max_dd_pct']:>9.2f}{st['buyhold_pct']:>9.2f}")
    print("\nRule: open above CPR -> long, open below CPR -> short, inside -> skip; "
          "entry at open, exit at close (intraday).")


if __name__ == "__main__":
    main()

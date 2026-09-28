"""Live paper CPR bot on Alpaca — places intraday CPR trades and shows live P&L.

For each symbol:
    CPR from YESTERDAY's daily bar:
        pivot=(H+L+C)/3   bc=(H+L)/2   tc=2*pivot-bc
        top=max(tc,bc)    bottom=min(tc,bc)
    Today's OPEN above CPR top     -> LONG
    Today's OPEN below CPR bottom  -> SHORT
    Today's OPEN inside the CPR    -> no trade

Each position is ~NOTIONAL per symbol, held intraday; close with --close.

Flags:
    --check     account connectivity + buying power (no orders)
    --signal    show today's CPR signal for each symbol (no orders)
    --run       place the CPR trades   (DRY-RUN unless --execute is added)
    --execute   actually submit the orders
    --pnl       show open positions + live unrealised P&L
    --close     close all open positions (also needs --execute)
"""
import argparse
import json

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

KEYS_PATH = r"C:\Users\SHALVA\apolloprojects\quanttrading\cpr_keys.json"
SYMBOLS = ["SPY", "QQQ", "AAPL"]
NOTIONAL = 5000        # ~$ per position


def _clients():
    k = json.load(open(KEYS_PATH))
    trade = TradingClient(k["api_key"], k["api_secret"], paper=True)
    data = StockHistoricalDataClient(k["api_key"], k["api_secret"])
    return trade, data


def _cpr_signal(data, symbol):
    """Return (side, price, levels) using yesterday's CPR vs today's open."""
    import datetime as dt
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                           start=dt.datetime.now() - dt.timedelta(days=12),
                           feed=DataFeed.IEX)
    df = data.get_stock_bars(req).df
    if df is None or len(df) < 2:
        return None, None, None
    df = df.xs(symbol, level=0) if df.index.nlevels > 1 else df
    prev, today = df.iloc[-2], df.iloc[-1]
    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3
    bc = (prev["high"] + prev["low"]) / 2
    tc = 2 * pivot - bc
    top, bot = max(tc, bc), min(tc, bc)
    o = today["open"]
    # latest price for sizing / display
    snap = data.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=symbol))
    price = float(snap[symbol].latest_trade.price) if snap.get(symbol) and snap[symbol].latest_trade else float(today["close"])
    side = "LONG" if o > top else "SHORT" if o < bot else "FLAT"
    return side, price, {"pivot": pivot, "top": top, "bottom": bot, "open": o}


def check():
    trade, _ = _clients()
    a = trade.get_account()
    print(f"Connected. account={a.account_number}  equity=${float(a.equity):,.2f}  "
          f"buying_power=${float(a.buying_power):,.2f}  status={a.status}")


def signal():
    _, data = _clients()
    print("Today's CPR signal:")
    for s in SYMBOLS:
        side, price, lv = _cpr_signal(data, s)
        if side is None:
            print(f"  {s:5} no data"); continue
        print(f"  {s:5} open={lv['open']:.2f}  CPR[{lv['bottom']:.2f}..{lv['top']:.2f}]  "
              f"price={price:.2f}  -> {side}")


def run(execute):
    trade, data = _clients()
    print(f"{'EXECUTE' if execute else 'DRY-RUN'} — placing CPR trades (~${NOTIONAL}/symbol):")
    for s in SYMBOLS:
        side, price, lv = _cpr_signal(data, s)
        if side in (None, "FLAT"):
            print(f"  {s:5} {side or 'no data'} — no trade"); continue
        qty = max(1, int(NOTIONAL / price))
        order_side = OrderSide.BUY if side == "LONG" else OrderSide.SELL
        print(f"  {s:5} {side}  {qty} sh @ ~{price:.2f}", end="")
        if not execute:
            print("   (dry-run)"); continue
        try:
            trade.submit_order(MarketOrderRequest(symbol=s, qty=qty, side=order_side,
                                                  time_in_force=TimeInForce.DAY))
            print("   ORDER SENT")
        except Exception as e:
            print(f"   NOT PLACED: {e}")


def pnl():
    trade, _ = _clients()
    positions = trade.get_all_positions()
    if not positions:
        print("No open positions."); return
    print(f"{'symbol':<7}{'qty':>7}{'avg_entry':>11}{'price':>10}{'mkt_val':>12}{'unreal_P&L':>13}{'P&L%':>9}")
    print("-" * 69)
    total = 0.0
    for p in positions:
        pl = float(p.unrealized_pl); total += pl
        print(f"{p.symbol:<7}{p.qty:>7}{float(p.avg_entry_price):>11.2f}{float(p.current_price):>10.2f}"
              f"{float(p.market_value):>12.2f}{pl:>13.2f}{float(p.unrealized_plpc)*100:>8.2f}%")
    print("-" * 69)
    print(f"{'TOTAL unrealised P&L':<47}{total:>13.2f}")


def close(execute):
    trade, _ = _clients()
    positions = trade.get_all_positions()
    if not positions:
        print("No positions to close."); return
    for p in positions:
        print(f"  closing {p.symbol} ({p.qty})", end="")
        if not execute:
            print("   (dry-run)"); continue
        try:
            trade.close_position(p.symbol); print("   CLOSED")
        except Exception as e:
            print(f"   FAILED: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--signal", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--pnl", action="store_true")
    ap.add_argument("--close", action="store_true")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    if args.check: check()
    elif args.signal: signal()
    elif args.run: run(args.execute)
    elif args.pnl: pnl()
    elif args.close: close(args.execute)
    else:
        print("Pick one: --check | --signal | --run [--execute] | --pnl | --close [--execute]")


if __name__ == "__main__":
    main()

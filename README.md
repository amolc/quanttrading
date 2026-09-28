# CPR Strategy (Central Pivot Range) — Alpaca

A Central Pivot Range (CPR) strategy with two parts:
- **`cpr_strategy.py`** — backtests CPR on real Alpaca historical data
- **`cpr_live.py`** — runs CPR live on an Alpaca **paper** account and shows real-time P&L

> This repo also contains `strategyforapollo/` (a separate options VRP strategy). This README covers the CPR strategy.

---

## What CPR is

The Central Pivot Range is three price levels drawn from the **previous day's** High, Low and Close. Think of it as yesterday's "fair-value zone" projected onto today:

```
pivot  = (High + Low + Close) / 3
bc     = (High + Low) / 2
tc     = 2 * pivot - bc
top    = max(tc, bc)      # top of the range
bottom = min(tc, bc)      # bottom of the range
```

- Price **above** the range → bullish lean
- Price **below** the range → bearish lean
- A **narrow** range → a trending day; a **wide** range → a choppy/rangebound day

## The trading rule (no look-ahead)

CPR is built from **yesterday's** bar; the direction is decided at **today's open** (which is already known), so there is no peeking into the future:

| Today's open vs CPR | Action |
|---------------------|--------|
| Opens **above** the top | **Long** — buy at open, exit at close |
| Opens **below** the bottom | **Short** — sell at open, cover at close |
| Opens **inside** the range | No trade (rangebound) |

Each trade is intraday (open → close).

---

## 1. Backtest — `cpr_strategy.py`

Pulls real historical daily bars from Alpaca (free IEX feed — no options data needed), applies the rule above, and reports the results per symbol.

Run:
```powershell
$py = "C:\Users\SHALVA\apolloprojects\algoengine\venv\Scripts\python.exe"
& $py cpr_strategy.py
```

Output columns: trades, win %, total return, profit factor, average win/loss, max drawdown, and buy-&-hold for comparison.

### Honest results (SPY / QQQ / AAPL, 2022–2026)

| Symbol | Total Return | Profit Factor | Buy & Hold |
|--------|-------------:|--------------:|-----------:|
| SPY | −35.9% | 0.88 | +61.0% |
| QQQ | −22.2% | 0.96 | +79.6% |
| AAPL | −32.6% | 0.95 | +78.3% |

**The basic daily CPR rule loses money** and underperforms simply holding. Reason: CPR is really an **intraday** strategy — a daily open→close version is too crude (it trades almost every day and captures none of the intraday structure). To make it realistic it needs **minute bars** and proper stops/targets. The backtest is honest about this rather than curve-fitting a win.

---

## 2. Live paper bot — `cpr_live.py`

Runs the same CPR logic against an Alpaca **paper** account, places real paper orders, and reports live P&L. Useful for demonstrating the end-to-end pipeline.

```powershell
$py = "C:\Users\SHALVA\apolloprojects\algoengine\venv\Scripts\python.exe"

& $py cpr_live.py --check              # account connectivity + buying power
& $py cpr_live.py --signal             # today's CPR signal per symbol (no orders)
& $py cpr_live.py --run --execute      # place the CPR trades (US market hours only)
& $py cpr_live.py --pnl                # open positions + live unrealised P&L
& $py cpr_live.py --close --execute    # close all positions
```

- Without `--execute`, `--run` is a **dry run** (prints what it would do, places nothing).
- Orders only fill while the **US market is open** (~7:00 PM–1:30 AM IST).
- Sizing is ~$5,000 per symbol (`NOTIONAL` in the file); symbols are set in `SYMBOLS`.

---

## Setup

1. **Python deps** (numpy, pandas, alpaca-py):
   ```powershell
   pip install alpaca-py pandas numpy
   ```
2. **Alpaca keys** — create a `cpr_keys.json` in this folder (it is **gitignored**, never committed):
   ```json
   {
     "api_key": "YOUR_ALPACA_PAPER_KEY_ID",
     "api_secret": "YOUR_ALPACA_PAPER_SECRET",
     "paper": true
   }
   ```
   Get paper keys from the Alpaca dashboard → your paper account → API Keys.

## Security

- **Never commit API keys.** `cpr_keys.json` is in `.gitignore` — each person creates their own locally.
- The bot uses **paper** trading only (`paper: true`) — no real money.

## Disclaimer

For research/education. The backtest shows this strategy is **not profitable** as-is. Not financial advice.

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Optional


def fetch_data(
    ticker: str,
    period: str = "6mo",
    interval: str = "1d",
) -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [col.lower() for col in df.columns]
    return df


def calculate_zscore(df: pd.DataFrame, window: int = 20) -> pd.Series:
    roll_mean = df["close"].rolling(window=window).mean()
    roll_std = df["close"].rolling(window=window).std()
    return (df["close"] - roll_mean) / roll_std


def calculate_bollinger_bands(
    df: pd.DataFrame, window: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    roll_mean = df["close"].rolling(window=window).mean()
    roll_std = df["close"].rolling(window=window).std()
    bands = pd.DataFrame(index=df.index)
    bands["middle"] = roll_mean
    bands["upper"] = roll_mean + num_std * roll_std
    bands["lower"] = roll_mean - num_std * roll_std
    return bands


def calculate_rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = pd.Series(np.nan, index=df.index, dtype=float)
    avg_loss = pd.Series(np.nan, index=df.index, dtype=float)
    avg_gain.iloc[window] = gain.iloc[1 : window + 1].mean()
    avg_loss.iloc[window] = loss.iloc[1 : window + 1].mean()
    for i in range(window + 1, len(df)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (window - 1) + gain.iloc[i]) / window
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (window - 1) + loss.iloc[i]) / window
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def generate_signals(
    df: pd.DataFrame,
    zscore_entry: float = 2.0,
    zscore_exit: float = 0.5,
    rsi_oversold: float = 30,
    rsi_overbought: float = 70,
) -> pd.DataFrame:
    result = df[["close"]].copy()
    result["zscore"] = calculate_zscore(df)
    result["rsi"] = calculate_rsi(df)
    result["position"] = 0
    in_position = False
    for i in range(1, len(result)):
        zs = result["zscore"].iloc[i]
        rsi_val = result["rsi"].iloc[i]
        if pd.isna(zs) or pd.isna(rsi_val):
            if in_position:
                result.loc[result.index[i], "position"] = result["position"].iloc[i - 1]
            continue
        if not in_position:
            if zs < -zscore_entry or rsi_val < rsi_oversold:
                result.loc[result.index[i], "position"] = 1
                in_position = True
            elif zs > zscore_entry or rsi_val > rsi_overbought:
                result.loc[result.index[i], "position"] = -1
                in_position = True
        else:
            prev_pos = result["position"].iloc[i - 1]
            if prev_pos == 1 and zs >= -zscore_exit and rsi_val > rsi_oversold:
                result.loc[result.index[i], "position"] = 0
                in_position = False
            elif prev_pos == -1 and zs <= zscore_exit and rsi_val < rsi_overbought:
                result.loc[result.index[i], "position"] = 0
                in_position = False
            else:
                result.loc[result.index[i], "position"] = prev_pos
    return result


def backtest(
    signals: pd.DataFrame,
    initial_capital: float = 10000.0,
    commission: float = 0.001,
) -> pd.DataFrame:
    result = signals.copy()
    result["returns"] = result["close"].pct_change()
    result["strategy_returns"] = result["position"].shift(1) * result["returns"]
    result["strategy_returns"] -= commission * result["position"].diff().abs()
    result["strategy_returns"] = result["strategy_returns"].fillna(0)
    result["equity"] = initial_capital * (1 + result["strategy_returns"]).cumprod()
    result["buy_hold"] = initial_capital * (1 + result["returns"].fillna(0)).cumprod()
    return result


def plot_results(backtest_result: pd.DataFrame, ticker: str) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    ax1, ax2, ax3 = axes
    ax1.plot(backtest_result.index, backtest_result["close"], label="Close", color="blue", alpha=0.6)
    buy_signals = backtest_result[backtest_result["position"] == 1]
    sell_signals = backtest_result[backtest_result["position"] == -1]
    ax1.scatter(buy_signals.index, buy_signals["close"], marker="^", color="green", s=100, label="Buy Signal")
    ax1.scatter(sell_signals.index, sell_signals["close"], marker="v", color="red", s=100, label="Sell Signal")
    ax1.set_title(f"{ticker} - Price & Signals")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax2.plot(backtest_result.index, backtest_result["zscore"], label="Z-Score", color="purple")
    ax2.axhline(2, color="red", linestyle="--", alpha=0.5)
    ax2.axhline(-2, color="green", linestyle="--", alpha=0.5)
    ax2.axhline(0, color="gray", linestyle="-", alpha=0.3)
    ax2.set_title("Z-Score")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax3.plot(backtest_result.index, backtest_result["equity"], label="Strategy", color="green", linewidth=2)
    ax3.plot(backtest_result.index, backtest_result["buy_hold"], label="Buy & Hold", color="gray", linestyle="--")
    ax3.set_title("Equity Curve")
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def run_strategy(
    ticker: str = "SPY",
    period: str = "1y",
    interval: str = "1d",
    zscore_entry: float = 2.0,
    zscore_exit: float = 0.5,
    initial_capital: float = 10000.0,
) -> Optional[pd.DataFrame]:
    print(f"Fetching {ticker} data ({period}, {interval})...")
    df = fetch_data(ticker, period, interval)
    if df.empty:
        print("No data fetched.")
        return None
    print(f"Loaded {len(df)} rows from {df.index[0].date()} to {df.index[-1].date()}")
    signals = generate_signals(df, zscore_entry, zscore_exit)
    result = backtest(signals, initial_capital)
    total_return = (result["equity"].iloc[-1] / initial_capital - 1) * 100
    bh_return = (result["buy_hold"].iloc[-1] / initial_capital - 1) * 100
    num_trades = int(result["position"].diff().abs().sum())
    print(f"Strategy Return: {total_return:.2f}%")
    print(f"Buy & Hold Return: {bh_return:.2f}%")
    print(f"Number of Trades: {num_trades}")
    plot_results(result, ticker)
    return result


if __name__ == "__main__":
    run_strategy("SPY", period="1y")

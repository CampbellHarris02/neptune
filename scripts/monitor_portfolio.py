from pathlib import Path
from ta.momentum import RSIIndicator, ROCIndicator # type: ignore
from ta.trend    import MACD # type: ignore
import numpy as np
import pandas as pd
import ccxt, os, time, logging # type: ignore
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv        # type: ignore

from scripts.utilities import save_json, load_json, get_price, get_quantity

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

# ─────────────────────────────── Config ──────────────────────────────────────
load_dotenv()

PENDING_FILE   = "data/pending_orders.json"
POSITION_FILE  = "data/positions.json"
PORTFOLIO_FILE = "data/portfolio.json"

LOG_FILE       = "log.txt"
SLEEP_SECONDS  = 30          # loop delay
BOUNDARY       = 0.08        # 8 % trailing stop
HARD_SL_PCT    = 0.08     # 8 %
TRIGGER_PROFIT = 0.02     # +2 %
TIMEFRAME      = "1h"     # momentum timeframe
KRAKEN         = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_API_KEY"),
    'secret': os.getenv("KRAKEN_API_SECRET"),
    'enableRateLimit': True,
})
# assume helpers load_json / save_json / get_price already exist
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Momentum helper
# ------------------------------------------------------------
def momentum_score(df: pd.DataFrame) -> float:
    """Return scalar in [-1,1] for the last row of df (expects open/high/low/close)."""
    if len(df) < 30:
        return 0.0
    close = df["close"]
    rsi  = RSIIndicator(close, 14).rsi().iloc[-1]
    macd = MACD(close)
    macd_diff = (macd.macd() - macd.macd_signal()).iloc[-1]
    roc  = ROCIndicator(close, 5).roc().iloc[-1]
    sma  = close.rolling(20).mean().iloc[-1]

    rsi_s  = (rsi - 50) / 50
    macd_s = np.tanh(macd_diff / close.std())
    roc_s  = np.tanh(roc / 10)
    sma_s  = np.tanh(((close.iloc[-1] / sma) - 1) * 10)

    return float(np.clip((rsi_s + macd_s + roc_s + sma_s) / 4, -1, 1))

# ------------------------------------------------------------
#  monitor
# ------------------------------------------------------------
HARD_SL_PCT     = 0.08   # 8% max loss
TRIGGER_PROFIT  = 0.04   # 4% to activate trailing
TRAIL_SL_PCT    = 0.03   # 3% trail below peak
MOM_THRESHOLD   = -0.2   # optional exit on momentum
TIMEFRAME       = "30m"   # example timeframe
MOM_WINDOW      = 60     # number of candles to use

def monitor_portfolio() -> None:
    positions = load_json(POSITION_FILE)
    portfolio = load_json(PORTFOLIO_FILE)
    new_pos   = {}

    for symbol, data in positions.items():
        current_price = get_price(symbol)
        if current_price is None:
            new_pos[symbol] = data
            continue

        entry_px   = data["entry_price"]
        stop_price = data.get("stop_price", entry_px * (1 - HARD_SL_PCT))
        peak_price = data.get("peak_price", entry_px)

        # Update peak price if new high
        if current_price > peak_price:
            peak_price = current_price

        # If profit has exceeded trigger threshold, activate trailing SL
        if current_price >= entry_px * (1 + TRIGGER_PROFIT):
            trailing_sl = peak_price * (1 - TRAIL_SL_PCT)
            stop_price = max(stop_price, trailing_sl)

        # Check hard SL (applies always)
        if current_price <= stop_price:
            sell_and_log(symbol, current_price, data, portfolio,
                         reason=f"SL hit: price={current_price:.4f}, stop={stop_price:.4f}, peak={peak_price:.4f}")
            continue

        # ───────────────────────────────
        # Step 2: Momentum-based exit
        # ───────────────────────────────
        score = None
        try:
            ohlcv = KRAKEN.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=MOM_WINDOW)
            mom_df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "vol"])
            mom_df["close"] = mom_df["close"].astype(float)
            score = momentum_score(mom_df[["open", "high", "low", "close"]])
            logger.info("Momentum score for %s: %.2f", symbol, score)
        except Exception as e:
            logger.warning("Momentum fetch error for %s: %s", symbol, e)

        if score is not None and score < MOM_THRESHOLD:
            sell_and_log(symbol, current_price, data, portfolio,
                         reason=f"Bearish momentum (score {score:.2f})")
            continue

        # Update tracking
        data["stop_price"] = stop_price
        data["peak_price"] = peak_price
        new_pos[symbol] = data

        # Save monitoring info
        sym_id = symbol.replace("/", "_").lower()
        mon_path = os.path.join("data", "historical", sym_id, "monitor.json")
        os.makedirs(os.path.dirname(mon_path), exist_ok=True)

        monitor_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": current_price,
            "momentum_score": score,
            "stop_loss": stop_price,
            "peak_price": peak_price
        }

        save_json(monitor_data, mon_path)

    save_json(new_pos, POSITION_FILE)
    save_json(portfolio, PORTFOLIO_FILE)



# ------------------------------------------------------------
#  Helper to execute sells & bookkeeping
# ------------------------------------------------------------
def sell_and_log(symbol: str, price: float, data: dict,
                 portfolio: dict, reason: str):
    """Attempt to liquidate and update portfolio; silent retry left to caller."""
    logger.warning("Exit %s @ %.4f ‒ %s", symbol, price, reason)
    try:
        KRAKEN.create_market_sell_order(symbol, data["qty"])
        usd = price * data["qty"]
        portfolio["USD"] = portfolio.get("USD", 0) + usd
        logger.info("Sold %.4f %s for ≈ %.2f USD", data["qty"], symbol, usd)
    except Exception as e:
        logger.error("Sell error for %s: %s", symbol, e)
        # if sell fails we keep position unchanged for next loop
        positions = load_json(POSITION_FILE)
        positions[symbol] = data
        save_json(positions, POSITION_FILE)


if __name__ == "__main__":
    import time
    from rich.console import Console # type: ignore

    console = Console()
    console.log("[cyan]Starting position monitor loop…")

    while True:
        try:
            monitor_portfolio()
            console.log(f"[green]monitor_positions ran successfully at {datetime.now().isoformat()}")
        except Exception as e:
            logger.error("Error in monitor_positions(): %s", e, exc_info=True)
        time.sleep(SLEEP_SECONDS)

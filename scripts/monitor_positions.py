from pathlib import Path
from ta.momentum import RSIIndicator, ROCIndicator
from ta.trend    import MACD
import numpy as np
import pandas as pd
import ccxt, os, time, logging
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
MOM_WINDOW     = 60       # candles for momentum look-back
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
#  Main monitor
# ------------------------------------------------------------
def monitor_positions() -> None:
    positions = load_json(POSITION_FILE)
    portfolio = load_json(PORTFOLIO_FILE)
    new_pos   = {}

    for symbol, data in positions.items():
        current_price = get_price(symbol)
        if current_price is None:
            new_pos[symbol] = data          # keep unchanged – price fetch failed
            continue

        entry_px   = data["entry_price"]
        triggered  = data.get("triggered", False)
        stop_price = data["stop_price"]

        # --------------------------------------------------------------------
        # 1) BEFORE trigger  (+2% not yet reached)
        # --------------------------------------------------------------------
        if not triggered:
            # raise stop once +2 % reached
            if current_price >= entry_px * (1 + TRIGGER_PROFIT):
                stop_price          = entry_px * (1 + TRIGGER_PROFIT)
                data["stop_price"]  = stop_price
                data["triggered"]   = True
                logger.info("%s trigger fired → SL raised to %.4f", symbol, stop_price)
                triggered = True     # continue to momentum logic

            # hard stop 8 % below entry
            elif current_price <= entry_px * (1 - HARD_SL_PCT):
                sell_and_log(symbol, current_price, data, portfolio,
                             reason="Hard SL 8 % below entry")
                continue

        # --------------------------------------------------------------------
        # 2) AFTER trigger – momentum-based stop
        # --------------------------------------------------------------------
        if triggered:
            # momentum check
            ohlcv = KRAKEN.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=MOM_WINDOW)
            mom_df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"])
            mom_df["close"] = mom_df["close"].astype(float)
            score = momentum_score(mom_df[["open","high","low","close"]])

            if score < 0:
                sell_and_log(symbol, current_price, data, portfolio,
                             reason=f"Momentum down (score {score:.2f})")
                continue

            # fallback hard stop at fixed stop_price
            if current_price <= stop_price:
                sell_and_log(symbol, current_price, data, portfolio,
                             reason="Fixed +2 % stop hit")
                continue

        # position still open – write back any updated fields
        data["stop_price"] = stop_price
        new_pos[symbol] = data

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

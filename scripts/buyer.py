"""
buyer.py  -  Scans ranked_coins.json and places limit-buy orders
---------------------------------------------------------------
• Full event history (INFO+) is written to log.txt
• Terminal shows only a start / end notice through Rich
"""

from __future__ import annotations

import os, logging
from datetime import datetime
from typing import Dict, Any

import ccxt                           # type: ignore
from dotenv import load_dotenv        # type: ignore
from rich.console import Console      # type: ignore
from rich.logging import RichHandler  # type: ignore

from scripts.utilities import load_json, save_json

# ───────────────────────────── Config ────────────────────────────────────────
load_dotenv()

LOG_FILE              = "log.txt"
MIN_SCORE_THRESHOLD   = 0.7
BUY_PORTFOLIO_PERCENT = 0.10   # allocate at most 10 % of total portfolio

# ───────────────────────────── Logging setup ────────────────────────────────
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        RichHandler(console=console, markup=True, rich_tracebacks=True, level=logging.WARNING),
    ],
)
logger = logging.getLogger(__name__)

# ───────────────────────────── Kraken connection ────────────────────────────
kraken = ccxt.kraken({
    "apiKey":  os.getenv("KRAKEN_API_KEY"),
    "secret":  os.getenv("KRAKEN_API_SECRET"),
    "enableRateLimit": True,
})

# ───────────────────────────── Core function ────────────────────────────────
def buyer() -> None:
    """Read ranked_coins.json and place new limit-buy orders if conditions meet."""
    console.log("[cyan]Buyer started")

    portfolio: Dict[str, float]  = load_json("data/portfolio.json")
    ranked_coins: Dict[str, Any] = load_json("data/ranked_coins.json")
    pending_orders: Dict[str, Any] = load_json("data/pending_orders.json")
    positions: Dict[str, Any]      = load_json("data/positions.json")   # ← NEW

    total_value    = sum(portfolio.values())
    available_usd  = portfolio.get("USD", 0.0)
    max_alloc      = total_value * BUY_PORTFOLIO_PERCENT

    logger.info("Portfolio %.2f USD (cash %.2f USD) - max allocation per coin %.2f USD",
                total_value, available_usd, max_alloc)

    # iterate coins ordered by score descending
    for symbol, data in sorted(ranked_coins.items(),
                               key=lambda x: x[1].get("score", 0),
                               reverse=True):

        score = data.get("score", 0.0)
        price = data.get("price", 0.0)

        if score < MIN_SCORE_THRESHOLD:
            continue
        if symbol in positions:             # ← NEW check
            logger.info("Skip %s - position already open", symbol)
            continue
        if symbol in pending_orders:
            logger.info("Skip %s - order already pending", symbol)
            continue
        if price <= 0:
            logger.warning("Skip %s - invalid price %.6f", symbol, price)
            continue
        if available_usd < max_alloc:
            logger.info("Skip %s - insufficient USD (%.2f left)", symbol, available_usd)
            break

        amount = round(max_alloc / price, 6)
        logger.info("Placing limit buy: %s %.6f @ %.5f USD", symbol, amount, price)

        try:
            order = kraken.create_limit_buy_order(symbol, amount, price)
            if isinstance(order, dict):
                order_id = order.get("id") or order.get("orderId")
            elif isinstance(order, list) and len(order) > 0:
                # Maybe Kraken returned [ order_id, … ]?
                order_id = order[0]
            else:
                raise ValueError(f"Unexpected order format: {order}")

            logger.info("Order placed - id %s", order_id)

            pending_orders[symbol] = {
                "order_id":  order_id,
                "symbol":    symbol,
                "price":     price,
                "timestamp": datetime.utcnow().isoformat(),
            }
            available_usd -= max_alloc

        except Exception as exc:
            logger.error("Error placing order for %s: %s", symbol, exc)

    save_json(pending_orders, "data/pending_orders.json")
    console.log("[green]Buyer finished")


# Manual run
if __name__ == "__main__":
    try:
        buyer()
    except KeyboardInterrupt:
        console.log("[red]User interrupt - exiting buyer")
        logger.info("buyer.py terminated by user")

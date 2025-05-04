"""
Stop-loss & pending-order monitor (rich-enabled)
-----------------------------------------------
• All detailed events are written to log.txt via the root logger.
• The terminal shows minimal rich output (status spinner + one-line updates).
"""

from __future__ import annotations

import os
import time
import json
import logging
from datetime import datetime
from typing import Dict, Any

import ccxt                           # type: ignore
from dotenv import load_dotenv        # type: ignore
from rich.console import Console        # type: ignore
from rich.logging import RichHandler    # type: ignore

# ─────────────────────────────── Config ──────────────────────────────────────
load_dotenv()

PENDING_FILE   = "data/pending_orders.json"
POSITION_FILE  = "data/positions.json"
PORTFOLIO_FILE = "data/portfolio.json"
LOG_FILE       = "log.txt"
SLEEP_SECONDS  = 30          # loop delay
BOUNDARY       = 0.08        # 8 % trailing stop

# ─────────────────────────────── Logging ─────────────────────────────────────
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        # Only warnings/errors go to the terminal to keep it quiet
        RichHandler(console=console, markup=True, rich_tracebacks=True, level=logging.WARNING),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────── Helpers ─────────────────────────────────────
def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ───────────────────────────── Kraken setup ──────────────────────────────────
kraken = ccxt.kraken({
    "apiKey":  os.getenv("KRAKEN_API_KEY"),
    "secret":  os.getenv("KRAKEN_API_SECRET"),
    "enableRateLimit": True,
})

# ───────────────────────────── API wrappers ──────────────────────────────────
def fetch_order_status(order_id: str):
    try:
        return kraken.fetch_order(order_id)
    except Exception as e:
        logger.warning("Could not fetch order %s: %s", order_id, e)
        return None

def get_price(symbol: str):
    try:
        return kraken.fetch_ticker(symbol)["last"]
    except Exception as e:
        logger.warning("Failed to fetch price for %s: %s", symbol, e)
        return None

def get_quantity(symbol: str):
    base = symbol.split("/")[0]
    balances = kraken.fetch_balance()
    return balances["free"].get(base, 0)

# ───────────────────────────── Core functions ────────────────────────────────
def check_pending_orders() -> None:
    pending   = load_json(PENDING_FILE)
    positions = load_json(POSITION_FILE)
    updated   = []

    for order_data in pending:
        symbol   = order_data["symbol"]
        order_id = order_data["order_id"]
        logger.info("Checking pending order %s → %s", symbol, order_id)
        order = fetch_order_status(order_id)

        if not order:
            updated.append(order_data)       # keep, try again later
            continue

        if order["status"] == "closed":
            filled_price = float(order["average"] or order_data["price"])
            qty          = order["filled"]
            stop_price   = filled_price * (1 - BOUNDARY)

            logger.info(
                "%s filled at %.4f; trailing‑stop initialised at %.4f",
                symbol, filled_price, stop_price
            )
            positions[symbol] = {
                "entry_price":   filled_price,
                "trailing_high": filled_price,
                "stop_price":    stop_price,
                "qty":           qty,
                "filled_at":     datetime.utcnow().isoformat(),
            }
        else:
            updated.append(order_data)

    save_json(positions, POSITION_FILE)
    save_json(updated,   PENDING_FILE)

def monitor_positions() -> None:
    positions  = load_json(POSITION_FILE)
    portfolio  = load_json(PORTFOLIO_FILE)
    new_pos    = {}

    for symbol, data in positions.items():
        current_price = get_price(symbol)
        if current_price is None:             # price failure → keep unchanged
            new_pos[symbol] = data
            continue

        trailing_high  = max(data["trailing_high"], current_price)
        new_stop_price = trailing_high * (1 - BOUNDARY)

        # update trailing stop
        data["trailing_high"] = trailing_high
        data["stop_price"]    = new_stop_price

        if current_price < new_stop_price:    # stop‑loss condition
            logger.warning(
                "Stop-loss triggered for %s: price %.4f < stop %.4f",
                symbol, current_price, new_stop_price
            )
            try:
                kraken.create_market_sell_order(symbol, data["qty"])
                usd_received           = current_price * data["qty"]
                portfolio["USD"]       = portfolio.get("USD", 0) + usd_received
                logger.info(
                    "Sold %.4f %s for approximately %.2f USD",
                    data["qty"], symbol, usd_received
                )
            except Exception as e:
                logger.error("Error selling %s: %s", symbol, e)
                new_pos[symbol] = data      # keep for retry
        else:
            new_pos[symbol] = data          # position still healthy

    save_json(new_pos,  POSITION_FILE)
    save_json(portfolio, PORTFOLIO_FILE)

# ───────────────────────────── Main loop ─────────────────────────────────────
def main() -> None:
    console.rule("[bold cyan]Stop-loss monitor started")

    with console.status("[bold cyan]Running", spinner="dots"):
        while True:
            console.log("[yellow]Checking pending orders")
            check_pending_orders()

            console.log("[green]Monitoring filled positions for stop-loss")
            monitor_positions()

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.log("[red]User interrupt - shutting down…")
        logger.info("Stop-loss monitor terminated by user")

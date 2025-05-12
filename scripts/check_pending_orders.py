"""
pending-order monitor
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
from datetime import datetime, timedelta, timezone

import ccxt                           # type: ignore
from dotenv import load_dotenv        # type: ignore
from rich.console import Console        # type: ignore
from rich.logging import RichHandler    # type: ignore

from scripts.utilities import save_json, load_json, get_price, get_quantity, fetch_order_status

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


# ───────────────────────────── Kraken setup ──────────────────────────────────
kraken = ccxt.kraken({
    "apiKey":  os.getenv("KRAKEN_API_KEY"),
    "secret":  os.getenv("KRAKEN_API_SECRET"),
    "enableRateLimit": True,
})





MAX_PENDING_AGE = timedelta(hours=3)

# ───────────────────────────── Core functions ────────────────────────────────
def check_pending_orders() -> None:
    pending   = load_json(PENDING_FILE)          # list[dict]
    positions = load_json(POSITION_FILE)         # dict
    updated   = []                               # new pending list

    now = datetime.now(timezone.utc)

    for order_data in pending:
        symbol      = order_data["symbol"]
        order_id    = order_data["order_id"]
        placed_iso = order_data.get("placed_at")
        if placed_iso:
            placed_time = datetime.fromisoformat(placed_iso)
            if placed_time.tzinfo is None:
                placed_time = placed_time.replace(tzinfo=timezone.utc)
        else:
            placed_time = now


        logger.info("Checking pending order %s → %s", symbol, order_id)
        order = fetch_order_status(order_id)

        # ── Could not fetch — keep for retry ────────────────────────────────
        if not order:
            updated.append(order_data)
            continue

        status = order["status"]

        # ── Filled ─────────────────────────────────────────────────────────
        if status == "closed":
            filled_price = float(order["average"] or order_data["price"])
            qty          = order["filled"]
            stop_price   = filled_price * (1 - BOUNDARY)

            logger.info(
                "%s filled at %.4f; trailing-stop initialised at %.4f",
                symbol, filled_price, stop_price
            )
            positions[symbol] = {
                "entry_price":   filled_price,
                "trailing_high": filled_price,
                "stop_price":    stop_price,
                "qty":           qty,
                "filled_at":     datetime.utcnow().isoformat(),
                "triggered":     False           # for new SL logic
            }
            continue

        # ── Still open … has it exceeded the 3-hour window? ────────────────
        age = now - placed_time
        if age > MAX_PENDING_AGE:
            try:
                kraken.cancel_order(order_id, symbol)
                logger.warning(
                    "⏱️  Pending order %s (%s) cancelled after %.1f h",
                    order_id, symbol, age.total_seconds() / 3600
                )
            except Exception as e:
                logger.error("Cancel error %s → %s", order_id, e)
                # keep for next loop if cancel fails
                updated.append(order_data)
        else:
            updated.append(order_data)

    # ─── Persist state ──────────────────────────────────────────────────────
    save_json(positions, POSITION_FILE)
    save_json(updated,   PENDING_FILE)

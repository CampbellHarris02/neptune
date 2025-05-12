"""
Neptune trading‑bot maintenance script
-------------------------------------
• Keeps local JSON books (portfolio, positions, pending orders) in sync with Kraken.
• Survives API hiccups by retrying and, if necessary, skipping balance/position refresh for
  the current cycle.
• All runtime messages are written to *log.txt* instead of stdout.
"""

from __future__ import annotations

import json
import os
import time
import logging
from typing import Optional, Dict, Any

import ccxt  # type: ignore
from dotenv import load_dotenv  # type: ignore
from datetime import datetime

from scripts.historical import historical, update_events
from scripts.utilities import update_log_status


# ---------------------------------------------------------------------------
# 0.  Logging
# ---------------------------------------------------------------------------
LOG_FILE = "log.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# 1.  Environment & File paths
# ---------------------------------------------------------------------------
load_dotenv()

PORTFOLIO_FILE = "data/portfolio.json"
POSITIONS_FILE = "data/positions.json"
PENDING_FILE = "data/pending_orders.json"

# ---------------------------------------------------------------------------
# 2.  Kraken client (with legacy balance endpoint fallback)
# ---------------------------------------------------------------------------
kraken = ccxt.kraken({
    "apiKey": os.getenv("KRAKEN_API_KEY"),
    "secret": os.getenv("KRAKEN_API_SECRET"),
    "enableRateLimit": True,
    # Use the stable /0/private/Balance endpoint rather than BalanceEx
    "options": {"fetchBalanceMethod": "privatePostBalance"},
    # Increase time‑out for slow responses (ms)
    "timeout": 20_000,
})

# ---------------------------------------------------------------------------
# 3.  JSON helpers
# ---------------------------------------------------------------------------

def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------------------------------------------------------------------
# 4.  Resilient Kraken wrappers
# ---------------------------------------------------------------------------

def _retry_delay(attempt: int, base: float = 1.0) -> float:
    """Exponential back‑off (1,2,4 … seconds)"""
    return base * (2 ** (attempt - 1))


def safe_fetch_balances(max_attempts: int = 3) -> Optional[Dict[str, Any]]:
    for attempt in range(1, max_attempts + 1):
        try:
            return kraken.fetch_balance()
        except Exception as exc:
            logging.warning("fetch_balance attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(_retry_delay(attempt))
    logging.error("All fetch_balance attempts failed – keeping previous snapshot.")
    return None


def fetch_current_price(symbol: str) -> Optional[float]:
    try:
        return kraken.fetch_ticker(symbol)["last"]
    except Exception as exc:
        logging.warning("Failed to fetch price for %s: %s", symbol, exc)
        return None

# ---------------------------------------------------------------------------
# 5.  Update routines
# ---------------------------------------------------------------------------

def update_portfolio() -> None:
    balances = safe_fetch_balances()
    if balances is None:
        return  # skip this cycle

    updated: Dict[str, Any] = {}
    usd_balance = balances["total"].get("USD", 0)
    updated["USD"] = round(usd_balance, 6)
    logging.info("USD cash balance: %.6f", usd_balance)

    for coin, amount in balances["total"].items():
        if coin == "USD" or amount == 0:
            continue
        symbol = f"{coin}/USD"
        price = fetch_current_price(symbol)
        if price is not None:
            usd_value = amount * price
            updated[symbol] = round(usd_value, 6)
            logging.info("%s: %.6f ≈ $%.2f", symbol, amount, usd_value)
        time.sleep(0.3)  # polite rate limit

    save_json(updated, PORTFOLIO_FILE)
    logging.info("portfolio.json updated (%d assets).", len(updated))


ALLOWED_FIELDS = {"entry_price", "qty", "filled_at"}   # nothing else!

def verify_positions() -> None:
    """
    • Remove any position whose on-chain balance is zero
    • Strip extraneous keys so each entry has only
      {'entry_price', 'qty', 'filled_at'}
    """
    balances = safe_fetch_balances()
    if balances is None:
        return                                          # skip cycle if API down

    positions = load_json(POSITIONS_FILE)
    updated: Dict[str, Any] = {}

    for symbol, entry in positions.items():
        coin = symbol.split("/")[0]

        # 1) keep only if wallet still holds that coin
        if balances["total"].get(coin, 0) == 0:
            logging.info("Removing stale position - no balance for %s", symbol)
            continue

        # 2) enforce schema
        clean_entry = {k: entry[k] for k in ALLOWED_FIELDS if k in entry}

        # warn if something was discarded
        extra_keys = set(entry) - ALLOWED_FIELDS
        if extra_keys:
            logging.warning("%s had extra fields %s - removed",
                            symbol, ", ".join(extra_keys))

        # 3) sanity-check required fields
        if ALLOWED_FIELDS.issubset(clean_entry):
            updated[symbol] = clean_entry
        else:
            logging.error("Position %s missing required keys - dropped", symbol)

    save_json(updated, POSITIONS_FILE)
    logging.info("positions.json verified (%d active).", len(updated))



def clean_pending_orders() -> None:
    pending = load_json(PENDING_FILE)
    if not pending:
        return

    updated: list[Dict[str, Any]] = []
    for order in pending:
        order_id = order.get("id")
        if not order_id:
            continue
        try:
            status = kraken.fetch_order(order_id)
            if status["status"] in ("open", "pending"):
                updated.append(order)
            else:
                logging.info("Order %s is %s - removing from pending list", order_id, status["status"])
        except Exception as exc:
            logging.warning("Could not fetch order %s: %s", order_id, exc)
        time.sleep(0.3)

    save_json(updated, PENDING_FILE)
    logging.info("pending_orders.json cleaned (%d remaining).", len(updated))

# ---------------------------------------------------------------------------
# 6.  Orchestration
# ---------------------------------------------------------------------------

def update_all(assets, status) -> None:
    update_log_status(status=status, message="Updating portfolio positions...")
    update_portfolio()
    update_log_status(status=status, message="Syncing local books with Kraken's portfolio positions...")
    verify_positions()
    update_log_status(status=status, message="Cleaning pending orders...")
    clean_pending_orders()
    update_log_status(status=status, message="Updating historical data...")
    historical(assets=assets, status=status)
    update_log_status(status=status, message="Updating historical events...")
    update_events(assets=assets, status=status)
    


if __name__ == "__main__":

    logging.info("────────── update cycle start ──────────")
    update_all()
    logging.info("────────── update cycle end ───────────\n")

import json
import os
import ccxt #type: ignore
from dotenv import load_dotenv        # type: ignore
from rich.console import Console        # type: ignore
from rich.logging import RichHandler    # type: ignore
import logging
from datetime import datetime

console = Console()

LOG_FILE       = "log.txt"

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

STATUS_FILE = "status.txt"
def update_log_status(status, message: str) -> None:
    """Replace the status line in the terminal and write status.txt."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full = f"[{ts}] {message}"

    # Update Rich status (overwrites the same line)
    status.update(f"[cyan]{message}")

    # Persist for the web-UI
    with open(STATUS_FILE, "w") as f:
        f.write(full + "\n")


# --- Utilities ---
from pathlib import Path

BASE = Path(__file__).parent.parent   # neptune/scripts → neptune/


def load_json(path):
    full = os.path.join(BASE, path)
    if os.path.exists(full):
        with open(full, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def save_json(obj, path):
    full = os.path.join(BASE, path)
    # ensure the directory exists
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        
        
kraken = ccxt.kraken({
    "apiKey":  os.getenv("KRAKEN_API_KEY"),
    "secret":  os.getenv("KRAKEN_API_SECRET"),
    "enableRateLimit": True,
})
        
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
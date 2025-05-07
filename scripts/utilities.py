import json
import os
import ccxt
from dotenv import load_dotenv        # type: ignore
from rich.console import Console        # type: ignore
from rich.logging import RichHandler    # type: ignore
import logging

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

# --- Utilities ---
def load_json(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_json(obj, path):
    with open(path, "w") as f:
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
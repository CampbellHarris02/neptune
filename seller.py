import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import ccxt

from utilities import load_json, save_json

# --- Config ---
load_dotenv()
PENDING_FILE = "data/pending_orders.json"
POSITION_FILE = "data/positions.json"
PORTFOLIO_FILE = "data/portfolio.json"
SLEEP_SECONDS = 30
BOUNDARY = 0.08  # 8% trailing stop

# --- Kraken Setup ---
kraken = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_API_KEY"),
    'secret': os.getenv("KRAKEN_API_SECRET"),
    'enableRateLimit': True,
})


def fetch_order_status(order_id):
    try:
        return kraken.fetch_order(order_id)
    except Exception as e:
        print(f"⚠️ Could not fetch order {order_id}: {e}")
        return None

def get_price(symbol):
    try:
        return kraken.fetch_ticker(symbol)['last']
    except:
        return None

def get_quantity(symbol):
    base = symbol.split("/")[0]
    balances = kraken.fetch_balance()
    return balances['free'].get(base, 0)

# --- Main Check ---
def check_pending_orders():
    pending = load_json(PENDING_FILE)
    positions = load_json(POSITION_FILE)
    updated = {}

    for symbol, order_data in pending.items():
        order_id = order_data["order_id"]
        print(f"🔍 Checking order: {symbol} → {order_id}")
        order = fetch_order_status(order_id)

        if not order:
            updated[symbol] = order_data
            continue

        if order["status"] == "closed":
            filled_price = float(order["average"]) if order["average"] else float(order_data["price"])
            qty = order["filled"]
            stop_price = filled_price * (1 - BOUNDARY)

            print(f"✅ {symbol} filled at {filled_price:.2f} — Trailing stop at {stop_price:.2f}")

            positions[symbol] = {
                "entry_price": filled_price,
                "trailing_high": filled_price,
                "stop_price": stop_price,
                "qty": qty,
                "filled_at": datetime.utcnow().isoformat()
            }
        else:
            updated[symbol] = order_data  # still pending

    save_json(positions, POSITION_FILE)
    save_json(updated, PENDING_FILE)

if __name__ == "__main__":
    while True:
        print("🔄 Monitoring pending orders...")
        check_pending_orders()
        time.sleep(SLEEP_SECONDS)

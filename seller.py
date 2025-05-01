import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv  # type: ignore
import ccxt  # type: ignore

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

# --- Utilities ---
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
    print(f"pending orders: {pending}")
    positions = load_json(POSITION_FILE)
    print(f"positions: {positions}")
    updated = {}

    for symbol, order_data in pending.items():
        order_id = order_data["order_id"]
        print(f"🔍 Checking order: {symbol} → {order_id}")
        order = fetch_order_status(order_id)

        if not order:
            updated[symbol] = order_data
            continue

        if order["status"] == "closed":
            filled_price = float(order["average"] or order_data["price"])
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
            updated[symbol] = order_data

    save_json(positions, POSITION_FILE)
    save_json(updated, PENDING_FILE)


def monitor_positions():
    positions = load_json(POSITION_FILE)
    portfolio = load_json(PORTFOLIO_FILE)
    updated_positions = {}

    for symbol, data in positions.items():
        current_price = get_price(symbol)
        if current_price is None:
            updated_positions[symbol] = data
            continue

        trailing_high = max(data["trailing_high"], current_price)
        new_stop_price = trailing_high * (1 - BOUNDARY)

        # Update trailing stop
        data["trailing_high"] = trailing_high
        data["stop_price"] = new_stop_price

        if current_price < new_stop_price:
            print(f"🚨 Selling {symbol}: price {current_price:.2f} < stop {new_stop_price:.2f}")
            try:
                order = kraken.create_market_sell_order(symbol, data["qty"])
                usd_received = current_price * data["qty"]
                portfolio["USD"] = portfolio.get("USD", 0) + usd_received
                print(f"✅ Sold {data['qty']} of {symbol}, received ~{usd_received:.2f} USD")
            except Exception as e:
                print(f"❌ Error selling {symbol}: {e}")
                updated_positions[symbol] = data
        else:
            updated_positions[symbol] = data

    save_json(updated_positions, POSITION_FILE)
    save_json(portfolio, PORTFOLIO_FILE)


if __name__ == "__main__":
    while True:
        print("🔄 Checking pending orders...")
        check_pending_orders()

        print("🔄 Monitoring filled positions for stop loss...")
        monitor_positions()

        time.sleep(SLEEP_SECONDS)

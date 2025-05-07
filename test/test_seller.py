import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv  # type: ignore
from scripts.utilities import load_json, save_json

# --- Config ---
load_dotenv()
TEST_PENDING_FILE = "data/test_pending_orders.json"
TEST_POSITION_FILE = "data/test_positions.json"
TEST_PORTFOLIO_FILE = "data/test_portfolio.json"
SLEEP_SECONDS = 30
BOUNDARY = 0.08  # 8% trailing stop

# --- Mock utilities ---
def mock_fetch_order_status(order_id):
    # Simulate all orders as filled immediately
    return {
        "status": "closed",
        "average": 1.0 + (hash(order_id) % 1000) / 1000.0,  # mock filled price
        "filled": 10.0  # mock filled qty
    }

def mock_get_price(symbol):
    # Return a simulated fluctuating price based on symbol hash
    base_price = 1.0 + (hash(symbol) % 1000) / 100.0
    multiplier = 1.02 if int(time.time()) % 2 == 0 else 0.97
    return round(base_price * multiplier, 2)

# --- Simulated Order Check ---
def check_pending_orders():
    pending = load_json(TEST_PENDING_FILE)
    print(f"🧪 Pending test orders: {pending}")
    positions = load_json(TEST_POSITION_FILE)
    updated = {}

    for symbol, order_data in pending.items():
        order_id = order_data["order_id"]
        print(f"🔍 TEST checking {symbol} → {order_id}")
        order = mock_fetch_order_status(order_id)

        if order["status"] == "closed":
            filled_price = float(order["average"] or order_data["price"])
            qty = order["filled"]
            stop_price = filled_price * (1 - BOUNDARY)

            print(f"✅ TEST filled {symbol} at {filled_price:.2f}, stop set to {stop_price:.2f}")

            positions[symbol] = {
                "entry_price": filled_price,
                "trailing_high": filled_price,
                "stop_price": stop_price,
                "qty": qty,
                "filled_at": datetime.utcnow().isoformat()
            }
        else:
            updated[symbol] = order_data

    save_json(positions, TEST_POSITION_FILE)
    save_json(updated, TEST_PENDING_FILE)

# --- Simulated Trailing Stop Monitoring ---
def monitor_positions():
    positions = load_json(TEST_POSITION_FILE)
    portfolio = load_json(TEST_PORTFOLIO_FILE)
    updated_positions = {}

    for symbol, data in positions.items():
        current_price = mock_get_price(symbol)
        trailing_high = max(data["trailing_high"], current_price)
        new_stop_price = trailing_high * (1 - BOUNDARY)

        data["trailing_high"] = trailing_high
        data["stop_price"] = new_stop_price

        if current_price < new_stop_price:
            print(f"🚨 TEST SELL {symbol}: price {current_price:.2f} < stop {new_stop_price:.2f}")
            usd_received = round(current_price * data["qty"], 2)
            portfolio["USD"] = portfolio.get("USD", 0) + usd_received
            print(f"✅ TEST sold {data['qty']} of {symbol}, +${usd_received:.2f} USD")
        else:
            print(f"💤 Holding {symbol} — price {current_price:.2f} above stop {new_stop_price:.2f}")
            updated_positions[symbol] = data

    save_json(updated_positions, TEST_POSITION_FILE)
    save_json(portfolio, TEST_PORTFOLIO_FILE)

if __name__ == "__main__":
    while True:
        print("🔄 [TEST] Checking mock pending orders...")
        check_pending_orders()

        print("🔄 [TEST] Monitoring test positions for stop-loss...")
        monitor_positions()

        time.sleep(SLEEP_SECONDS)

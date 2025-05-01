import os
import json
import time
import ccxt  # type: ignore
from dotenv import load_dotenv  # type: ignore

# Load environment variables
load_dotenv()

# File paths
PORTFOLIO_FILE = "data/portfolio.json"
POSITIONS_FILE = "data/positions.json"
PENDING_FILE = "data/pending_orders.json"

# Kraken setup
kraken = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_API_KEY"),
    'secret': os.getenv("KRAKEN_API_SECRET"),
    'enableRateLimit': True,
})


# Loaders & Savers
def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# Fetch balance from Kraken
def fetch_kraken_balances():
    return kraken.fetch_balance()


# Price fetch
def fetch_current_price(symbol):
    try:
        return kraken.fetch_ticker(symbol)['last']
    except Exception as e:
        print(f"Failed to fetch price for {symbol}: {e}")
        return None


# Update portfolio.json
def update_portfolio():
    portfolio = load_json(PORTFOLIO_FILE)
    balances = fetch_kraken_balances()

    updated_portfolio = {}
    usd_balance = balances['total'].get("USD", 0)
    updated_portfolio["USD"] = round(usd_balance, 6)
    print(f"USD: {usd_balance:.6f}")

    for coin, amount in balances['total'].items():
        if coin == "USD" or amount == 0:
            continue
        symbol = f"{coin}/USD"
        price = fetch_current_price(symbol)
        if price:
            usd_value = amount * price
            updated_portfolio[symbol] = round(usd_value, 6)
            print(f"{symbol}: {amount:.6f} ≈ ${usd_value:.2f}")
        time.sleep(0.3)

    save_json(updated_portfolio, PORTFOLIO_FILE)
    print("portfolio.json updated.")


# Verify open positions
def verify_positions():
    positions = load_json(POSITIONS_FILE)
    balances = fetch_kraken_balances()
    updated_positions = {}

    for symbol, entry in positions.items():
        coin = symbol.split("/")[0]
        if balances['total'].get(coin, 0) > 0:
            updated_positions[symbol] = entry
        else:
            print(f"No balance found for {symbol} — removing position.")

    save_json(updated_positions, POSITIONS_FILE)
    print("positions.json verified.")


# Check order status and clean pending_orders.json
def clean_pending_orders():
    pending = load_json(PENDING_FILE)
    updated_pending = []

    for order in pending:
        order_id = order.get("id")
        if not order_id:
            continue
        try:
            status = kraken.fetch_order(order_id)
            if status['status'] in ['open', 'pending']:
                updated_pending.append(order)
            else:
                print(f"Order {order_id} is {status['status']} — removing.")
        except Exception as e:
            print(f"Could not fetch order {order_id}: {e}")

        time.sleep(0.3)

    save_json(updated_pending, PENDING_FILE)
    print("pending_orders.json cleaned.")


# Main pipeline
def update_all():
    update_portfolio()
    verify_positions()
    clean_pending_orders()


if __name__ == "__main__":
    update_all()

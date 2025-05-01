import os
import json
import ccxt
import time
from dotenv import load_dotenv

load_dotenv()

def load_portfolio(filename="data/portfolio.json"):
    with open(filename, "r") as f:
        return json.load(f)

def save_portfolio(data, filename="data/portfolio.json"):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def fetch_kraken_balances():
    kraken = ccxt.kraken({
        'apiKey': os.getenv("KRAKEN_API_KEY"),
        'secret': os.getenv("KRAKEN_API_SECRET"),
        'enableRateLimit': True,
    })
    return kraken.fetch_balance()

def fetch_current_price(kraken, symbol):
    try:
        ticker = kraken.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        print(f"⚠️ Failed to fetch price for {symbol}: {e}")
        return None

def update_portfolio():
    portfolio = load_portfolio()
    kraken = ccxt.kraken({
        'apiKey': os.getenv("KRAKEN_API_KEY"),
        'secret': os.getenv("KRAKEN_API_SECRET"),
        'enableRateLimit': True,
    })
    balances = fetch_kraken_balances()

    for symbol in portfolio.keys():
        if symbol == "USDT/USD":
            coin = "USDT"
        else:
            coin = symbol.split("/")[0]

        balance = balances['total'].get(coin, 0)

        # If coin is USDT or USD, treat as cash
        if coin in ["USD", "USDT"]:
            usd_value = balance
        else:
            price = fetch_current_price(kraken, symbol)
            if price is None:
                continue
            usd_value = balance * price

        portfolio[symbol] = round(usd_value, 6)
        time.sleep(0.5)  # Be nice to Kraken

    save_portfolio(portfolio)
    print("✅ portfolio.json updated with live USD values.")

if __name__ == "__main__":
    update_portfolio()

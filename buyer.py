import os
import json
from dotenv import load_dotenv  # type: ignore
import ccxt  # type: ignore
from datetime import datetime

from utilities import load_json, save_json

load_dotenv()

MIN_SCORE_THRESHOLD = 0.7
BUY_PORTFOLIO_PERCENT = 0.10  # 10% of total portfolio

# --- Connect to Kraken ---
kraken = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_API_KEY"),
    'secret': os.getenv("KRAKEN_API_SECRET"),
    'enableRateLimit': True,
})

def buyer():
    portfolio = load_json("data/portfolio.json")
    ranked_coins = load_json("data/ranked_coins.json")
    pending_orders = load_json("data/pending_orders.json")

    total_value = sum(portfolio.values())
    available_usd = portfolio.get("USD", 0)
    max_alloc = total_value * BUY_PORTFOLIO_PERCENT

    print(f"💰 Portfolio total: ${total_value:.2f}, Available USD: ${available_usd:.2f}")

    for symbol, data in ranked_coins.items():
        score = data.get("score", 0)
        price = data.get("price", 0)

        if score < MIN_SCORE_THRESHOLD:
            continue

        if symbol in pending_orders:
            print(f"⏩ Skipping {symbol}, already has a pending order.")
            continue

        coin = symbol.split("/")[0]
        coin_pair = f"{coin}/USD"
        
        print(f"found potential order (coin: {coin}), checking available funds...")

        if available_usd >= max_alloc and price > 0:
            amount = round(max_alloc / price, 6)

            try:
                print(f"🛒 Placing buy order for {amount} {coin} at {price} USD")
                order = kraken.create_limit_buy_order(coin_pair, amount, price)
                print(f"✅ Order placed: {order['id']}")

                pending_orders[symbol] = {
                    "order_id": order["id"],
                    "symbol": symbol,
                    "price": price,
                    "timestamp": datetime.utcnow().isoformat()
                }

                available_usd -= max_alloc  # reduce for future checks

            except Exception as e:
                print(f"❌ Error placing order for {coin_pair}: {e}")
        else:
            print(f"⚠️ Not enough USD to buy {coin_pair} or invalid price")

    save_json(pending_orders, "data/pending_orders.json")

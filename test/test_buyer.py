import os
import json
from dotenv import load_dotenv  # type: ignore
from datetime import datetime
from scripts.utilities import load_json, save_json

load_dotenv()

MIN_SCORE_THRESHOLD = 0.6
BUY_PORTFOLIO_PERCENT = 0.10  # 10% of total portfolio

def test_buyer():
    portfolio = load_json("data/portfolio.json")
    ranked_coins = load_json("data/ranked_coins.json")
    pending_orders = load_json("data/test_pending_orders.json")

    total_value = sum(portfolio.values())
    available_usd = portfolio.get("USD", 0)
    max_alloc = total_value * BUY_PORTFOLIO_PERCENT

    print("🧪 TEST MODE: Simulating buy decisions...")
    print(f"💰 Portfolio total: ${total_value:.2f}, Available USD: ${available_usd:.2f}")
    print("--------------------------------------------------")

    for symbol, data in ranked_coins.items():
        score = data.get("score", 0)
        price = data.get("price", 0)

        if score < MIN_SCORE_THRESHOLD:
            print(f"❌ {symbol} skipped — score {score:.2f} below threshold.")
            continue

        if symbol in pending_orders:
            print(f"⏩ Skipping {symbol}, already has a test pending order.")
            continue

        coin = symbol.split("/")[0]
        coin_pair = f"{coin}/USD"
        print(f"🔍 Found candidate: {coin} (score={score:.2f}, price={price})")

        if available_usd >= max_alloc and price > 0:
            amount = round(max_alloc / price, 6)
            mock_order_id = f"test-{coin.lower()}-{datetime.utcnow().timestamp()}"

            print(f"✅ Simulated BUY: {amount} {coin} at ${price:.2f} (Order ID: {mock_order_id})")

            pending_orders[symbol] = {
                "order_id": mock_order_id,
                "symbol": symbol,
                "price": price,
                "timestamp": datetime.utcnow().isoformat(),
                "amount": amount
            }

            available_usd -= max_alloc  # simulate funds spent

        else:
            print(f"⚠️ Not enough USD to simulate buying {coin_pair} or invalid price")

    print("--------------------------------------------------")
    print(f"📝 {len(pending_orders)} test orders saved.")
    save_json(pending_orders, "data/test_pending_orders.json")

if __name__ == "__main__":
    test_buyer()

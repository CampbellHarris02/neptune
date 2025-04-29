import ccxt  # type: ignore
import pandas as pd  # type: ignore
import time
import csv
from datetime import datetime, timedelta
from pre_pipe import build_ohlc_features, cluster_confidence_bins
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

# Configuration
API_KEY = 'your_kraken_api_key'
API_SECRET = 'your_kraken_api_secret'
LOOKBACK_DAYS = 7
TOP_N_COINS = 10
UPDATE_INTERVAL = 60*20  # in seconds
ALLOCATION_METHOD = 'momentum_weighted'  # options: 'momentum_weighted', 'equal_weight'
INITIAL_CASH = 100  # USD
LOG_FILE = 'portfolio_log.csv'
TRADES_FILE = 'trades_log.csv'

# Initialize Kraken API
kraken = ccxt.kraken({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
})

# Portfolio and trading state
portfolio = {'USDT': INITIAL_CASH}

trading_state = {
    'ETH': {'position': False, 'buy_bin': None},
    'BTC': {'position': False, 'buy_bin': None},
    'USDT': {'position': False, 'buy_bin': None},
}


def setup_logs():
    with open(LOG_FILE, 'w', newline='') as f:
        csv.writer(f).writerow(['timestamp', 'symbol', 'volume', 'price', 'value_usd'])
    with open(TRADES_FILE, 'w', newline='') as f:
        csv.writer(f).writerow(['timestamp', 'action', 'symbol', 'amount', 'price', 'fee'])  # updated



def get_symbols():
    markets = kraken.load_markets()
    return [m for m in markets if m.endswith('/USD') and not m.startswith('Z')]


def fetch_ohlcv_ohlc(symbol, days=LOOKBACK_DAYS):
    since = kraken.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    ohlcv = kraken.fetch_ohlcv(symbol, timeframe='1h', since=since)
    if ohlcv:
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df.set_index('timestamp')
    return None


def compute_latest_bin(ohlc_df, pca_model, trained_kmeans):
    features = build_ohlc_features(ohlc_df[['open', 'high', 'low', 'close']])
    features_pca = pca_model.transform(features)
    bins = cluster_confidence_bins(features_pca, trained_kmeans)
    return bins[-1] if len(bins) > 0 else None



def calculate_momentum(df):
    if len(df) < LOOKBACK_DAYS:
        return None
    return (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]


def select_top_momentum_coins(symbols):
    scores = {}
    for symbol in symbols:
        try:
            df = fetch_ohlcv_ohlc(symbol)
            if df is not None:
                score = calculate_momentum(df)
                if score is not None:
                    scores[symbol] = score
        except Exception as e:
            print(f"Failed to fetch {symbol}: {e}")
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:TOP_N_COINS]


def get_target_allocations(selected_coins):
    if ALLOCATION_METHOD == 'equal_weight':
        return {symbol: 1 / len(selected_coins) for symbol, _ in selected_coins}
    elif ALLOCATION_METHOD == 'momentum_weighted':
        total = sum(max(score, 0) for _, score in selected_coins)
        return {symbol: max(score, 0) / total for symbol, score in selected_coins} if total > 0 else {
            symbol: 1 / len(selected_coins) for symbol, _ in selected_coins}


def fetch_prices(symbols):
    tickers = kraken.fetch_tickers(symbols)
    return {s: tickers[s]['last'] for s in symbols if s in tickers}


def portfolio_value(portfolio, prices):
    total = portfolio.get('USDT', 0)
    for asset, amount in portfolio.items():
        if asset != 'USDT':
            for symbol, price in prices.items():
                if symbol.split('/')[0] == asset:
                    total += amount * price
    return total



GAS_FEE_RATE = 0.01  # 1% per trade

def simulate_trade(side, symbol, amount, price):
    base = symbol.split('/')[0]

    if side == 'buy':
        available_usdt = portfolio.get('USDT', 0)

        # Adjust amount downward to what is affordable (including fee)
        max_affordable_amount = available_usdt / (price * (1 + GAS_FEE_RATE))
        amount = min(amount, max_affordable_amount)

        if amount <= 0:
            print(f"[⚠️] Not enough USDT to buy any {base}. Skipping.")
            return

        fee = amount * price * GAS_FEE_RATE
        total_cost = amount * price + fee

        portfolio['USDT'] -= total_cost
        portfolio[base] = portfolio.get(base, 0) + amount
        log_trade(side, symbol, amount, price, fee)

    elif side == 'sell':
        current_amt = portfolio.get(base, 0)
        amount = min(amount, current_amt)

        if amount <= 0:
            print(f"[⚠️] Not enough {base} to sell. Skipping.")
            return

        fee = amount * price * GAS_FEE_RATE
        proceeds = max(amount * price - fee, 0)

        portfolio[base] -= amount
        portfolio['USDT'] = portfolio.get('USDT', 0) + proceeds
        log_trade(side, symbol, amount, price, fee)





def log_trade(action, symbol, amount, price, fee):
    with open(TRADES_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([datetime.now(), action, symbol, amount, price, fee])
    print(f"[PAPER TRADE] {action.upper()} {amount:.4f} {symbol} at {price:.2f} USDT (fee: {fee:.4f})")



def log_portfolio(latest_prices):
    timestamp = datetime.now()
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        for asset, volume in portfolio.items():
            if asset == 'USDT':
                continue  # Cash reserve, skip it
            price = next((p for sym, p in latest_prices.items() if sym.split('/')[0] == asset), None)
            if price is None:
                continue
            value_usd = volume * price
            writer.writerow([timestamp, asset, volume, price, value_usd])



def rebalance_portfolio(target_allocations, prices):
    global latest_prices
    latest_prices = prices
    total_value = portfolio_value(portfolio, prices)

    for symbol, target_pct in target_allocations.items():
        base = symbol.split('/')[0]
        price = prices.get(symbol)
        if price is None:
            continue
        current_value = portfolio.get(base, 0) * price
        deviation = target_pct - (current_value / total_value if total_value > 0 else 0)
        if abs(deviation) > 0.02:
            amount = abs((deviation * total_value) / price)
            simulate_trade('buy' if deviation > 0 else 'sell', symbol, amount, price)

    log_portfolio(latest_prices)



# Main strategy loop
import time
import cvxpy as cp
import time

def get_bin_signals(symbols, symbol_models):
    bins = {}
    latest_prices = {}

    for symbol in symbols:
        print(f"\n[📊] Evaluating {symbol}")
        df = fetch_ohlcv_ohlc(symbol, days=3)

        if df is None or len(df) < 50:
            print(f"[!] Not enough data for {symbol}")
            continue

        if symbol not in symbol_models:
            print(f"[!] No model for {symbol}")
            continue

        model = symbol_models[symbol]
        current_bin = compute_latest_bin(df, model['pca'], model['kmeans'])
        price = df['close'].iloc[-1]

        if current_bin is not None:
            bins[symbol] = current_bin
            latest_prices[symbol] = price

    return bins, latest_prices


def optimize_portfolio(bins):
    scores = {s: (8 - b) for s, b in bins.items()}  # Higher score = lower bin
    assets = list(scores.keys())

    w = cp.Variable(len(assets))  # portfolio weights
    score_vec = cp.Parameter(len(assets))
    score_vec.value = [scores[s] for s in assets]

    objective = cp.Maximize(score_vec @ w)
    constraints = [
        cp.sum(w) == 1,
        w >= 0
    ]

    problem = cp.Problem(objective, constraints)
    problem.solve()

    optimal_weights = w.value

    return dict(zip(assets, optimal_weights))


def execute_rebalancing(optimal_allocations, latest_prices):
    total_value = portfolio_value(portfolio, latest_prices)

    adjustments = []

    for symbol, target_weight in optimal_allocations.items():
        base = symbol.split('/')[0]
        price = latest_prices.get(symbol)
        if price is None:
            continue

        target_value = total_value * target_weight
        current_value = portfolio.get(base, 0) * price if base in portfolio else 0
        deviation = target_value - current_value

        # Only act if deviation is significant
        if abs(deviation) / total_value > 0.02:
            amount = abs(deviation) / price
            side = 'buy' if deviation > 0 else 'sell'
            adjustments.append((side, symbol, amount, price))

    # 🟥 Step 1: Process all SELL orders to increase USDT
    for side, symbol, amount, price in adjustments:
        if side == 'sell':
            print(f"[💸] SELL {symbol.split('/')[0]} → amount: {amount:.4f} at {price:.2f}")
            simulate_trade('sell', symbol, amount, price)

    # 🟩 Step 2: Process all BUY orders with updated USDT balance
    for side, symbol, amount, price in adjustments:
        if side == 'buy':
            print(f"[🛒] BUY {symbol.split('/')[0]} → amount: {amount:.4f} at {price:.2f}")
            simulate_trade('buy', symbol, amount, price)

    # 📈 Save snapshot
    log_portfolio(latest_prices)





def main_loop(symbols, symbol_models):
    while True:
        bins, latest_prices = get_bin_signals(symbols, symbol_models)

        if not bins:
            print("[!] No valid bin signals, sleeping...")
            time.sleep(UPDATE_INTERVAL)
            continue

        optimal_allocations = optimize_portfolio(bins)

        print("\n[🧠] Optimal Portfolio Weights:")
        for asset, weight in optimal_allocations.items():
            print(f" - {asset}: {weight:.2%}")

        execute_rebalancing(optimal_allocations, latest_prices)

        time.sleep(UPDATE_INTERVAL)



if __name__ == "__main__":
    
    TRAIN_DAYS = 30
    symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'TON/USDT', 'DOGE/USDT', 'ADA/USDT']

    symbol_models = {}

    print("[🧠] Training PCA + KMeans models per symbol...")
    for symbol in symbols:
        df = fetch_ohlcv_ohlc(symbol, days=TRAIN_DAYS)
        if df is None or len(df) < 100:
            print(f"[!] Skipping {symbol} — not enough data")
            continue

        feats = build_ohlc_features(df[['open', 'high', 'low', 'close']])
        feats_df = pd.DataFrame(feats)

        pca = PCA(n_components=8)
        features_pca = pca.fit_transform(feats_df)

        kmeans = KMeans(n_clusters=8, random_state=42).fit(features_pca)

        symbol_models[symbol] = {'pca': pca, 'kmeans': kmeans}

    print("[✅] Model training complete.")
    
    setup_logs()
    
    main_loop(symbols, symbol_models)
    

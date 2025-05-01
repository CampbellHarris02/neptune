
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import os
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import mean_squared_error
import matplotlib.pyplot as plt
from scipy.stats import laplace


from dotenv import load_dotenv
import os
import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

import json



# Histogram setup
bin_width = 0.1
bin_range = 8
bins = np.arange(-bin_range * bin_width, (bin_range + 1) * bin_width, bin_width)
bin_centers = (bins[:-1] + bins[1:]) / 2
n_bins = len(bin_centers)

# Histograms (decayed over time)
hist_open = np.zeros(n_bins)
hist_high = np.zeros(n_bins)
hist_low = np.zeros(n_bins)
hist_close = np.zeros(n_bins)

# Parameters
decay_rate = 0.9  # exponential decay factor




# Configurable parameters
n_centroids = 8  # Number of quantization centroids

bin_width = 0.1

bins = np.arange(-bin_range * bin_width, (bin_range + 1) * bin_width, bin_width)
bin_centers = (bins[:-1] + bins[1:]) / 2
n_bins = len(bin_centers)

# Histograms

histogram_vectors = []


BOUNDARY = 0.08 #   +/- 8%


# Laplace + Quantizer helpers
def fit_asymmetric_laplace_from_histogram(bin_centers, counts, loc=0):
    counts = np.asarray(counts)
    x = bin_centers - loc
    left = x < 0
    right = x >= 0
    weights_left = counts[left]
    weights_right = counts[right]
    x_left = np.abs(x[left])
    x_right = np.abs(x[right])
    b_left = np.sum(weights_left * x_left) / np.sum(weights_left) if np.sum(weights_left) > 0 else 0.05
    b_right = np.sum(weights_right * x_right) / np.sum(weights_right) if np.sum(weights_right) > 0 else 0.05
    return b_left, b_right

def lloyd_max_quantizer(x, pdf, n_centroids, max_iter=5000, tol=1e-5):
    pmf = pdf / np.sum(pdf)
    centroids = np.linspace(x.min(), x.max(), n_centroids)
    for _ in range(max_iter):
        boundaries = np.convolve(centroids, [0.5, 0.5], mode='valid')
        partitions = np.digitize(x, boundaries)
        new_centroids = []
        for k in range(n_centroids):
            mask = partitions == k
            if np.any(mask):
                weights = pmf[mask]
                new_centroids.append(np.sum(x[mask] * weights) / np.sum(weights))
            else:
                new_centroids.append(centroids[k])
        new_centroids = np.array(new_centroids)
        if np.allclose(new_centroids, centroids, atol=tol):
            break
        centroids = new_centroids
    return centroids



def get_centroids(df):
    hist_combined = np.zeros(n_bins)  # ✅ now local to function
    centroid_array = []  # also make this local to avoid appending across multiple runs

    for frame in range(len(df)):
        row = df.iloc[frame]
        base_price = row["open"]
        prices = np.array([row["open"], row["high"], row["low"], row["close"]])
        deltas = prices - base_price

        hist_combined *= decay_rate
        hist_combined += np.histogram(deltas, bins=bins)[0]

        hist = hist_combined.copy()
        b_left, b_right = fit_asymmetric_laplace_from_histogram(bin_centers, hist, loc=0)

        x = np.linspace(bin_centers[0], bin_centers[-1], 300)
        y = np.where(x < 0,
                     0.5 * np.exp(x / b_left) / b_left,
                     0.5 * np.exp(-x / b_right) / b_right)
        y *= np.sum(hist) * bin_width  # Normalize to histogram mass

        centroids = lloyd_max_quantizer(x, y, n_centroids)
        centroid_array.append(centroids)

    return centroid_array
    





def cluster_centroids(centroid_series, n_clusters=8, random_state=42):
    """
    Cluster per-frame centroid vectors using KMeans and return cluster labels,
    the fitted model, and a nearest-neighbor quantizer function.
    """
    # Convert to 2D matrix: (n_frames, n_centroids)
    centroid_matrix = np.stack(centroid_series.to_numpy())

    # Fit KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state)
    labels = kmeans.fit_predict(centroid_matrix)

    # Define nearest-neighbor quantizer
    def quantize_centroids(new_centroids):
        new_centroids = np.atleast_2d(new_centroids)
        return kmeans.predict(new_centroids)

    return labels, kmeans, quantize_centroids




def find_good_clusters(df):
    # Precompute midprice for each row
    df["mid_price"] = df[["open", "high", "low", "close"]].median(axis=1)

    # Store results
    cluster_success_counts = {}
    cluster_total_counts = {}

    # Loop over each row (time step)
    for i in range(len(df)):
        cluster = df.iloc[i]["laplace_cluster"]
        midpoint = df.iloc[i]["mid_price"]

        upper = (1 + BOUNDARY) * midpoint
        lower = (1 - BOUNDARY) * midpoint

        # Look ahead in time
        future_prices = df.iloc[i+1:]["mid_price"].values

        hit_upper = np.argmax(future_prices >= upper) if np.any(future_prices >= upper) else None
        hit_lower = np.argmax(future_prices <= lower) if np.any(future_prices <= lower) else None

        success = False
        if hit_upper is not None and hit_lower is not None:
            success = hit_upper < hit_lower  # rises before it falls
        elif hit_upper is not None:
            success = True  # only rises
        else:
            success = False  # never rises

        # Tally
        cluster_total_counts[cluster] = cluster_total_counts.get(cluster, 0) + 1
        if success:
            cluster_success_counts[cluster] = cluster_success_counts.get(cluster, 0) + 1

    # Compute success ratios
    success_ratios = {}
    for cluster in cluster_total_counts:
        total = cluster_total_counts[cluster]
        success = cluster_success_counts.get(cluster, 0)
        ratio = success / total
        success_ratios[cluster] = ratio

    # Display as DataFrame
    summary_df = pd.DataFrame({
        "cluster": list(success_ratios.keys()),
        "success_ratio": list(success_ratios.values()),
        "successes": [cluster_success_counts.get(c, 0) for c in success_ratios],
        "total": [cluster_total_counts[c] for c in success_ratios]
    }).sort_values("success_ratio", ascending=False)

    print(summary_df)
    
    return df






def fetch_kraken_ohlcv(symbol="BTC/USD", timeframe="1h", lookback_days=30, limit_per_fetch=720, pause=1.2):
    """
    Fetch OHLCV price data from Kraken for a given symbol and lookback period.
    
    Args:
        symbol (str): Kraken trading pair (e.g., "BTC/USD", "ETH/USD")
        timeframe (str): OHLCV timeframe (e.g., '1h', '1d')
        lookback_days (int): How many days of data to fetch
        limit_per_fetch (int): Max candles per API call
        pause (float): Delay between calls to avoid rate limits

    Returns:
        pd.DataFrame: OHLCV dataframe with timestamp index
    """
    kraken = ccxt.kraken({
        'apiKey': os.getenv("KRAKEN_API_KEY"),
        'secret': os.getenv("KRAKEN_API_SECRET"),
        'enableRateLimit': True,
    })

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)
    since = int(start_time.timestamp() * 1000)

    all_ohlcv = []

    print(f"⏳ Fetching last {lookback_days} days of {symbol} ({timeframe}) data...")

    while True:
        try:
            ohlcv = kraken.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit_per_fetch)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            print(f"✅ Got {len(ohlcv)} candles — latest: {pd.to_datetime(ohlcv[-1][0], unit='ms')}")
            since = ohlcv[-1][0] + 1
            if pd.to_datetime(ohlcv[-1][0], unit='ms') >= end_time:
                break
            time.sleep(pause)
        except Exception as e:
            print(f"⚠️ Error: {e}. Retrying...")
            time.sleep(5)

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    print(f"✅ Fetched {len(df)} rows for {symbol}")
    return df



if __name__ == "__main__":
    assets = {
        "BTC/USD": "data/centroids/btc_usd_cluster_centers.json",
        "ETH/USD": "data/centroids/eth_usd_cluster_centers.json",
        "BNB/USD": "data/centroids/bnb_usd_cluster_centers.json",
        "SOL/USD": "data/centroids/sol_usd_cluster_centers.json",
        "XRP/USD": "data/centroids/xrp_usd_cluster_centers.json",
        "TON/USD": "data/centroids/ton_usd_cluster_centers.json",
        "DOGE/USD": "data/centroids/doge_usd_cluster_centers.json",
        "ADA/USD": "data/centroids/ada_usd_cluster_centers.json",
        "DOT/USD": "data/centroids/dot_usd_cluster_centers.json",
        "AVAX/USD": "data/centroids/avax_usd_cluster_centers.json",
        "LINK/USD": "data/centroids/link_usd_cluster_centers.json",
        "MATIC/USD": "data/centroids/matic_usd_cluster_centers.json",
        "SHIB/USD": "data/centroids/shib_usd_cluster_centers.json",
        "ATOM/USD": "data/centroids/atom_usd_cluster_centers.json",
        "LTC/USD": "data/centroids/ltc_usd_cluster_centers.json",
    }
    
    
    load_dotenv()

    cluster_models = {}

    for symbol, json_file in assets.items():
        print(f"\n🚀 Fetching and processing {symbol} from Kraken...")

        # Fetch data directly from Kraken
        df = fetch_kraken_ohlcv(symbol)
        df = df[['open', 'high', 'low', 'close']].dropna()

        # Compute Laplace centroids
        centroids = get_centroids(df)
        df["laplace_centroids"] = centroids

        # Run KMeans clustering
        labels, kmeans_model, quantize_centroids = cluster_centroids(df["laplace_centroids"], n_clusters=8)
        df["laplace_cluster"] = labels

        print(f"Cluster Centers for {symbol}:\n", kmeans_model.cluster_centers_)

        # Save the cluster centers (for nearest-neighbor quantization in real-time)
        cluster_centers = kmeans_model.cluster_centers_.tolist()
        with open(json_file, "w") as f:
            json.dump(cluster_centers, f)

        # Save full model and quantizer in memory if needed
        cluster_models[symbol] = {
            "model": kmeans_model,
            "quantizer": quantize_centroids
        }

        # Optional: evaluate clusters
        df_clusters = find_good_clusters(df)

    print("✅ All cluster centers saved.")

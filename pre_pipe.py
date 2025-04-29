import numpy as np
import pandas as pd
from scipy.linalg import eigh
import pywt

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans





# Wavelet Denoising

def wavelet_denoise(signal, wavelet='db4', level=None, threshold_method='soft'):
    coeffs = pywt.wavedec(signal, wavelet, mode='per', level=level)
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745
    uthresh = sigma * np.sqrt(2 * np.log(len(signal)))
    denoised_coeffs = [coeffs[0]] + [
        pywt.threshold(c, value=uthresh, mode=threshold_method)
        for c in coeffs[1:]
    ]
    return pywt.waverec(denoised_coeffs, wavelet, mode='per')[:len(signal)]


# Marcenko-Pastur Denoising

def mp_denoise(corr_matrix, n_samples):
    n_assets = corr_matrix.shape[0]
    q = n_samples / n_assets
    lambda_plus = (1 + 1 / np.sqrt(q)) ** 2

    evals, evecs = eigh(corr_matrix)
    cleaned_evals = np.where(evals > lambda_plus, evals, 0)
    cleaned_corr = (evecs @ np.diag(cleaned_evals) @ evecs.T)
    cleaned_corr /= np.outer(np.sqrt(np.diag(cleaned_corr)), np.sqrt(np.diag(cleaned_corr)))
    return cleaned_corr


# Feature Construction (Price-Based)

def build_features(price_series, window=10):
    df = pd.DataFrame({'price': price_series})
    df['returns'] = df['price'].pct_change()
    df['momentum'] = df['price'].diff(window)
    df['volatility'] = df['returns'].rolling(window).std()
    df['sharpe'] = df['returns'].rolling(window).mean() / df['volatility']
    features = df[['momentum', 'volatility', 'sharpe']].dropna()
    return (features - features.mean()) / features.std()


# Feature Construction (OHLC)

def build_ohlc_features(df):
    vectors = []
    prev_row = None
    for _, row in df.iterrows():
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        hl_range = h - l
        oc_change = c - o
        
        if hl_range == 0:
            hl_range = 1e-8
        features = [hl_range, oc_change, c, o, h, l]
        log_features = np.log(np.abs(features) + 1e-8)
        signed_sqrt = np.sign(features) * np.sqrt(np.abs(features))

        if prev_row is None:
            prev_row = features
            prev_diff = np.zeros_like(features)
        else:
            diff = np.array(features) - np.array(prev_row)
            accel = diff - prev_diff
            frame_vector = np.concatenate([features, log_features, signed_sqrt, diff, accel])
            vectors.append(frame_vector)
            prev_row = features
            prev_diff = diff

    return np.array(vectors)


# Eigenvector Feature Extraction

def add_eigenvector_features(corr_matrix, top_k=5):
    _, evecs = eigh(corr_matrix)
    return evecs[:, -top_k:]  # shape: (features, top_k)


# KMeans Clustering into Confidence Bins

def cluster_confidence_bins(features, kmeans):
    labels = kmeans.predict(features)
    cluster_centers = kmeans.cluster_centers_[:, 0]
    ranking = np.argsort(np.argsort(cluster_centers))
    return np.array([ranking[label] + 1 for label in labels])


# Run Example and Predict Momentum


if __name__ == "__main__":
    df = pd.read_csv("btc_usd_hourly_kraken.csv", index_col='timestamp', parse_dates=True)
    df = df[['open', 'high', 'low', 'close']].dropna()

    # Build Features
    features = build_ohlc_features(df)

    # Apply PCA to reduce dimensions
    n_components = 8
    pca = PCA(n_components=n_components)
    features_pca = pca.fit_transform(features)

    # Predict Future Momentum
    future_close = df['close'].shift(-1).values[len(df) - len(features_pca):]
    current_close = df['close'].values[len(df) - len(features_pca):]
    future_momentum = (future_close - current_close) > 0

    # Cluster with KMeans
    kmeans = KMeans(n_clusters=8, random_state=42).fit(features_pca)
    bins = cluster_confidence_bins(features_pca, kmeans)

    # Align and Plot
    aligned_price = df['close'].values[-len(bins):]
    x = np.arange(len(bins))

    plt.figure(figsize=(14, 6))
    for bin_level in range(1, 9):
        mask = bins == bin_level
        plt.fill_between(x, aligned_price.min(), aligned_price.max(), where=mask, alpha=0.1 + 0.02*bin_level, label=f"Bin {bin_level}", step='mid')

    plt.plot(x, aligned_price, label='Price', color='black', linewidth=1.5)
    plt.title("BTC Price with Clustered Confidence Bins (after PCA)")
    plt.xlabel("Time Step")
    plt.ylabel("Price")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    # Optional: Plot PCA Explained Variance
    plt.figure(figsize=(8, 4))
    plt.plot(np.cumsum(pca.explained_variance_ratio_), marker='o')
    plt.title("Cumulative Explained Variance by PCA Components")
    plt.xlabel("Number of Components")
    plt.ylabel("Cumulative Variance Explained")
    plt.grid(True)
    plt.show()
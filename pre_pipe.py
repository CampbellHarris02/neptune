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



# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# Feature Construction

def build_features(price_series, window=100):
    df = pd.DataFrame({'price': price_series})
    df['returns'] = df['price'].pct_change()
    df['momentum'] = df['price'].diff(window)
    df['volatility'] = df['returns'].rolling(window).std()
    df['sharpe'] = df['returns'].rolling(window).mean() / df['volatility']
    features = df[['momentum', 'volatility', 'sharpe']].dropna()
    return (features - features.mean()) / features.std()

# ─────────────────────────────────────────────────────────────────────────────
# Eigenvector Feature Extraction

def add_eigenvector_features(corr_matrix, top_k=3):
    _, evecs = eigh(corr_matrix)
    return evecs[:, -top_k:]  # shape: (features, top_k)

# ─────────────────────────────────────────────────────────────────────────────
# KMeans Clustering into Confidence Bins

def cluster_confidence_bins(features, kmeans):
    labels = kmeans.predict(features)
    cluster_centers = kmeans.cluster_centers_[:, 0]
    ranking = np.argsort(np.argsort(cluster_centers))
    return np.array([ranking[label] + 1 for label in labels])

# ─────────────────────────────────────────────────────────────────────────────
# Example Usage with Train-Test Split

if __name__ == "__main__":
    df = pd.read_csv("btc_usd_hourly_kraken.csv", index_col='timestamp', parse_dates=True)
    price = df['close'].dropna().values

    # Step 1: Denoise
    denoised = wavelet_denoise(price, wavelet='haar', level=3)

    # Train/Test split (80% train, 20% test)
    split = int(0.8 * len(denoised))
    train_price, test_price = denoised[:split], denoised[split:]

    # Step 2: Train Correlation Matrix + Denoising
    train_returns = pd.Series(train_price).pct_change().dropna()
    window = 100
    train_matrix = np.array([train_returns.shift(i) for i in range(window)]).T[window-1:]
    train_matrix = (train_matrix - train_matrix.mean(axis=0)) / train_matrix.std(axis=0)
    corr_matrix = np.corrcoef(train_matrix, rowvar=False)
    cleaned_corr = mp_denoise(corr_matrix, n_samples=train_matrix.shape[0])

    # Step 3: Train KMeans on Features
    train_features = build_features(train_price, window=window)
    kmeans = KMeans(n_clusters=5, random_state=42).fit(train_features)
    train_bins = cluster_confidence_bins(train_features, kmeans)

    # Step 4: Apply to Test Set
    test_features = build_features(test_price, window=window)
    test_bins = cluster_confidence_bins(test_features, kmeans)

    # Step 5: Plotting Test Results
    test_trimmed_price = test_price[-len(test_bins):]
    x = np.arange(len(test_bins))

    norm = mcolors.Normalize(vmin=1, vmax=5)
    colors = cm.viridis(norm(test_bins))

    plt.figure(figsize=(14, 6))
    ax1 = plt.gca()
    ax1.plot(x, test_trimmed_price, label='Price', color='royalblue', linewidth=2)
    ax1.set_ylabel('BTC/USD Price', fontsize=12)
    ax1.set_title("BTC Test Price + Clustered Confidence Signal", fontsize=14)
    ax1.grid(True, linestyle='--', alpha=0.3)
    for i in range(len(x)):
        ax1.scatter(x[i], test_trimmed_price[i], color=colors[i], s=15)

    bin_legend = [Line2D([0], [0], marker='o', color='w', label=f'Bin {i}',
                         markerfacecolor=cm.viridis(norm(i)), markersize=8)
                  for i in range(1, 6)]
    plt.legend(handles=[*bin_legend, Line2D([], [], color='royalblue', label='Price')], 
               title='Signal Strength', loc='lower right')
    plt.tight_layout()
    plt.show()

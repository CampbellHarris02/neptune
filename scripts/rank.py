
import numpy as np
import pandas as pd # type: ignore
import matplotlib.pyplot as plt # type: ignore
import matplotlib.animation as animation # type: ignore
import os
from sklearn.decomposition import PCA # type: ignore
from sklearn.cluster import KMeans # type: ignore
from sklearn.metrics import mean_squared_error # type: ignore
import matplotlib.pyplot as plt # type: ignore
from scipy.stats import laplace
from numba import njit

from sklearn.exceptions import ConvergenceWarning
import warnings

from dotenv import load_dotenv # type: ignore
import os
import ccxt # type: ignore
import pandas as pd # type: ignore
import time
from datetime import datetime, timedelta, timezone

import json

from pathlib import Path

from ta.momentum import RSIIndicator, ROCIndicator                # pip install ta
from ta.trend import MACD
from ta.utils import dropna
import numpy as np
import pandas as pd
import logging


# ───────────────────────────── Logging ─────────────────────────────
LOG_FILE = "log.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)


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

MAX_LOOKBACK_FOR_720_HOURS = {
    "1w":   720 * 168,   # 120,960 hours
    "1d":   720 * 24,    # 17,280 hours
    "4h":   720 * 4,     # 2,880 hours
    "1h":   720 * 1,     # 720 hours
    "30m":  720 * 0.5,   # 360 hours
    "15m":  720 * 0.25,  # 180 hours
    "5m":   720 * (5/60),# 60 hours
    "1m":   720 * (1/60) # 12 hours
}




# Configurable parameters
n_centroids = 8  # Number of quantization centroids

bin_width = 0.1

bins = np.arange(-bin_range * bin_width, (bin_range + 1) * bin_width, bin_width)
bin_centers = (bins[:-1] + bins[1:]) / 2
n_bins = len(bin_centers)

# Histograms

histogram_vectors = []


BOUNDARY = 0.08 #   +/- 8%


# efficient momentum computing
def add_ta_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Returns df with cached rsi, macd_diff, roc, sma20 columns."""
    if {"rsi","macd_diff","roc","sma20"}.issubset(df.columns):
        return df                                                   # already done

    close = df["close"]

    df["rsi"]       = RSIIndicator(close, 14).rsi()
    macd            = MACD(close)
    df["macd_diff"] = macd.macd() - macd.macd_signal()
    df["roc"]       = close.pct_change(5) * 100          # ≈ ROC
    df["sma20"]     = close.rolling(20).mean()

    return df

def momentum_from_row(row, close_std) -> float:
    rsi_s  = (row.rsi - 50) / 50
    macd_s = np.tanh(row.macd_diff / close_std)
    roc_s  = np.tanh(row.roc / 10)
    sma_s  = np.tanh(((row.close / row.sma20) - 1) * 10)
    return float(np.clip((rsi_s + macd_s + roc_s + sma_s) / 4, -1, 1))

def compute_momentum_score(df: pd.DataFrame) -> float:
    df = add_ta_columns(df)
    last = df.iloc[-1]
    return momentum_from_row(last, df["close"].std())



# Laplace + Quantizer helpers
def fit_asymmetric_laplace_from_histogram(bin_centers, counts, loc=0.0):
    x      = np.asarray(bin_centers) - loc
    counts = np.asarray(counts)
    left_mask  = x < 0
    right_mask = ~left_mask
    # dot product / sum  (faster than manual loops)
    w_left  = counts[left_mask]
    w_right = counts[right_mask]
    x_left  = np.abs(x[left_mask])
    x_right = np.abs(x[right_mask])
    b_left  = np.dot(w_left,  x_left ) / w_left.sum()  if w_left.sum()  else 0.05
    b_right = np.dot(w_right, x_right) / w_right.sum() if w_right.sum() else 0.05
    return b_left, b_right


def lloyd_max_quantizer(x, pdf, n_centroids, max_iter=200, tol=1e-5):
    """
    Vectorised Lloyd-Max quantiser (1-D) ~10-30x faster than naive loop.
    """
    pmf       = pdf / pdf.sum()
    centroids = np.linspace(x.min(), x.max(), n_centroids)

    for _ in range(max_iter):
        # mid-boundaries & partition indices
        bounds     = (centroids[:-1] + centroids[1:]) * 0.5
        partitions = np.searchsorted(bounds, x)

        # accumulate sums & weights in one shot
        sums   = np.bincount(partitions, weights=x * pmf, minlength=n_centroids)
        weights= np.bincount(partitions, weights=pmf,  minlength=n_centroids)
        new_c  = np.where(weights > 0, sums / weights, centroids)

        if np.allclose(new_c, centroids, atol=tol):
            break
        centroids = new_c
    return centroids




def get_centroids(
        df: pd.DataFrame,
        step: int = 5,
        grid_pts: int = 300,
        max_iter: int = 200,
) -> list[np.ndarray]:
    """
    Return list-of-centroid arrays (len == len(df)).
    Much faster than the naïve per-row Lloyd-Max loop.
    """
    if df.empty or not {"open", "high", "low", "close"}.issubset(df.columns):
        logger.warning("get_centroids: missing columns or empty DF")
        return []

    close_arr  = df[["open", "high", "low", "close"]].to_numpy(dtype=np.float32)
    N          = len(df)
    hist_comb  = np.zeros(n_bins, dtype=np.float64)
    centroids_prev = np.full(n_centroids, np.nan, dtype=np.float32)

    # pre-allocate result
    result = [None] * N

    # fixed grid for Lloyd-Max
    x_grid = np.linspace(bin_centers[0], bin_centers[-1], grid_pts, dtype=np.float64)

    for i in range(N):
        # vectorised delta calculation for 4 prices at row i
        base = close_arr[i, 0]                          # open price
        hist_comb *= decay_rate
        deltas = close_arr[i] - base
        hist_comb += np.histogram(deltas, bins=bins)[0]

        # recompute only every `step` rows (plus first row)
        if i == 0 or i % step == 0:
            b_l, b_r = fit_asymmetric_laplace_from_histogram(
                bin_centers, hist_comb, loc=0.0
            )
            y = np.where(
                    x_grid < 0,
                    0.5 * np.exp(x_grid / b_l) / b_l,
                    0.5 * np.exp(-x_grid / b_r) / b_r
                )
            y *= hist_comb.sum() * bin_width

            centroids_prev = lloyd_max_quantizer(
                x_grid, y, n_centroids, max_iter=max_iter
            )

        # reuse last-computed centroids
        result[i] = centroids_prev

    return result





def safe_cluster(series, k=8):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        return cluster_centroids(series, n_clusters=k)


def cluster_centroids(centroid_series, n_clusters=8, random_state=42):
    if len(centroid_series) == 0:
        raise ValueError("No centroid vectors to cluster — check data pipeline.")

    centroid_matrix = np.stack(centroid_series.to_numpy())

    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state)
    labels = kmeans.fit_predict(centroid_matrix)

    def quantize_centroids(new_centroids):
        new_centroids = np.atleast_2d(new_centroids)
        return kmeans.predict(new_centroids)

    return labels, kmeans, quantize_centroids






# find good clusters momuntum fast

#  1. Pre-compute momentum scores once (vectorised TA columns)
def add_momentum_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "mom_score" in df.columns:      # already computed
        return df

    close = df["close"]
    df["rsi"]       = RSIIndicator(close, 14).rsi()
    macd            = MACD(close)
    df["macd_diff"] = macd.macd() - macd.macd_signal()
    df["roc"]       = close.pct_change(5) * 100
    df["sma20"]     = close.rolling(20).mean()

    std = close.std()
    mom = (
        (df["rsi"]  - 50) / 50 +
        np.tanh(df["macd_diff"] / std) +
        np.tanh(df["roc"] / 10) +
        np.tanh(((close / df["sma20"]) - 1) * 10)
    ) / 4
    df["mom_score"] = np.clip(mom, -1, 1)
    return df


# 2. Numba-accelerated core loop (pure NumPy arrays)
@njit(cache=True, fastmath=True)
def _simulate(mid_px, clusters, mom, buy_fee,
              sl_pct, trig_pct, mom_win):

    n            = mid_px.size
    successes    = np.zeros(n, dtype=np.int32)
    totals       = np.zeros(n, dtype=np.int32)

    for i in range(n - 1):
        c          = clusters[i]
        entry_px   = mid_px[i] * (1.0 + buy_fee)
        sl_price   = entry_px * (1.0 - sl_pct)
        sl_raised  = False
        exit_px    = mid_px[-1]      # fallback

        j = i + 1
        while j < n:
            cur_px = mid_px[j]

            # raise SL once +2 %
            if (not sl_raised) and cur_px >= entry_px * (1.0 + trig_pct):
                sl_price  = entry_px * (1.0 + trig_pct)
                sl_raised = True

            # momentum exit
            if sl_raised and j - mom_win >= 0:
                if mom[j] < 0:        # mom score already pre-computed
                    exit_px = cur_px
                    break

            # hard SL
            if cur_px <= sl_price:
                exit_px = cur_px
                break

            j += 1

        # bookkeeping
        totals[c] += 1
        if exit_px - entry_px > 0:
            successes[c] += 1

    return successes, totals

# function wrapper
def find_good_clusters_momentum(df: pd.DataFrame,
                                     buy_fee: float = 0.0025,
                                     stop_loss_pct: float = 0.08,
                                     trigger_profit: float = 0.02,
                                     momentum_window: int = 60):

    df = df.copy()
    df["mid_price"] = df[["open", "high", "low", "close"]].median(axis=1)
    df = add_momentum_columns(df)

    # extract raw arrays for numba
    mid_px   = df["mid_price"].to_numpy(np.float64)
    clusters = df["laplace_cluster"].to_numpy(np.int32)
    mom      = df["mom_score"].to_numpy(np.float64)

    succ, tot = _simulate(mid_px, clusters, mom, buy_fee,
                          stop_loss_pct, trigger_profit, momentum_window)

    # convert to summary DataFrame
    clusters_seen = np.where(tot > 0)[0]
    summary = []
    for c in clusters_seen:
        ratio = succ[c] / (tot[c] + 2)      # Wilson smoothing
        summary.append((c, ratio, succ[c], tot[c]))

    df_summary = (pd.DataFrame(summary,
                   columns=["cluster", "success_ratio", "successes", "total"])
                   .sort_values("success_ratio", ascending=False))

    return df, df_summary



def analyze_coins(
        coin_folder: Path,
        n_clusters: int = 8,
        step_centroids: int = 5,           # reuse Lloyd-Max every 5 rows
) -> dict[str, float] | None:
    """
    Return {'score': final_ratio, 'price': latest_close}
    """
    symbol = coin_folder.name.replace("_", "/").upper()
    logger.info("Processing %s …", symbol)

    latest_price: float | None = None

    # 1-minute file for freshest price
    one_min_fp = coin_folder / "1m.csv"
    if one_min_fp.exists():
        latest_price = pd.read_csv(
            one_min_fp, usecols=["close"], dtype={"close": "float32"}
        ).iloc[-1, 0]

    total_succ = total_trades = 0

    for tf in MAX_LOOKBACK_FOR_720_HOURS:         # deterministic order
        fp = coin_folder / f"{tf}.csv"
        if not fp.exists():
            continue

        df = pd.read_csv(fp,
                         usecols=["timestamp", "open", "high", "low", "close"],
                         parse_dates=["timestamp"],
                         dtype={"open": "float32", "high": "float32",
                                "low": "float32", "close": "float32"})

        if df.empty:
            continue

        if latest_price is None:
            latest_price = float(df["close"].iloc[-1])

        # ---------- fast pipeline -----------------------------------
        df = df[["open", "high", "low", "close"]].dropna()

        df["laplace_centroids"] = get_centroids(df, step=step_centroids)

        df["laplace_cluster"], _, _ = safe_cluster(df["laplace_centroids"], k=8)


        _, summary = find_good_clusters_momentum(df, buy_fee=0.0025)
        cur_bin = int(df["laplace_cluster"].iloc[-1])

        row = summary.loc[summary["cluster"] == cur_bin]
        if row.empty:
            continue

        total_succ   += int(row["successes"].iloc[0])
        total_trades += int(row["total"].iloc[0])

    if total_trades == 0:
        logger.warning("%s skipped - no valid trades", symbol)
        return None

    final_ratio = total_succ / (total_trades + 10)
    logger.info("  %s final_ratio=%.4f (succ %d / %d)",
                symbol, final_ratio, total_succ, total_trades)

    return {
        "score": round(final_ratio, 4),
        "price": float(latest_price) if latest_price is not None else np.nan,
    }





# ─────────────────────────── rank all symbols ──────────────────────
def rank_coins() -> None:
    THIS_DIR = Path(__file__).resolve().parent          #  …/neptune/scripts
    ROOT = THIS_DIR.parent                          #  …/neptune
    HIST   = ROOT / "data" / "historical"
    OUTPUT = ROOT / "data" / "ranked_coins.json"

    ranking: dict[str, dict[str, float]] = {}

    for coin_dir in sorted(HIST.iterdir()):
        if not coin_dir.is_dir():
            continue
        result = analyze_coins(coin_dir)
        if result:
            symbol = coin_dir.name.replace("_", "/").upper()
            ranking[symbol] = result
        time.sleep(0.1)          # polite delay

    ranking_sorted = dict(
        sorted(ranking.items(), key=lambda x: x[1]["score"], reverse=True)
    )

    OUTPUT.write_text(json.dumps(ranking_sorted, indent=2))
    logger.info("ranked_coins.json written with %d symbols", len(ranking_sorted))


# manual run
if __name__ == "__main__":
    rank_coins()
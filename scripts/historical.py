import os
import time
import json
import pandas as pd
from datetime import datetime, timedelta, timezone
import ccxt # type: ignore

from dotenv import load_dotenv # type: ignore
load_dotenv()
import logging


LOG_FILE = "log.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

MAX_LOOKBACK_FOR_720_HOURS = {
    "1w":   720 * 168,   # 120,960 hours
    "1d":   720 * 24,    # 17,280 hours
    "4h":   720 * 4,     # 2,880 hours
    "1h":   720 * 1,     # 720 hours
    "30m":  720 * 0.5,   # 360 hours
    "15m":  720 * 0.25   # 180 hours
}

TIMEFRAME_DELTAS = {
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h":  timedelta(hours=1),
    "4h":  timedelta(hours=4),
    "1d":  timedelta(days=1),
    "1w":  timedelta(weeks=1),
}

ASSETS = {
    "BTC/USD": "data/centroids/btc_usd_cluster_centers.json",
    "ETH/USD": "data/centroids/eth_usd_cluster_centers.json",
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
    "TRX/USD": "data/centroids/trx_usd_cluster_centers.json",
    "XLM/USD": "data/centroids/xlm_usd_cluster_centers.json",
    "FIL/USD": "data/centroids/fil_usd_cluster_centers.json",
    "UNI/USD": "data/centroids/uni_usd_cluster_centers.json",
    "ALGO/USD": "data/centroids/algo_usd_cluster_centers.json",
    "EGLD/USD": "data/centroids/egld_usd_cluster_centers.json",
    "AAVE/USD": "data/centroids/aave_usd_cluster_centers.json",
    "NEAR/USD": "data/centroids/near_usd_cluster_centers.json",
    "XTZ/USD": "data/centroids/xtz_usd_cluster_centers.json",
    "CRV/USD": "data/centroids/crv_usd_cluster_centers.json",
    "RUNE/USD": "data/centroids/rune_usd_cluster_centers.json",
    "INJ/USD": "data/centroids/inj_usd_cluster_centers.json",
    "LDO/USD": "data/centroids/ldo_usd_cluster_centers.json",
    "SUI/USD": "data/centroids/sui_usd_cluster_centers.json",
    "STX/USD": "data/centroids/stx_usd_cluster_centers.json",
    "GRT/USD": "data/centroids/grt_usd_cluster_centers.json",
    "FLOW/USD": "data/centroids/flow_usd_cluster_centers.json",
    "ENS/USD": "data/centroids/ens_usd_cluster_centers.json",
    "IMX/USD": "data/centroids/imx_usd_cluster_centers.json",
    "SNX/USD": "data/centroids/snx_usd_cluster_centers.json",
    "KAVA/USD": "data/centroids/kava_usd_cluster_centers.json",
    "BCH/USD": "data/centroids/bch_usd_cluster_centers.json",
    "SAND/USD": "data/centroids/sand_usd_cluster_centers.json",
    "CHZ/USD": "data/centroids/chz_usd_cluster_centers.json",
    "APE/USD": "data/centroids/ape_usd_cluster_centers.json",
    "AXS/USD": "data/centroids/axs_usd_cluster_centers.json",
    "COMP/USD": "data/centroids/comp_usd_cluster_centers.json",
}

BASE_OUTPUT_DIR = "data/historical"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)



# ─────────────────────────────────────────────────────────────
# Fetch function
# ─────────────────────────────────────────────────────────────

def fetch_kraken_ohlcv(symbol, timeframe, lookback_amount, lookback_unit="hours", limit_per_fetch=720, pause=2.5):
    kraken = ccxt.kraken({
        'apiKey': os.getenv("KRAKEN_API_KEY"),
        'secret': os.getenv("KRAKEN_API_SECRET"),
        'enableRateLimit': True,
    })

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=lookback_amount)
    since = int(start_time.timestamp() * 1000)

    all_ohlcv = []

    while True:
        try:
            ohlcv = kraken.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit_per_fetch)
        except Exception as e:
            logging.info(f"Error fetching {symbol} [{timeframe}]: {e}")
            break

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1

        if len(ohlcv) < limit_per_fetch:
            break

        time.sleep(pause)

    if not all_ohlcv:
        logging.info(f"No data returned for {symbol} [{timeframe}]")
        return None

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    return df

# ─────────────────────────────────────────────────────────────
# Main Execution
# ─────────────────────────────────────────────────────────────

def historical(assets):
    """Update OHLCV data by fetching only the minimal recent data required to keep up-to-date."""
    for symbol in assets:
        symbol_id = symbol.replace("/", "_").lower()
        coin_dir = os.path.join(BASE_OUTPUT_DIR, symbol_id)
        os.makedirs(coin_dir, exist_ok=True)

        for timeframe, delta in TIMEFRAME_DELTAS.items():
            file_path = os.path.join(coin_dir, f"{timeframe}.csv")

            df_existing = None
            last_timestamp = None
            # Ensure last_timestamp is timezone-aware (UTC)
            if last_timestamp.tzinfo is None:
                last_timestamp = last_timestamp.tz_localize("UTC")


            # Try to read existing data
            if os.path.exists(file_path):
                try:
                    df_existing = pd.read_csv(file_path, parse_dates=["timestamp"])
                    df_existing.set_index("timestamp", inplace=True)
                    last_timestamp = df_existing.index[-1]
                except Exception as e:
                    logging.info(f"Error reading {file_path}: {e}")

            # Determine if update is needed
            now = datetime.now(timezone.utc)
            hours_to_fetch = 2 * delta.total_seconds() / 3600

            if last_timestamp:
                next_expected_time = last_timestamp + delta
                if next_expected_time > now:
                    logging.info(f"Up-to-date: {symbol} [{timeframe}] — skipping.")
                    continue
            else:
                logging.info(f"No file yet for {symbol} [{timeframe}] — creating with recent data.")

            # Always fetch 2 candles worth (minimally)
            df_new = fetch_kraken_ohlcv(symbol, timeframe, lookback_amount=hours_to_fetch)

            if df_new is None or df_new.empty:
                continue

            # Filter and combine only if prior data exists
            if df_existing is not None:
                df_new = df_new[df_new.index > df_existing.index[-1]]
                if df_new.empty:
                    logging.info(f"No new rows for {symbol} [{timeframe}]")
                    continue
                df_combined = pd.concat([df_existing, df_new])
                df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
                df_combined.sort_index(inplace=True)
                df_combined.to_csv(file_path)
                logging.info(f"Appended {len(df_new)} rows to {symbol} [{timeframe}]")
            else:
                df_new.to_csv(file_path)
                logging.info(f"Created new file with {len(df_new)} rows for {symbol} [{timeframe}]")

            time.sleep(2.5)  # Respect Kraken API rate limits



if __name__ == "__main__":
    historical(ASSETS)

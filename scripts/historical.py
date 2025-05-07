import os
import time
import json
import pandas as pd
from datetime import datetime, timedelta, timezone
import ccxt

from dotenv import load_dotenv
load_dotenv()

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
    "OP/USD": "data/centroids/op_usd_cluster_centers.json",
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
    "DYDX/USD": "data/centroids/dydx_usd_cluster_centers.json",
    "COMP/USD": "data/centroids/comp_usd_cluster_centers.json",
}

BASE_OUTPUT_DIR = "data/historical"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)



# ─────────────────────────────────────────────────────────────
# Fetch function
# ─────────────────────────────────────────────────────────────

def fetch_kraken_ohlcv(symbol, timeframe, lookback_amount, lookback_unit="hours", limit_per_fetch=720, pause=5):
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
            print(f"⚠️  Error fetching {symbol} [{timeframe}]: {e}")
            break

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1

        if len(ohlcv) < limit_per_fetch:
            break

        time.sleep(pause)

    if not all_ohlcv:
        print(f"⚠️  No data returned for {symbol} [{timeframe}]")
        return None

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    return df

# ─────────────────────────────────────────────────────────────
# Main Execution
# ─────────────────────────────────────────────────────────────

def historical(assets):
    """Download OHLCV for every symbol / timeframe and overwrite existing CSVs."""
    for symbol in assets:
        symbol_id = symbol.replace("/", "_").lower()
        coin_dir  = os.path.join(BASE_OUTPUT_DIR, symbol_id)
        os.makedirs(coin_dir, exist_ok=True)

        for timeframe, hours in MAX_LOOKBACK_FOR_720_HOURS.items():
            file_path = os.path.join(coin_dir, f"{timeframe}.csv")

            # always refresh (overwrite) ───────────────────────────────
            df = fetch_kraken_ohlcv(symbol, timeframe, lookback_amount=hours)
            time.sleep(5)   # polite delay for the API

            if df is not None and not df.empty:
                df.to_csv(file_path)



if __name__ == "__main__":
    historical(ASSETS)

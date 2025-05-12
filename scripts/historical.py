import os
import time
import json
import pandas as pd
from pandas.errors import EmptyDataError
from datetime import datetime, timedelta, timezone
import ccxt # type: ignore

import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv # type: ignore
load_dotenv()
import logging

from scripts.utilities import update_log_status


LOG_FILE = "log.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

STATUS_FILE = "status.txt"

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


TARGET_ROWS = 700                         # keep exactly 720 rows

# helper
def safe_fetch_ohlcv(symbol: str, tf: str, hours: float) -> pd.DataFrame:
    """Fetch OHLCV and handle errors gracefully."""
    df = fetch_kraken_ohlcv(symbol, tf, lookback_amount=hours)
    if df is not None and not df.empty:
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
    return df


def historical(assets, status):
    """Maintain a rolling 720-row UTC-aware OHLCV window for every symbol / timeframe."""
    total = len(assets)
    for i, symbol in enumerate(assets, 1):
        update_log_status(status=status, message=f"[{i}/{total}] Updating historical data for {symbol}...")

        sym_id = symbol.replace("/", "_").lower()
        coin_dir = os.path.join(BASE_OUTPUT_DIR, sym_id)
        os.makedirs(coin_dir, exist_ok=True)

        for tf, delta in TIMEFRAME_DELTAS.items():
            path = os.path.join(coin_dir, f"{tf}.csv")
            now = datetime.now(timezone.utc)

            # ── read existing file (if any) ──────────────────────────────
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    df = (
                        pd.read_csv(path, parse_dates=["timestamp"])
                        .set_index("timestamp")
                    )
                    if df.index.tzinfo is None:
                        df.index = df.index.tz_localize("UTC")
                else:
                    raise EmptyDataError("file missing or empty")
            except (ValueError, EmptyDataError):
                df = pd.DataFrame(
                    columns=["open", "high", "low", "close", "volume"],
                    index=pd.DatetimeIndex([], name="timestamp", tz="UTC")
                )

            # ── 1 · append forward ───────────────────────────────────────
            last_ts = df.index[-1] if not df.empty else now - TARGET_ROWS * delta
            while last_ts + delta <= now:
                look_hours = 100 * delta.total_seconds() / 3600
                new = safe_fetch_ohlcv(symbol, tf, look_hours)
                if new is None or new.empty:
                    break

                new = new[new.index > last_ts]
                if new.empty:
                    break

                df = pd.concat([df, new])
                last_ts = df.index[-1]
                logging.info(f"{symbol} [{tf}] appended {len(new)} rows")
                time.sleep(1.0)  # only after successful fetch

            # ── 2 · back-fill ────────────────────────────────────────────
            while len(df) < TARGET_ROWS:
                if df.empty:
                    earliest_needed = now - TARGET_ROWS * delta
                else:
                    earliest_needed = df.index[0] - (TARGET_ROWS - len(df)) * delta

                hours_back = (now - earliest_needed).total_seconds() / 3600 * 1.2
                old = safe_fetch_ohlcv(symbol, tf, hours_back)

                if old is None or old.empty:
                    logging.info(f"{symbol} [{tf}] cannot fetch further history")
                    break

                if not df.empty:
                    old = old[old.index < df.index[0]]
                if old.empty:
                    break

                df = pd.concat([old, df])
                logging.info(f"{symbol} [{tf}] prepended {len(old)} rows")
                time.sleep(1.0)  # only after successful fetch

            # ── 3 · Final sort, dedup, trim, save ────────────────────────
            df = df.sort_index().drop_duplicates().tail(TARGET_ROWS)
            df.to_csv(path)
            logging.info(f"{symbol} [{tf}] saved {len(df)} rows → {path}")







def fetch_kraken_my_trades(
        symbol: str,
        lookback_amount: int,
        lookback_unit: str = "hours",      # "hours", "days" …
        limit_per_fetch: int = 1000,       # Kraken returns max 1000 fills
        pause: float = 2.5                 # throttle between pages
    ) -> pd.DataFrame:
    """
    Fetch your personal trade history for <symbol> over the last <lookback_amount>
    units (eg. 24 hours, 30 days).  Returns a DataFrame with UTC-aware index and
    columns: side, price, qty.
    """
    kraken = ccxt.kraken({
        "apiKey": os.getenv("KRAKEN_API_KEY"),
        "secret": os.getenv("KRAKEN_API_SECRET"),
        "enableRateLimit": True,
    })

    # ---- time window ---------------------------------------------------
    end_time   = datetime.now(timezone.utc)
    delta_kw   = {lookback_unit: lookback_amount}
    start_time = end_time - timedelta(**delta_kw)
    since_ms   = int(start_time.timestamp() * 1000)

    all_rows   = []
    while True:
        try:
            trades = kraken.fetch_my_trades(symbol,
                                            since=since_ms,
                                            limit=limit_per_fetch)
        except Exception as e:
            logging.info(f"Error fetching trades for {symbol}: {e}")
            break

        if not trades:
            break

        # convert list[dict] → rows
        for t in trades:
            all_rows.append({
                "time":   pd.to_datetime(t["timestamp"], unit="ms", utc=True),
                "side":   t["side"],               # "buy" | "sell"
                "price":  float(t["price"]),
                "qty":    float(t["amount"]),
            })

        # advance 'since' cursor
        since_ms = int(trades[-1]["timestamp"]) + 1
        if len(trades) < limit_per_fetch:
            break    # finished window
        time.sleep(pause)

    if not all_rows:
        return pd.DataFrame(columns=["side","price","qty"],
                            index=pd.DatetimeIndex([], name="time", tz="UTC"))

    df = pd.DataFrame(all_rows).set_index("time").sort_index()
    return df[~df.index.duplicated(keep="last")]





def symbol_dir(sym: str) -> str:
    return sym.replace("/", "_").lower()

def load_events(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=["side","price","qty"],
                            index=pd.DatetimeIndex([], name="time", tz="UTC"))
    with open(path, "r") as f:
        arr = json.load(f)
    df = pd.DataFrame(arr).set_index("time")
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()

def save_events(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = df.reset_index()
    out["time"] = out["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w") as f:
        json.dump(out.to_dict(orient="records"), f, indent=2)

def update_events(assets, status, full_days_init: int = 90):
    """
    Refresh each <symbol>/events.json so it contains ALL personal fills.
    Reads existing rows, fetches only what's missing, appends, dedupes, saves.
    """
    total = len(assets)
    for i, sym in enumerate(assets, 1):
        message = f"[{i}/{total}] Updating historical events for {sym}..."
        update_log_status(status=status, message=message)
        folder = os.path.join("data", "historical", symbol_dir(sym))
        path   = os.path.join(folder, "events.json")

        df = load_events(path)          # existing (may be empty)

        # ── decide look-back window ───────────────────────────────────
        if df.empty:
            look_amount, look_unit = full_days_init, "days"
        else:
            last_ts    = df.index[-1]
            hours_diff = max(1, int((datetime.now(timezone.utc) - last_ts)
                                     .total_seconds() // 3600) + 1)
            look_amount, look_unit = hours_diff, "hours"

        # ── fetch new private trades ─────────────────────────────────
        new = fetch_kraken_my_trades(sym,
                                     lookback_amount = look_amount,
                                     lookback_unit   = look_unit)

        if new.empty:
            logging.info(f"{sym}: no new fills")
            continue

        # keep only rows strictly newer than our last stored candle
        if not df.empty:
            new = new[new.index > df.index[-1]]
        if new.empty:
            logging.info(f"{sym}: nothing beyond last stored fill")
            continue

        # ── combine, dedupe, save ───────────────────────────────────
        df = pd.concat([df, new]).sort_index()
        df = df[~df.index.duplicated(keep="last")]

        save_events(df, path)
        logging.info(f"{sym}: wrote {len(df)} rows → events.json (+{len(new)})")

        time.sleep(2.5)             # respect Kraken private rate-limit




if __name__ == "__main__":
    historical(ASSETS)

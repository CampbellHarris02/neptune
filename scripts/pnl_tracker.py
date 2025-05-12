# pnl_tracker.py  – append   data/account_pnl.csv   once per UTC-day
import csv, os, time, sys
from datetime import datetime, timezone
import pandas as pd
import ccxt       # only needed for typing / errors
import json

CSV_PATH = "data/account_pnl.csv"
JSON_PATH = "data/assets_usd.json"
SLEEP    = 1.2                   # rate-limit spacing for price calls

def _usd_price(kr, asset: str) -> float | None:
    """Spot price of <asset> in USD or None if pair unavailable."""
    asset = {"BTC": "XBT"}.get(asset, asset)         # Kraken quirk
    pair  = f"{asset}/USD"
    if pair not in kr.markets:                       # e.g. some small coins
        return None
    return kr.fetch_ticker(pair)["last"]

def _portfolio_value_usd(kr) -> float:
    bal   = kr.fetch_balance(params={"asset_class": "currency"})["total"]
    total = 0.0

    for asset, qty in bal.items():
        if qty == 0:
            continue
        if asset in ("USD", "ZUSD"):                 # cash balance
            total += qty
            continue
        price = _usd_price(kr, asset)
        if price is None:
            print(f"⚠ skip {asset}: no USD pair", file=sys.stderr)
            continue
        total += qty * price
        time.sleep(SLEEP)
    return round(total, 2)

def _last_row(path):
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path).iloc[-1]
    except Exception:
        return None

def update_account_pnl(kr: ccxt.kraken):
    """Call once – does nothing if today's snapshot already exists."""
    today  = datetime.now(timezone.utc).date().isoformat()
    last   = _last_row(CSV_PATH)

    if last is not None and str(last["date"]) == today:
        return                                           # already done today

    value = _portfolio_value_usd(kr)
    pct   = 0.0 if last is None else round(
            (value - last["value_usd"]) / last["value_usd"] * 100, 4)

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    header_needed = not os.path.exists(CSV_PATH)

    with open(CSV_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if header_needed:
            w.writerow(["date", "value_usd", "pct_pnl"])
        w.writerow([today, value, pct])
        
    with open(JSON_PATH, "w") as j:
        json.dump({"value_usd": value, "pct_pnl": pct}, j, indent=2)

    print(f"[PNL] {today}  ${value:,.2f}  ({pct:+.2f} %)")

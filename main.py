"""
Neptune trading-bot main runner (rich-enabled)
----------------------------------------------
This script coordinates hourly scanning/buying and five-minute stop-loss checks.
• Uses **rich** for minimal but colourful terminal feedback.
• All details are persisted in *log.txt* via the root logger.
"""

from __future__ import annotations

import time
import logging
from typing import Dict

from rich.console import Console # type: ignore
from rich.logging import RichHandler # type: ignore

# ───────────────────────────── Third‑party strategy modules ───────────────────
from centroids import ranked
from update_all import update_all
from buyer import buyer
from seller import check_pending_orders

# ───────────────────────────── Logging / Rich setup ──────────────────────────
LOG_FILE = "log.txt"
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        RichHandler(console=console, markup=True, rich_tracebacks=True),
    ],
)
logger = logging.getLogger(__name__)


ASSETS: Dict[str, str] = {
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
    "AR/USD": "data/centroids/ar_usd_cluster_centers.json",
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



def main() -> None:
    """Run hourly scans & five‑minute stop‑loss checks with rich output."""
    last_hourly = 0.0
    update_all()  # initial full sync
    console.rule("[bold cyan]Bot started")

    with console.status("[bold cyan]Running", spinner="earth"):
        while True:
            now = time.time()
            if now - last_hourly >= 1800:  # 30‑minute cadence
                console.log("[yellow]Hourly tasks (portfolio, scan, buyer)")
                update_all()
                ranked(assets=ASSETS)
                buyer()
                last_hourly = now

            console.log("[green]Five-minute stop-loss sweep")
            check_pending_orders()
            time.sleep(300)  # five‑minute pause


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.log("[red]User interrupt - shutting down…")
        logger.info("Bot terminated by user")
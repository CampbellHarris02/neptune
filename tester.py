import time
from centroids import ranked
from neptune.update_all import update_portfolio
from buyer import buyer
from seller import check_pending_orders

ASSETS = {
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
    "COMP/USD": "data/centroids/comp_usd_cluster_centers.json"
}

def tester():

        print("⏰ Running hourly tasks...")
        print("updating portfolio...")
        update_portfolio()
        print("scanning coins...")
        ranked(assets=ASSETS)

        time.sleep(300)  # wait 5 minutes

if __name__ == "__main__":
    tester()

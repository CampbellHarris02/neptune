import gradio as gr  # type: ignore
import pandas as pd  # type: ignore
import plotly.express as px  # type: ignore
import os

PORTFOLIO_LOG = "portfolio_log.csv"
TRADES_LOG = "trades_log.csv"

import ccxt  # Add this at the top with other imports

# Add these functions for real-time price updates
def fetch_real_time_prices(symbols):
    kraken = ccxt.kraken()
    try:
        tickers = kraken.fetch_tickers(symbols)
        return {s: tickers[s]['last'] for s in symbols if s in tickers}
    except Exception as e:
        print(f"Price fetch error: {e}")
        return {}

def get_current_holdings():
    if not os.path.exists(PORTFOLIO_LOG):
        return {}
    df = pd.read_csv(PORTFOLIO_LOG, parse_dates=['timestamp'])
    if df.empty:
        return {}
    
    # Get latest position for each asset
    latest_entries = df.loc[df.groupby('symbol')['timestamp'].idxmax()]
    return latest_entries.set_index('symbol')[['volume', 'price']].to_dict('index')

def calculate_live_portfolio():
    holdings = get_current_holdings()
    if not holdings:
        return 0, pd.DataFrame()
    
    # Get symbols excluding USDT
    symbols = [s for s in holdings.keys() if s != 'USDT']
    prices = fetch_real_time_prices(symbols)
    
    total_value = 0
    live_data = []
    
    # Add USDT value
    if 'USDT' in holdings:
        usdt_value = holdings['USDT']['volume']
        total_value += usdt_value
        live_data.append({
            'symbol': 'USDT',
            'value_usd': usdt_value,
            'price': 1.0,
            'volume': usdt_value
        })
    
    # Calculate crypto values
    for symbol, data in holdings.items():
        if symbol == 'USDT' or symbol not in prices:
            continue
            
        current_price = prices[symbol]
        current_value = data['volume'] * current_price
        total_value += current_value
        
        live_data.append({
            'symbol': symbol,
            'value_usd': current_value,
            'price': current_price,
            'volume': data['volume']
        })
    
    return total_value, pd.DataFrame(live_data)

# Modified update_dashboard function
def update_dashboard():
    if not os.path.exists(PORTFOLIO_LOG) or not os.path.exists(TRADES_LOG):
        return "❌ Log files not found.", None, None, None

    # Calculate live portfolio values
    total_value, live_snapshot = calculate_live_portfolio()
    portfolio_log = pd.read_csv(PORTFOLIO_LOG, parse_dates=['timestamp'])
    trades_log = pd.read_csv(TRADES_LOG, parse_dates=['timestamp'])

    # Create portfolio value timeline
    historical_values = portfolio_log.groupby('timestamp')['value_usd'].sum().reset_index()
    
    # Add current live value to timeline
    if not live_snapshot.empty:
        current_time = pd.Timestamp.now()
        historical_values = historical_values.append({
            'timestamp': current_time,
            'value_usd': total_value
        }, ignore_index=True)

    # Create visualizations
    fig1 = px.line(
        historical_values,
        x='timestamp',
        y='value_usd',
        title="📈 Portfolio Value (Historical + Live)",
        labels={'value_usd': 'Value (USDT)'}
    )
    
    fig2 = px.pie(
        live_snapshot,
        names='symbol',
        values='value_usd',
        title="📊 Live Portfolio Allocation"
    ) if not live_snapshot.empty else None

    # Format recent trades
    trades_table = None
    if not trades_log.empty:
        trades_table = trades_log.sort_values('timestamp', ascending=False).head(10)
        trades_table = trades_table[['timestamp', 'action', 'symbol', 'amount', 'price']]

    return "", fig1, fig2, trades_table
# Gradio App
with gr.Blocks() as demo:
    gr.Markdown("# 🚀 Momentum Portfolio Bot Dashboard")
    gr.Markdown("Track your portfolio performance and recent trades live.")

    refresh_button = gr.Button("🔄 Refresh Dashboard")

    error_box = gr.Markdown("")  # <--- error output

    with gr.Row():
        portfolio_plot = gr.Plot(label="Portfolio Value Over Time")
        holdings_pie = gr.Plot(label="Current Portfolio Allocation")

    trades_table = gr.Dataframe(
        label="Recent Trades",
        interactive=False,
        headers=["Timestamp", "Action", "Symbol", "Amount", "Price"]
    )

    refresh_button.click(
        fn=update_dashboard,
        outputs=[error_box, portfolio_plot, holdings_pie, trades_table]
    )

# Launch the app
demo.launch()
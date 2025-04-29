import gradio as gr  # type: ignore
import pandas as pd  # type: ignore
import plotly.express as px  # type: ignore
import os

PORTFOLIO_LOG = "portfolio_log.csv"
TRADES_LOG = "trades_log.csv"

def update_dashboard():
    if not os.path.exists(PORTFOLIO_LOG) or not os.path.exists(TRADES_LOG):
        return "❌ Log files not found.", None, None, None

    portfolio_log = pd.read_csv(PORTFOLIO_LOG, parse_dates=['timestamp'])
    trades_log = pd.read_csv(TRADES_LOG, parse_dates=['timestamp'])

    if portfolio_log.empty:
        return "❌ Portfolio log is empty.", None, None, None

    portfolio_value = portfolio_log.groupby('timestamp')['value_usd'].sum().reset_index()

    fig1 = px.line(
        portfolio_value,
        x='timestamp',
        y='value_usd',
        title="📈 Portfolio Value Over Time",
        labels={'value_usd': 'Portfolio Value (USDT)'}
    )

    latest_time = portfolio_log['timestamp'].max()
    latest_snapshot = portfolio_log[portfolio_log['timestamp'] == latest_time]

    fig2 = None
    if not latest_snapshot.empty:
        fig2 = px.pie(
            latest_snapshot,
            names='symbol',
            values='value_usd',
            title="📊 Current Portfolio Allocation"
        )

    trades_table = None
    if not trades_log.empty:
        trades_table = trades_log.sort_values('timestamp', ascending=False).head(10)

    return "", fig1, fig2, trades_table  # "" means no error


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

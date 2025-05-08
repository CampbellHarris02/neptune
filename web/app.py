from flask import Flask, render_template, jsonify, send_from_directory
import json
import os

app = Flask(__name__)


@app.route("/chart/<symbol>")
def chart(symbol):
    return render_template("chart.html", symbol=symbol.upper())

@app.route("/historical_data/<symbol>/<filename>")
def serve_csv(symbol, filename):
    return send_from_directory(f"data/historical/{symbol.lower()}", filename)



@app.route("/")
def home():
    return render_template("positions.html")

@app.route("/positions")
def get_positions():
    with open("data/positions.json") as f:
        return jsonify(json.load(f))

@app.route("/portfolio")
def get_portfolio():
    with open("data/portfolio.json") as f:
        return jsonify(json.load(f))

@app.route("/ranked_coins")
def get_ranked_coins():
    with open("data/ranked_coins.json") as f:
        return jsonify(json.load(f))
    
@app.route("/status")
def get_status():
    try:
        with open("status.txt") as f:
            status = f.read().strip()
        return jsonify({"status": status})
    except FileNotFoundError:
        return jsonify({"status": "No status available"}), 404



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

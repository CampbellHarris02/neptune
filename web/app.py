from flask import Flask, render_template, jsonify
import json
import os

app = Flask(__name__)

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
    app.run(debug=True)

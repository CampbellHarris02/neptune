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
        positions = json.load(f)
    return jsonify(positions)

if __name__ == "__main__":
    app.run(debug=True)

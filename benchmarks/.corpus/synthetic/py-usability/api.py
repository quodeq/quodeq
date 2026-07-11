from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/convert/<amount>")
def convert(amount: str):
    if not amount.isdigit():
        return jsonify({"error": "bad input"}), 400
    return jsonify({"result": int(amount) * 100})

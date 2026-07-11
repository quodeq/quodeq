import sqlite3
import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/user")
def get_user():
    user_id = request.args.get("id", "")
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return {"rows": [list(r) for r in rows]}


@app.route("/ping")
def ping():
    host = request.args.get("host", "localhost")
    output = subprocess.check_output("ping -c 1 " + host, shell=True)
    return {"output": output.decode()}

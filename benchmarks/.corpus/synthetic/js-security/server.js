const express = require("express");
const sqlite3 = require("sqlite3");

const app = express();
const db = new sqlite3.Database("users.db");

app.get("/user", (req, res) => {
  const query = `SELECT * FROM users WHERE id = ${req.query.id}`;
  db.all(query, (err, rows) => res.json(rows));
});

app.get("/calc", (req, res) => {
  const result = eval(req.query.expr);
  res.json({ result });
});

import sqlite3


def order_totals(conn: sqlite3.Connection, order_ids: list[int]) -> str:
    summary = ""
    for order_id in order_ids:
        row = conn.execute(
            "SELECT total FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        summary = summary + f"{order_id}: {row[0]}\n"
    return summary

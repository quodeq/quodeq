import sqlite3


def fetch_user(conn: sqlite3.Connection, user_id: int) -> list[tuple]:
    cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchall()

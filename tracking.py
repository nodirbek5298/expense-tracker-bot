"""Foydalanuvchilar va faollikni kuzatish (admin statistikasi uchun). Xabar matnlari saqlanmaydi."""
import sqlite3
from contextlib import closing
from datetime import timedelta
from typing import List, Optional

import db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _stamp(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def init() -> None:
    with closing(_conn()) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, "
            "name TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, msgs INTEGER NOT NULL DEFAULT 0)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, kind TEXT NOT NULL, at TEXT NOT NULL)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_at ON events(at)")
        c.commit()


def touch(user_id: int, username: Optional[str], name: str) -> bool:
    """Foydalanuvchini yozadi/yangilaydi. Yangi foydalanuvchi bo'lsa True qaytaradi."""
    now = _stamp(db.now())
    with closing(_conn()) as c:
        exists = c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if exists:
            c.execute(
                "UPDATE users SET username = ?, name = ?, last_seen = ?, msgs = msgs + 1 WHERE user_id = ?",
                (username, name, now, user_id),
            )
        else:
            c.execute(
                "INSERT INTO users (user_id, username, name, first_seen, last_seen, msgs) VALUES (?, ?, ?, ?, ?, 1)",
                (user_id, username, name, now, now),
            )
        c.commit()
    return exists is None


def log_event(user_id: int, kind: str) -> None:
    with closing(_conn()) as c:
        c.execute("INSERT INTO events (user_id, kind, at) VALUES (?, ?, ?)", (user_id, kind, _stamp(db.now())))
        c.commit()


def summary() -> dict:
    now = db.now()
    today = now.strftime("%Y-%m-%d")
    week = _stamp(now - timedelta(days=7))

    def one(c, sql, *params) -> int:
        return int(c.execute(sql, params).fetchone()[0])

    with closing(_conn()) as c:
        return {
            "users": one(c, "SELECT COUNT(*) FROM users"),
            "new_today": one(c, "SELECT COUNT(*) FROM users WHERE first_seen >= ?", today),
            "active_today": one(c, "SELECT COUNT(*) FROM users WHERE last_seen >= ?", today),
            "active_week": one(c, "SELECT COUNT(*) FROM users WHERE last_seen >= ?", week),
            "events_today": one(c, "SELECT COUNT(*) FROM events WHERE at >= ?", today),
            "records": one(c, "SELECT COUNT(*) FROM expenses"),
            "top": [
                (r["kind"], r["n"])
                for r in c.execute(
                    "SELECT kind, COUNT(*) AS n FROM events WHERE at >= ? "
                    "GROUP BY kind ORDER BY n DESC LIMIT 5", (week,)
                )
            ],
        }


def list_users(limit: int = 15) -> List[sqlite3.Row]:
    with closing(_conn()) as c:
        return c.execute(
            "SELECT u.user_id, u.username, u.name, u.last_seen, u.msgs, "
            "(SELECT COUNT(*) FROM expenses e WHERE e.user_id = u.user_id) AS records "
            "FROM users u ORDER BY u.last_seen DESC LIMIT ?", (limit,)
        ).fetchall()


def user_detail(user_id: int) -> Optional[dict]:
    week = _stamp(db.now() - timedelta(days=7))
    with closing(_conn()) as c:
        u = c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if u is None:
            return None
        records = c.execute("SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)).fetchone()[0]
        kinds = c.execute(
            "SELECT kind, COUNT(*) AS n FROM events WHERE user_id = ? AND at >= ? "
            "GROUP BY kind ORDER BY n DESC LIMIT 6", (user_id, week)
        ).fetchall()
    return {"user": dict(u), "records": records, "kinds": [(r["kind"], r["n"]) for r in kinds]}

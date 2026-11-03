"""SQLite bilan ishlash. Har bir foydalanuvchining ma'lumoti alohida (user_id bo'yicha)."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

DB_PATH = os.getenv("DB_PATH", "expenses.db")
TZ = ZoneInfo("Asia/Tashkent")


def now() -> datetime:
    return datetime.now(TZ)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                category TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_date ON expenses(user_id, created_at)"
        )
        conn.commit()


def add_expense(user_id: int, amount: int, category: str) -> int:
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, created_at) VALUES (?, ?, ?, ?)",
            (user_id, amount, category, stamp),
        )
        conn.commit()
        return int(cur.lastrowid)


def delete_expense(user_id: int, expense_id: int) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def last_expenses(user_id: int, limit: int = 10) -> List[sqlite3.Row]:
    with closing(_connect()) as conn:
        return conn.execute(
            "SELECT id, amount, category, created_at FROM expenses "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def period_start(period: str) -> str:
    """'today' | 'week' | 'month' uchun boshlanish sanasi (YYYY-MM-DD)."""
    today = now().date()
    if period == "today":
        start = today
    elif period == "week":
        start = today - timedelta(days=6)  # bugun bilan birga oxirgi 7 kun
    elif period == "month":
        start = today.replace(day=1)
    else:
        raise ValueError(f"Noma'lum davr: {period}")
    return start.strftime("%Y-%m-%d")


def summary_by_category(user_id: int, since: str) -> List[sqlite3.Row]:
    with closing(_connect()) as conn:
        return conn.execute(
            "SELECT category, SUM(amount) AS total, COUNT(*) AS n FROM expenses "
            "WHERE user_id = ? AND created_at >= ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, since),
        ).fetchall()


def delete_all(user_id: int) -> int:
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount

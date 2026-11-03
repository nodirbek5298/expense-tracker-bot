"""SQLite bilan ishlash. Har bir foydalanuvchining ma'lumoti alohida (user_id bo'yicha)."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
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
        cols = [r[1] for r in conn.execute("PRAGMA table_info(expenses)")]
        if "kind" not in cols:  # eski bazalarni yangilash
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN kind TEXT NOT NULL DEFAULT 'expense'"
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings ("
            "user_id INTEGER PRIMARY KEY, budget INTEGER NOT NULL)"
        )
        conn.commit()


def add_expense(user_id: int, amount: int, category: str, kind: str = "expense") -> int:
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, created_at, kind) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, stamp, kind),
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
            "WHERE user_id = ? AND kind = 'expense' ORDER BY id DESC LIMIT ?",
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
            "WHERE user_id = ? AND kind = 'expense' AND created_at >= ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, since),
        ).fetchall()


def delete_all(user_id: int) -> int:
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount


def history(user_id: int, limit: int = 8) -> List[sqlite3.Row]:
    """Oxirgi yozuvlar (xarajat va kirim birga) - Mini App tarixi uchun."""
    with closing(_connect()) as conn:
        return conn.execute(
            "SELECT id, kind, amount, category, created_at FROM expenses "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def month_totals(user_id: int, since: str) -> Tuple[int, int]:
    """(kirim, xarajat) jami, `since` sanasidan boshlab."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT kind, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? AND created_at >= ? GROUP BY kind",
            (user_id, since),
        ).fetchall()
    totals = {r["kind"]: r["total"] for r in rows}
    return totals.get("income", 0), totals.get("expense", 0)


def daily_expenses(user_id: int, days: int = 7) -> List[int]:
    """Oxirgi `days` kun xarajatlari (eskidan yangiga), bugun oxirida."""
    today = now().date()
    start = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT substr(created_at, 1, 10) AS d, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? AND kind = 'expense' AND created_at >= ? GROUP BY d",
            (user_id, start),
        ).fetchall()
    totals = {r["d"]: r["total"] for r in rows}
    return [
        totals.get((today - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d"), 0)
        for i in range(days)
    ]


def get_budget(user_id: int) -> Optional[int]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT budget FROM settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row["budget"]) if row else None


def set_budget(user_id: int, amount: int) -> None:
    """Oylik limitni saqlaydi; amount=0 bo'lsa limitni o'chiradi."""
    with closing(_connect()) as conn:
        if amount > 0:
            conn.execute(
                "INSERT INTO settings (user_id, budget) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET budget = excluded.budget",
                (user_id, amount),
            )
        else:
            conn.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
        conn.commit()

"""Eslatmalar, doimiy xarajatlar, CSV eksport va oylik hisobot (aiogram'ga bog'liq emas)."""
import csv
import io
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from typing import List, Optional

import db
from utils import fmt_money

MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul",
          "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with closing(_conn()) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS reminders ("
            "user_id INTEGER PRIMARY KEY, at TEXT NOT NULL, last_sent TEXT)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS recurring ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "amount INTEGER NOT NULL, category TEXT NOT NULL, "
            "day INTEGER NOT NULL, last_run TEXT)"
        )
        c.commit()


# --- kunlik eslatma ---------------------------------------------------------

def set_reminder(user_id: int, at: str) -> None:
    """at='HH:MM'. Vaqt bugun o'tib ketgan bo'lsa, birinchi eslatma ertaga bo'ladi."""
    now = db.now()
    last = now.strftime("%Y-%m-%d") if at <= now.strftime("%H:%M") else None
    with closing(_conn()) as c:
        c.execute(
            "INSERT INTO reminders (user_id, at, last_sent) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET at = excluded.at, last_sent = excluded.last_sent",
            (user_id, at, last),
        )
        c.commit()


def clear_reminder(user_id: int) -> bool:
    with closing(_conn()) as c:
        cur = c.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
        c.commit()
        return cur.rowcount > 0


def get_reminder(user_id: int) -> Optional[str]:
    with closing(_conn()) as c:
        row = c.execute("SELECT at FROM reminders WHERE user_id = ?", (user_id,)).fetchone()
    return row["at"] if row else None


def due_reminders(hhmm: str, today: str) -> List[int]:
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT user_id FROM reminders WHERE at <= ? AND (last_sent IS NULL OR last_sent != ?)",
            (hhmm, today),
        ).fetchall()
    return [r["user_id"] for r in rows]


def mark_reminded(user_id: int, today: str) -> None:
    with closing(_conn()) as c:
        c.execute("UPDATE reminders SET last_sent = ? WHERE user_id = ?", (today, user_id))
        c.commit()


def has_entry_since(user_id: int, since: str) -> bool:
    with closing(_conn()) as c:
        row = c.execute(
            "SELECT 1 FROM expenses WHERE user_id = ? AND created_at >= ? LIMIT 1",
            (user_id, since),
        ).fetchone()
    return row is not None


# --- doimiy (oylik) xarajatlar -----------------------------------------------

def add_recurring(user_id: int, amount: int, category: str, day: int) -> int:
    """Har oyning `day`-kuni (1-28) xarajat qo'shadi. Shu oyda kun o'tgan bo'lsa, keyingi oydan."""
    today = db.now().date()
    last_run = today.strftime("%Y-%m") if day <= today.day else None
    with closing(_conn()) as c:
        cur = c.execute(
            "INSERT INTO recurring (user_id, amount, category, day, last_run) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, day, last_run),
        )
        c.commit()
        return int(cur.lastrowid)


def list_recurring(user_id: int) -> List[sqlite3.Row]:
    with closing(_conn()) as c:
        return c.execute(
            "SELECT id, amount, category, day FROM recurring WHERE user_id = ? ORDER BY day, id",
            (user_id,),
        ).fetchall()


def delete_recurring(user_id: int, rid: int) -> bool:
    with closing(_conn()) as c:
        cur = c.execute("DELETE FROM recurring WHERE id = ? AND user_id = ?", (rid, user_id))
        c.commit()
        return cur.rowcount > 0


def due_recurring(today: date) -> List[sqlite3.Row]:
    """Bu oy hali bajarilmagan va kuni kelgan (yoki o'tib ketgan) yozuvlar."""
    with closing(_conn()) as c:
        return c.execute(
            "SELECT * FROM recurring WHERE day <= ? AND (last_run IS NULL OR last_run != ?)",
            (today.day, today.strftime("%Y-%m")),
        ).fetchall()


def mark_run(rid: int, ym: str) -> None:
    with closing(_conn()) as c:
        c.execute("UPDATE recurring SET last_run = ? WHERE id = ?", (ym, rid))
        c.commit()


# --- CSV eksport va oylik hisobot ---------------------------------------------

def export_rows(user_id: int, since: Optional[str] = None) -> List[sqlite3.Row]:
    sql = "SELECT created_at, kind, category, amount FROM expenses WHERE user_id = ?"
    params: list = [user_id]
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    with closing(_conn()) as c:
        return c.execute(sql + " ORDER BY id", params).fetchall()


def _safe_cell(text: str) -> str:
    """Excel formulasi sifatida ishlab ketmasligi uchun (=, +, -, @ bilan boshlansa)."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def to_csv(rows) -> bytes:
    """Excel (utf-8 BOM, nuqtali vergul) uchun CSV."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Sana", "Turi", "Kategoriya", "Summa"])
    for r in rows:
        kind = "kirim" if r["kind"] == "income" else "xarajat"
        w.writerow([r["created_at"], kind, _safe_cell(r["category"]), r["amount"]])
    return buf.getvalue().encode("utf-8-sig")


def expense_between(user_id: int, start: str, end: str) -> int:
    with closing(_conn()) as c:
        row = c.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses "
            "WHERE user_id = ? AND kind = 'expense' AND created_at >= ? AND created_at < ?",
            (user_id, start, end),
        ).fetchone()
    return int(row["t"])


def build_report(user_id: int) -> str:
    today = db.now().date()
    first = today.replace(day=1)
    prev_first = (first - timedelta(days=1)).replace(day=1)
    fmt = "%Y-%m-%d"
    income, expense = db.month_totals(user_id, first.strftime(fmt))
    if not income and not expense:
        return "Bu oy hali yozuv yo'q."
    prev = expense_between(user_id, prev_first.strftime(fmt), first.strftime(fmt))
    trend = f" ({round((expense - prev) / prev * 100):+d}% o'tgan oyga nisbatan)" if prev else ""
    balance = income - expense
    lines = [
        f"📅 {MONTHS[today.month - 1]} hisoboti", "",
        f"Kirim: {fmt_money(income)}",
        f"Xarajat: {fmt_money(expense)}{trend}",
        f"Balans: {'-' if balance < 0 else ''}{fmt_money(abs(balance))}",
        f"Kuniga o'rtacha: {fmt_money(round(expense / today.day))}",
    ]
    top = db.summary_by_category(user_id, first.strftime(fmt))[:3]
    if top:
        lines += ["", "Eng ko'p sarflangan:"]
        lines += [f"• {r['category']}: {fmt_money(r['total'])}" for r in top]
    budget = db.get_budget(user_id)
    if budget:
        lines += ["", f"🎯 Limit: {round(expense / budget * 100)}% ({fmt_money(expense)} / {fmt_money(budget)})"]
    return "\n".join(lines)

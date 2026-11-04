"""Telegram Mini App bilan ulanish: tugma, holat (statistika) va ilovadan kelgan buyruqlar."""
import json
import os
import re
from datetime import timedelta
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo,
)

import db
import extras
import store
from utils import MAX_AMOUNT, encode_payload, fmt_money

router = Router()
router.include_router(extras.router)

MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul",
          "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
MAX_URL_LEN = 2000
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _state(user_id: int) -> dict:
    """Mini App ko'rsatadigan holat: statistika, limit, grafik, tarix, eslatma, doimiy xarajatlar."""
    since = db.period_start("month")
    month = db.summary_by_category(user_id, since)
    income, expense = db.month_totals(user_id, since)
    today = db.summary_by_category(user_id, db.period_start("today"))
    first = db.now().date().replace(day=1)
    prev_first = (first - timedelta(days=1)).replace(day=1)
    prev = store.expense_between(
        user_id, prev_first.strftime("%Y-%m-%d"), first.strftime("%Y-%m-%d")
    )
    top = [[r["category"][:20], r["total"]] for r in month[:7]]
    rest = sum(r["total"] for r in month[7:])
    if rest:
        top.append(["boshqalar", rest])
    history = [
        [r["id"], r["kind"], r["amount"], r["category"][:20], r["created_at"][5:16]]
        for r in db.history(user_id, 8)
    ]
    return {
        "mn": MONTHS[db.now().month - 1],
        "m": top,
        "t": sum(r["total"] for r in today),
        "n": expense,
        "i": income,
        "p": prev,
        "b": db.get_budget(user_id) or 0,
        "d": db.daily_expenses(user_id),
        "h": history,
        "r": store.get_reminder(user_id) or "",
        "c": [
            [r["id"], r["amount"], r["category"][:20], r["day"]]
            for r in store.list_recurring(user_id)[:6]
        ],
    }


def webapp_url(user_id: int) -> Optional[str]:
    base = os.getenv("WEBAPP_URL")
    if not base:
        return None
    data = _state(user_id)
    sep = "&" if "?" in base else "?"
    while True:
        url = f"{base}{sep}s={encode_payload(data)}"
        if len(url) <= MAX_URL_LEN or not data["h"]:
            return url
        data["h"].pop()  # URL juda uzun bo'lsa, tarixni qisqartiramiz


def keyboard(user_id: int) -> Optional[ReplyKeyboardMarkup]:
    url = webapp_url(user_id)
    if url is None:
        return None
    button = KeyboardButton(text="📱 Ilovani ochish", web_app=WebAppInfo(url=url))
    return ReplyKeyboardMarkup(
        keyboard=[[button]], resize_keyboard=True, is_persistent=True
    )


def budget_note(user_id: int) -> str:
    budget = db.get_budget(user_id)
    if not budget:
        return ""
    spent = db.month_totals(user_id, db.period_start("month"))[1]
    if spent >= budget:
        return f"\n⚠️ Oylik limit oshib ketdi: {fmt_money(spent)} / {fmt_money(budget)}"
    if spent >= budget * 0.8:
        pct = round(spent / budget * 100)
        return f"\n⚠️ Limitning {pct}% sarflandi: {fmt_money(spent)} / {fmt_money(budget)}"
    return ""


def _category(payload: dict) -> str:
    return str(payload.get("category", "")).strip().lower()[:50] or "boshqa"


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    kb = keyboard(message.from_user.id)
    if kb is None:
        await message.answer("Mini App sozlanmagan: .env ichiga WEBAPP_URL ni yozing (README).")
        return
    await message.answer("Ilovani pastdagi tugma orqali oching 👇", reply_markup=kb)


@router.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    """Ilovadan keladigan buyruqlar: add, del, budget, export, remind, rec_add, rec_del."""
    uid = message.from_user.id
    try:
        payload = json.loads(message.web_app_data.data)
        action = payload.get("a", "add")
        if action == "add":
            amount = int(payload["amount"])
            if not 0 < amount <= MAX_AMOUNT:
                raise ValueError("amount")
            kind = "income" if payload.get("k") == "income" else "expense"
            category = _category(payload)
            expense_id = db.add_expense(uid, amount, category, kind)
            label = "💰 Kirim" if kind == "income" else "✅ Xarajat"
            text = f"{label}: {fmt_money(amount)} - {category} (#{expense_id})"
            if kind == "expense":
                text += budget_note(uid)
        elif action == "del":
            expense_id = int(payload["id"])
            if db.delete_expense(uid, expense_id):
                text = f"🗑 #{expense_id} o'chirildi."
            else:
                text = "Bunday yozuv topilmadi."
        elif action == "budget":
            amount = int(payload["amount"])
            if not 0 <= amount <= MAX_AMOUNT:
                raise ValueError("budget")
            db.set_budget(uid, amount)
            text = f"🎯 Oylik limit: {fmt_money(amount)}" if amount else "Limit o'chirildi."
        elif action == "export":
            this_month = bool(payload.get("m"))
            rows = store.export_rows(uid, db.period_start("month") if this_month else None)
            if rows:
                name = "xarajatlar_oy.csv" if this_month else "xarajatlar.csv"
                await message.answer_document(
                    BufferedInputFile(store.to_csv(rows), filename=name),
                    caption=f"{len(rows)} ta yozuv. Excel'da ochish mumkin.",
                )
                text = "📤 Fayl yuborildi."
            else:
                text = "Yuklash uchun yozuv yo'q."
        elif action == "remind":
            at = str(payload.get("t", "")).strip()
            if not at:
                text = "Eslatma o'chirildi." if store.clear_reminder(uid) else "Eslatma allaqachon o'chiq."
            else:
                match = TIME_RE.match(at)
                if not match:
                    raise ValueError("time")
                at = f"{int(match.group(1)):02d}:{match.group(2)}"
                store.set_reminder(uid, at)
                text = f"⏰ Tayyor: har kuni {at} da eslataman (o'sha kuni yozuv bo'lmasa)."
        elif action == "rec_add":
            amount, day = int(payload["amount"]), int(payload["day"])
            if not 0 < amount <= MAX_AMOUNT or not 1 <= day <= 28:
                raise ValueError("recurring")
            category = _category(payload)
            rid = store.add_recurring(uid, amount, category, day)
            start = "shu oydan" if day > db.now().day else "keyingi oydan"
            text = f"🔁 #{rid}: har oyning {day}-kuni {fmt_money(amount)} - {category} ({start})."
        elif action == "rec_del":
            ok = store.delete_recurring(uid, int(payload["id"]))
            text = "🗑 Doimiy xarajat o'chirildi." if ok else "Bunday yozuv topilmadi."
        else:
            raise ValueError("action")
    except (ValueError, KeyError, TypeError, AttributeError):
        await message.answer("Ilovadan kelgan ma'lumotni o'qib bo'lmadi.")
        return
    await message.answer(text, reply_markup=keyboard(uid))

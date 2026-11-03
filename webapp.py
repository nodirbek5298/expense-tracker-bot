"""Telegram Mini App bilan ulanish: tugma, holat (statistika) va ilovadan kelgan buyruqlar."""
import json
import os
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

import db
import extras
from utils import MAX_AMOUNT, encode_payload, fmt_money

router = Router()
router.include_router(extras.router)

MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul",
          "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
MAX_URL_LEN = 2000


def _state(user_id: int) -> dict:
    """Mini App ko'rsatadigan holat: oylik statistika, limit, kunlik grafik, tarix."""
    since = db.period_start("month")
    month = db.summary_by_category(user_id, since)
    income, expense = db.month_totals(user_id, since)
    today = db.summary_by_category(user_id, db.period_start("today"))
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
        "b": db.get_budget(user_id) or 0,
        "d": db.daily_expenses(user_id),
        "h": history,
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


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    kb = keyboard(message.from_user.id)
    if kb is None:
        await message.answer("Mini App sozlanmagan: .env ichiga WEBAPP_URL ni yozing (README).")
        return
    await message.answer("Ilovani pastdagi tugma orqali oching 👇", reply_markup=kb)


@router.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    """Ilovadan keladigan buyruqlar: add (xarajat/kirim), del, budget."""
    uid = message.from_user.id
    try:
        payload = json.loads(message.web_app_data.data)
        action = payload.get("a", "add")
        if action == "add":
            amount = int(payload["amount"])
            if not 0 < amount <= MAX_AMOUNT:
                raise ValueError("amount")
            kind = "income" if payload.get("k") == "income" else "expense"
            category = str(payload.get("category", "")).strip().lower()[:50] or "boshqa"
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
        else:
            raise ValueError("action")
    except (ValueError, KeyError, TypeError, AttributeError):
        await message.answer("Ilovadan kelgan ma'lumotni o'qib bo'lmadi.")
        return
    await message.answer(text, reply_markup=keyboard(uid))

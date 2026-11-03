"""Telegram Mini App bilan ulanish: tugma, statistika va ilovadan kelgan ma'lumot."""
import json
import os
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

import db
from utils import MAX_AMOUNT, encode_payload, fmt_money

router = Router()

MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul",
          "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]


def webapp_url(user_id: int) -> Optional[str]:
    """Mini App manzili + shu foydalanuvchining oylik statistikasi (?s=...)."""
    base = os.getenv("WEBAPP_URL")
    if not base:
        return None
    month = db.summary_by_category(user_id, db.period_start("month"))
    today = db.summary_by_category(user_id, db.period_start("today"))
    top = [[r["category"][:20], r["total"]] for r in month[:7]]
    rest = sum(r["total"] for r in month[7:])
    if rest:
        top.append(["boshqalar", rest])
    data = {
        "mn": MONTHS[db.now().month - 1],
        "m": top,
        "t": sum(r["total"] for r in today),
        "n": sum(r["total"] for r in month),
    }
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}s={encode_payload(data)}"


def keyboard(user_id: int) -> Optional[ReplyKeyboardMarkup]:
    url = webapp_url(user_id)
    if url is None:
        return None
    button = KeyboardButton(text="📱 Ilovani ochish", web_app=WebAppInfo(url=url))
    return ReplyKeyboardMarkup(
        keyboard=[[button]], resize_keyboard=True, is_persistent=True
    )


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    kb = keyboard(message.from_user.id)
    if kb is None:
        await message.answer("Mini App sozlanmagan: .env ichiga WEBAPP_URL ni yozing (README).")
        return
    await message.answer("Ilovani pastdagi tugma orqali oching 👇", reply_markup=kb)


@router.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
        amount = int(payload["amount"])
        category = str(payload.get("category", "")).strip().lower()[:50] or "boshqa"
    except (ValueError, KeyError, TypeError):
        await message.answer("Ilovadan kelgan ma'lumotni o'qib bo'lmadi.")
        return
    if not 0 < amount <= MAX_AMOUNT:
        await message.answer("Summa noto'g'ri.")
        return
    expense_id = db.add_expense(message.from_user.id, amount, category)
    await message.answer(
        f"✅ Qo'shildi: {fmt_money(amount)} - {category} (#{expense_id})",
        reply_markup=keyboard(message.from_user.id),
    )

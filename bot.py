"""Xarajatlar hisobi Telegram boti (aiogram 3).

Ishlatish: xabar yozing, masalan "25000 tushlik" yoki "taksi 15k".
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

import db
import webapp
from utils import fmt_money, parse_expense

load_dotenv()

router = Router()

HELP_TEXT = (
    "💸 Xarajatlar hisobi boti\n\n"
    "Xarajat qo'shish: summa va izohni yozing\n"
    "  25000 tushlik\n"
    "  taksi 15k\n"
    "  120 ming kiyim\n\n"
    "Buyruqlar:\n"
    "/today - bugungi xarajatlar\n"
    "/week - oxirgi 7 kun\n"
    "/month - shu oy\n"
    "/last - oxirgi 10 ta yozuv\n"
    "/delete 12 - 12-raqamli yozuvni o'chirish\n"
    "/app - Mini App (ilova)\n"
    "/reset - barcha ma'lumotlarimni o'chirish\n"
    "/help - yordam"
)

PERIOD_TITLES = {
    "today": "Bugun",
    "week": "Oxirgi 7 kun",
    "month": "Shu oy",
}


def build_summary(user_id: int, period: str) -> str:
    title = PERIOD_TITLES[period]
    rows = db.summary_by_category(user_id, db.period_start(period))
    if not rows:
        return f"{title}: xarajat yo'q 🎉"
    total = sum(r["total"] for r in rows)
    lines = [f"📊 {title}", ""]
    for r in rows:
        lines.append(f"• {r['category']}: {fmt_money(r['total'])} ({r['n']} ta)")
    lines += ["", f"Jami: {fmt_money(total)}"]
    return "\n".join(lines)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=webapp.keyboard(message.from_user.id))


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    await message.answer(build_summary(message.from_user.id, "today"))


@router.message(Command("week"))
async def cmd_week(message: Message) -> None:
    await message.answer(build_summary(message.from_user.id, "week"))


@router.message(Command("month"))
async def cmd_month(message: Message) -> None:
    await message.answer(build_summary(message.from_user.id, "month"))


@router.message(Command("last"))
async def cmd_last(message: Message) -> None:
    rows = db.last_expenses(message.from_user.id, 10)
    if not rows:
        await message.answer("Hali yozuv yo'q. Masalan: 25000 tushlik")
        return
    lines = ["🧾 Oxirgi yozuvlar", ""]
    for r in rows:
        day = r["created_at"][5:16]  # MM-DD HH:MM
        lines.append(f"#{r['id']}  {day}  {fmt_money(r['amount'])} - {r['category']}")
    lines += ["", "O'chirish: /delete <raqam>"]
    await message.answer("\n".join(lines))


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdigit():
        await message.answer("Raqamni yozing, masalan: /delete 12")
        return
    if db.delete_expense(message.from_user.id, int(arg)):
        await message.answer(f"🗑 #{arg} o'chirildi.")
    else:
        await message.answer("Bunday yozuv topilmadi.")


@router.message(Command("reset"))
async def cmd_reset(message: Message, command: CommandObject) -> None:
    if (command.args or "").strip().lower() != "ha":
        await message.answer(
            "Barcha xarajatlaringiz o'chadi. Tasdiqlash uchun yozing:\n/reset ha"
        )
        return
    count = db.delete_all(message.from_user.id)
    await message.answer(f"Tayyor, {count} ta yozuv o'chirildi.")


@router.message(F.text, ~F.text.startswith("/"))
async def add_expense(message: Message) -> None:
    parsed = parse_expense(message.text)
    if parsed is None:
        await message.answer(
            "Summani tushunmadim 🤔\nMasalan: 25000 tushlik yoki taksi 15k\n/help - yordam"
        )
        return
    amount, category = parsed
    expense_id = db.add_expense(message.from_user.id, amount, category)
    await message.answer(
        f"✅ Qo'shildi: {fmt_money(amount)} - {category} (#{expense_id})",
        reply_markup=webapp.keyboard(message.from_user.id),
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylini tekshiring (README'ga qarang).")
    db.init_db()
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(webapp.router)
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

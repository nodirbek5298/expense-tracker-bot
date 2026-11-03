"""Qo'shimcha buyruqlar (/export, /report, /remind, /recurring) va fon vazifalari."""
import asyncio
import logging
import re
from typing import Optional

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BotCommand, BufferedInputFile, Message

import db
import store
from utils import fmt_money, parse_expense

router = Router()
_task: Optional[asyncio.Task] = None
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

COMMANDS = [
    BotCommand(command="app", description="Mini App (ilova)"),
    BotCommand(command="today", description="Bugungi xarajatlar"),
    BotCommand(command="week", description="Oxirgi 7 kun"),
    BotCommand(command="month", description="Shu oy"),
    BotCommand(command="report", description="Oylik hisobot"),
    BotCommand(command="export", description="Excel (CSV) yuklab olish"),
    BotCommand(command="last", description="Oxirgi yozuvlar"),
    BotCommand(command="remind", description="Kunlik eslatma"),
    BotCommand(command="recurring", description="Doimiy xarajatlar"),
    BotCommand(command="help", description="Yordam"),
]

RECURRING_HELP = (
    "Doimiy xarajatlar (har oy avtomatik qo'shiladi):\n"
    "/recurring add 150000 ijara 5 - har oyning 5-kuni\n"
    "/recurring del <raqam> - o'chirish\n"
    "Kun 1 dan 28 gacha bo'lishi kerak."
)


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    await message.answer(store.build_report(message.from_user.id))


@router.message(Command("export"))
async def cmd_export(message: Message, command: CommandObject) -> None:
    this_month = (command.args or "").strip().lower() in ("oy", "month")
    rows = store.export_rows(message.from_user.id, db.period_start("month") if this_month else None)
    if not rows:
        await message.answer("Yuklash uchun yozuv yo'q.")
        return
    name = "xarajatlar_oy.csv" if this_month else "xarajatlar.csv"
    await message.answer_document(
        BufferedInputFile(store.to_csv(rows), filename=name),
        caption=f"{len(rows)} ta yozuv. Excel'da ochish mumkin.\nFaqat shu oy: /export oy",
    )


@router.message(Command("remind"))
async def cmd_remind(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id
    arg = (command.args or "").strip().lower()
    if not arg:
        at = store.get_reminder(uid)
        await message.answer(
            f"⏰ Eslatma: har kuni {at}\nO'chirish: /remind off" if at
            else "Eslatma o'chiq. Yoqish: /remind 21:00"
        )
    elif arg in ("off", "o'chirish"):
        await message.answer("Eslatma o'chirildi." if store.clear_reminder(uid) else "Eslatma allaqachon o'chiq.")
    else:
        match = _TIME_RE.match(arg)
        if not match:
            await message.answer("Vaqtni shunday yozing: /remind 21:00")
            return
        at = f"{int(match.group(1)):02d}:{match.group(2)}"
        store.set_reminder(uid, at)
        await message.answer(
            f"⏰ Tayyor: har kuni {at} da (Toshkent vaqti), agar o'sha kuni yozuv bo'lmasa eslataman."
        )


@router.message(Command("recurring"))
async def cmd_recurring(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id
    tokens = (command.args or "").split()
    if not tokens:
        rows = store.list_recurring(uid)
        if not rows:
            await message.answer("Doimiy xarajat yo'q.\n\n" + RECURRING_HELP)
            return
        lines = ["🔁 Doimiy xarajatlar", ""]
        lines += [f"#{r['id']}  {r['day']}-kuni  {fmt_money(r['amount'])} - {r['category']}" for r in rows]
        await message.answer("\n".join(lines) + "\n\nO'chirish: /recurring del <raqam>")
    elif tokens[0] == "add" and len(tokens) >= 3 and tokens[-1].isdigit():
        day = int(tokens[-1])
        parsed = parse_expense(" ".join(tokens[1:-1]))
        if parsed is None or not 1 <= day <= 28:
            await message.answer(RECURRING_HELP)
            return
        amount, category = parsed
        rid = store.add_recurring(uid, amount, category, day)
        start = "shu oydan" if day > db.now().day else "keyingi oydan"
        await message.answer(f"🔁 #{rid}: har oyning {day}-kuni {fmt_money(amount)} - {category} ({start} boshlanadi).")
    elif tokens[0] == "del" and len(tokens) == 2 and tokens[1].lstrip("#").isdigit():
        ok = store.delete_recurring(uid, int(tokens[1].lstrip("#")))
        await message.answer("O'chirildi." if ok else "Bunday yozuv topilmadi.")
    else:
        await message.answer(RECURRING_HELP)


async def _safe_send(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception:  # foydalanuvchi botni bloklagan bo'lishi mumkin
        logging.warning("Xabar yuborilmadi: %s", user_id)


async def run_jobs(bot: Bot) -> None:
    now = db.now()
    today = now.strftime("%Y-%m-%d")
    for uid in store.due_reminders(now.strftime("%H:%M"), today):
        store.mark_reminded(uid, today)
        if not store.has_entry_since(uid, today):
            await _safe_send(bot, uid, "⏰ Bugungi xarajatlaringizni kiritdingizmi? Masalan: 25000 tushlik")
    for r in store.due_recurring(now.date()):
        db.add_expense(r["user_id"], r["amount"], r["category"])
        store.mark_run(r["id"], now.strftime("%Y-%m"))
        await _safe_send(bot, r["user_id"], f"🔁 Doimiy xarajat qo'shildi: {fmt_money(r['amount'])} - {r['category']}")


async def scheduler(bot: Bot) -> None:
    while True:
        try:
            await run_jobs(bot)
        except Exception:
            logging.exception("Fon vazifasida xato")
        await asyncio.sleep(60)


@router.startup()
async def on_startup(bot: Bot) -> None:
    global _task
    store.init()
    await bot.set_my_commands(COMMANDS)
    _task = asyncio.create_task(scheduler(bot))


@router.shutdown()
async def on_shutdown() -> None:
    if _task:
        _task.cancel()

"""Admin paneli: foydalanuvchilarni kuzatish va statistika (faqat ADMIN_IDS uchun)."""
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Set

from aiogram import BaseMiddleware, Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import tracking

router = Router()
KIND_LABELS = {"text": "xarajat yozish", "app": "Mini App", "other": "boshqa"}


def admin_ids() -> Set[int]:
    raw = os.getenv("ADMIN_IDS", "").replace(" ", "")
    return {int(x) for x in raw.split(",") if x.isdigit()}


def is_admin(user_id: int) -> bool:
    return user_id in admin_ids()


def _who(user_id: int, username, name) -> str:
    return f"@{username}" if username else (name or str(user_id))


def _label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind.replace("cmd:", ""))


def _kind(message: Message) -> str:
    if message.web_app_data:
        return "app"
    if message.text:
        if message.text.startswith("/"):
            return "cmd:" + message.text.split()[0].split("@")[0].lower()
        return "text"
    return "other"


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in admin_ids():
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logging.warning("Adminga xabar yuborilmadi: %s", admin_id)


class TrackingMiddleware(BaseMiddleware):
    """Har bir xabarda foydalanuvchi va harakat turini yozib boradi (matnni emas)."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user and not user.is_bot:
            try:
                is_new = tracking.touch(user.id, user.username, user.full_name)
                tracking.log_event(user.id, _kind(event))
                if is_new and not is_admin(user.id):
                    who = _who(user.id, user.username, user.full_name)
                    await notify_admins(data["bot"], f"🆕 Yangi foydalanuvchi: {who} (id {user.id})")
            except Exception:
                logging.exception("Kuzatishda xato")
        return await handler(event, data)


async def _guard(message: Message) -> bool:
    if not admin_ids():
        await message.answer("ADMIN_IDS sozlanmagan. /id bilan ID'ingizni bilib, .env ga yozing.")
        return False
    return is_admin(message.from_user.id)  # admin bo'lmaganlarga jim turamiz


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Sizning Telegram ID'ingiz: {message.from_user.id}")


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not await _guard(message):
        return
    s = tracking.summary()
    lines = [
        "👥 Foydalanuvchilar: %d" % s["users"],
        "🆕 Bugun yangi: %d" % s["new_today"],
        "🟢 Bugun faol: %d  |  7 kunda: %d" % (s["active_today"], s["active_week"]),
        "⚡ Bugungi harakatlar: %d" % s["events_today"],
        "🧾 Jami yozuvlar: %d" % s["records"],
    ]
    if s["top"]:
        lines += ["", "Eng ko'p ishlatilgan (7 kun):"]
        lines += [f"• {_label(k)}: {n}" for k, n in s["top"]]
    lines += ["", "/users - oxirgi foydalanuvchilar", "/user <id> - bitta foydalanuvchi"]
    await message.answer("\n".join(lines))


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not await _guard(message):
        return
    rows = tracking.list_users(15)
    if not rows:
        await message.answer("Hali foydalanuvchi yo'q.")
        return
    lines = ["👥 Oxirgi faol foydalanuvchilar", ""]
    for i, r in enumerate(rows, 1):
        who = _who(r["user_id"], r["username"], r["name"])
        lines.append(
            f"{i}. {who} - oxirgi: {r['last_seen'][5:16]}, xabar: {r['msgs']}, "
            f"yozuv: {r['records']} (id {r['user_id']})"
        )
    await message.answer("\n".join(lines))


@router.message(Command("user"))
async def cmd_user(message: Message, command: CommandObject) -> None:
    if not await _guard(message):
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Masalan: /user 123456789")
        return
    d = tracking.user_detail(int(arg))
    if d is None:
        await message.answer("Bunday foydalanuvchi topilmadi.")
        return
    u = d["user"]
    lines = [
        f"👤 {_who(u['user_id'], u['username'], u['name'])} (id {u['user_id']})",
        f"Ism: {u['name']}",
        f"Birinchi kirgan: {u['first_seen'][:16]}",
        f"Oxirgi faollik: {u['last_seen'][:16]}",
        f"Xabarlar: {u['msgs']}  |  Yozuvlar: {d['records']}",
    ]
    if d["kinds"]:
        lines += ["", "Oxirgi 7 kunda:"]
        lines += [f"• {_label(k)}: {n}" for k, n in d["kinds"]]
    await message.answer("\n".join(lines))

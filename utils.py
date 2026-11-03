"""Yordamchi funksiyalar: xabarni tahlil qilish va pulni chiroyli ko'rsatish."""
import re
from typing import Optional, Tuple

# 25000 | 25 000 | 15k | 15 ming  (so'ng ixtiyoriy izoh)
_AMOUNT_RE = re.compile(
    r"(?<![\w])(\d{1,3}(?: \d{3})+|\d+)(?:\s*(k|ming))?(?=\s|$|[.,!?])",
    re.IGNORECASE,
)


def parse_expense(text: str) -> Optional[Tuple[int, str]]:
    """Xabardan (summa, kategoriya) ni ajratadi.

    Misollar:
        "25000 tushlik"  -> (25000, "tushlik")
        "taksi 15k"      -> (15000, "taksi")
        "120 ming kiyim" -> (120000, "kiyim")
        "50000"          -> (50000, "boshqa")
    Summa topilmasa yoki 0 bo'lsa None qaytaradi.
    """
    text = (text or "").strip()
    match = _AMOUNT_RE.search(text)
    if not match:
        return None

    amount = int(match.group(1).replace(" ", ""))
    if match.group(2):
        amount *= 1000
    if amount <= 0:
        return None

    rest = (text[: match.start()] + " " + text[match.end():]).strip()
    category = " ".join(rest.split()).lower() or "boshqa"
    return amount, category[:50]


def fmt_money(amount: int) -> str:
    """25000 -> '25 000 so'm'"""
    return f"{amount:,}".replace(",", " ") + " so'm"

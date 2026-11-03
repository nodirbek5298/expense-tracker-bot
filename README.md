# 💸 Xarajatlar hisobi Telegram boti

Talabalar va oilalar uchun oddiy bot: xabar yozasiz, bot xarajatni saqlaydi va kategoriyalar bo'yicha hisobot beradi.

## Imkoniyatlar
- Tez kiritish: `25000 tushlik`, `taksi 15k`, `120 ming kiyim`
- Hisobotlar: `/today`, `/week`, `/month` (kategoriyalar bo'yicha jami)
- `/last` - oxirgi yozuvlar, `/delete <raqam>` - xato yozuvni o'chirish
- `/reset ha` - barcha ma'lumotlarni o'chirish
- Har bir foydalanuvchining ma'lumoti alohida saqlanadi
- Vaqt Toshkent vaqti bo'yicha

## Ishga tushirish
1. Telegramda [@BotFather](https://t.me/BotFather) orqali bot yarating va tokenni oling.
2. Loyihani yuklab, kutubxonalarni o'rnating:
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. `.env.example` faylidan `.env` yarating va tokenni yozing:
   ```bash
   cp .env.example .env
   ```
4. Botni ishga tushiring:
   ```bash
   python bot.py
   ```

## Testlar
```bash
python -m unittest -v
```

## Texnologiyalar
Python 3, [aiogram 3](https://docs.aiogram.dev/), SQLite.

## Muallif
Nodirbek - Telegram: [@nodir691](https://t.me/nodir691)

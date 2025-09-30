#!/usr/bin/env python3
"""
Telegram Bot для SecureLink VPN на aiogram 3
Автоотправка конфига и QR после оплаты
"""
import os
import logging
import asyncio
from io import BytesIO
from datetime import datetime

import psycopg2
import requests
import qrcode

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
    FSInputFile, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command
from dotenv import load_dotenv

# -------------------- Загрузка .env --------------------
load_dotenv()

# -------------------- Конфигурация --------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://truesocial.ru/dashboard")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://app:9000")

PLANS_UI = {
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

INSTRUCTION_TEXT = (
    "Инструкция по подключению:\n"
    "1) Установите WireGuard (iOS/Android/macOS/Windows).\n"
    "2) Импортируйте присланный .conf файл.\n"
    "3) Включите соединение.\n"
    "Если возникнут вопросы — напишите в поддержку."
)

# -------------------- Логирование --------------------
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- Инициализация бота --------------------
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# -------------------- Работа с БД --------------------
def get_db_connection():
    try:
        return psycopg2.connect(
            dbname=os.environ.get("PG_DB", "securelink"),
            user=os.environ.get("PG_USER", "securelink"),
            password=os.environ.get("PG_PASSWORD"),
            host=os.environ.get("PG_HOST", "localhost"),
            port=os.environ.get("PG_PORT", 5432)
        )
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def create_user(telegram_id, username, first_name, last_name, language_code):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_id=%s", (telegram_id,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
        cur.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user_id,))
        conn.commit()
        conn.close()
        return user_id
    cur.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name, language_code, created_at, last_login)
        VALUES (%s,%s,%s,%s,%s,NOW(),NOW()) RETURNING id
        """,
        (telegram_id, username, first_name, last_name, language_code)
    )
    user_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return user_id

def get_latest_paid_order_by_email(email):
    if not email:
        return None
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, conf_file, plan
        FROM orders
        WHERE email=%s AND status='paid' AND conf_file IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (email,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "conf_file": row[1], "plan": row[2]}

async def send_order_to_user(email, telegram_id):
    order = get_latest_paid_order_by_email(email)
    if not order:
        logger.warning(f"No paid order found for email {email}")
        return
    try:
        # Отправка конфига
        doc = FSInputFile(order["conf_file"], filename=f"securelink_{order['id']}.conf")
        await bot.send_document(chat_id=telegram_id, document=doc,
                                caption=f"Тариф: {order['plan']}\n{INSTRUCTION_TEXT}")
        # Отправка QR
        with open(order["conf_file"], "r") as f:
            buf = BytesIO()
            qrcode.make(f.read()).save(buf, format="PNG")
            buf.seek(0)
            photo = BufferedInputFile(buf.read(), filename=f"securelink_{order['id']}.png")
            await bot.send_photo(chat_id=telegram_id, photo=photo,
                                 caption=f"QR для импорта конфига (тариф: {order['plan']})\n{INSTRUCTION_TEXT}")
    except Exception as e:
        logger.error(f"Failed to send config/QR to {telegram_id}: {e}")

# -------------------- Обработка контакта / платежа --------------------
@dp.message(lambda m: m.contact is not None)
async def handle_contact(message: types.Message):
    phone = message.contact.phone_number.strip()
    user_id = create_user(message.from_user.id, message.from_user.username,
                          message.from_user.first_name, message.from_user.last_name,
                          message.from_user.language_code)
    await message.delete()
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())

    try:
        # Связываем телефон с телеграмом
        requests.post(f"{BACKEND_URL}/bot/link-phone",
                      json={"phone": phone, "telegram_id": message.from_user.id}, timeout=10)
        # Создаём платёж
        resp = requests.post(f"{BACKEND_URL}/create-payment",
                             json={"email": phone, "plan_id": 1}, timeout=20)  # plan_id можно взять из state
        data = resp.json() if resp.ok else None
        url = data.get("confirmation_url") if data else None
        if url:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти к оплате", url=url)]])
            await message.answer("Перейдите по ссылке для оплаты:", reply_markup=kb)

        # Автоотправка конфига и QR после успешного платежа
        await send_order_to_user(phone, message.from_user.id)

    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await message.answer("Ошибка при создании платежа. Попробуйте позже.")

# -------------------- Запуск бота --------------------
async def main():
    logger.info("Starting SecureLink Telegram Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
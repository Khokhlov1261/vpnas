#!/usr/bin/env python3
"""
Простой Telegram Bot для SecureLink VPN на aiogram 3
"""
import os
import logging
import asyncio
import psycopg2
import secrets
from datetime import datetime
from io import BytesIO

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, FSInputFile, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from dotenv import load_dotenv
from services.orders import PLANS
import json
import requests
import qrcode

load_dotenv()  # загружает переменные из .env

# -------------------- Логирование --------------------
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# -------------------- Конфигурация --------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://truesocial.ru/dashboard")
BACKEND_URL = os.environ.get("BACKEND_URL", os.environ.get("WEB_BACKEND_URL", "http://app:9000"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Securelinkvpn_bot")

PLANS_UI = {
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

# -------------------- Работа с базой --------------------
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

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cursor.fetchone()

    if user:
        user_id = user[0]
        cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()
        return user_id

    cursor.execute("""
        INSERT INTO users (telegram_id, username, first_name, last_name, language_code, created_at, last_login)
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING id
    """, (telegram_id, username, first_name, last_name, language_code))
    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    logger.info(f"Created new user {user_id}")
    return user_id

def get_user_token(user_id):
    return None

# -------------------- Инициализация бота --------------------
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Простое хранение состояния оплаты (ожидаем контакт)
PAYMENT_STATE = {}

# -------------------- Клавиатуры --------------------
def main_keyboard(user_id):
    token = get_user_token(user_id)
    # Всегда ведёт на /dashboard
    url = f"{WEB_APP_URL}/dashboard"
    if token:
        url += f"?token={token}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="📊 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def plans_keyboard():
    keyboard = []
    for plan_id, plan in PLANS_UI.items():
        button_text = f"{plan['emoji']} {plan['name']} - {plan['price']} ₽"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"plan_{plan_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def plan_detail_keyboard(plan_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{plan_id}")],
        [InlineKeyboardButton(text="🔙 Назад к тарифам", callback_data="show_plans")]
    ])

# -------------------- Хэндлеры --------------------
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user = message.from_user
    user_id = create_user(user.id, user.username, user.first_name, user.last_name, user.language_code)
    welcome_text = f"""
🔒 <b>Добро пожаловать в SecureLink VPN!</b>

Привет, {user.first_name}! 👋

Выберите действие ниже:
"""
    await message.answer(welcome_text, reply_markup=main_keyboard(user_id))

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = f"""
🔒 <b>SecureLink VPN - Помощь</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/help - Эта справка
"""
    await message.answer(help_text)

@dp.callback_query(lambda c: c.data == "show_plans")
async def show_plans_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("💰 <b>Тарифы SecureLink VPN</b>\n\nВыберите тариф:", reply_markup=plans_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("plan_"))
async def plan_details(callback: types.CallbackQuery):
    plan_id = int(callback.data.split("_")[1])
    plan = PLANS_UI.get(plan_id)
    if not plan:
        await callback.answer("Неверный тариф", show_alert=True)
        return
    plan_text = f"""
{plan['emoji']} <b>{plan['name']}</b>

<b>Цена:</b> {plan['price']} ₽
<b>Срок:</b> {plan['days']} дней
<b>Трафик:</b> Безлимитный
<b>Серверы:</b> Все доступные
<b>Поддержка:</b> 24/7
"""
    await callback.message.edit_text(plan_text, reply_markup=plan_detail_keyboard(plan_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pay_"))
async def pay_plan(callback: types.CallbackQuery):
    plan_id = int(callback.data.split("_")[1])
    plan = PLANS_UI.get(plan_id)
    if not plan:
        await callback.answer("Неверный тариф", show_alert=True)
        return
    if plan['price'] == 0:
        await callback.message.edit_text(f"🎉 Бесплатный тариф '{plan['name']}' активирован!", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="show_plans")]]
        ))
        await callback.answer()
        return
    # Просим номер телефона через кнопку Поделиться номером
    PAYMENT_STATE[callback.from_user.id] = {"plan_id": plan_id, "awaiting_contact": True}
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer("Поделитесь вашим номером телефона для оформления оплаты:", reply_markup=kb)
    await callback.answer()

@dp.message()
async def catch_email_for_payment(message: types.Message):
    state = PAYMENT_STATE.get(message.from_user.id)
    if not state or not state.get("awaiting_email"):
        return
    email = (message.text or "").strip()
    if "@" not in email or "." not in email:
        await message.answer("Похоже на некорректный email. Попробуйте ещё раз или нажмите Назад.")
        return
    plan_id = state["plan_id"]
    # Вызываем backend для создания платежа
    try:
        # Линкуем email с telegram_id на бэкенде (для автодоставки после оплаты)
        try:
            requests.post(f"{BACKEND_URL}/bot/link-email", json={"email": email, "telegram_id": message.from_user.id}, timeout=10)
        except Exception as e:
            logger.warning(f"link-email failed: {e}")
        resp = requests.post(f"{BACKEND_URL}/create-payment", json={"email": email, "plan_id": plan_id}, timeout=15)
        data = resp.json() if resp.ok else None
        url = data.get("confirmation_url") if data else None
        if not url:
            raise RuntimeError(f"backend error: {resp.status_code} {resp.text}")
        # Показываем кнопку оплаты
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти к оплате", url=url)], [InlineKeyboardButton(text="🔙 Назад", callback_data="show_plans")]])
        await message.answer("Нажмите для оплаты:", reply_markup=kb)
        # Сохраним email для связи с telegram_id в заказе (после вебхука привяжем)
        state["awaiting_email"] = False
        state["email"] = email
    except Exception as e:
        logger.error(f"Payment create error: {e}")
        await message.answer("Не удалось создать платёж. Попробуйте позже.")

@dp.callback_query(lambda c: c.data == "my_account")
async def my_account(callback: types.CallbackQuery):
    user = callback.from_user
    user_id = create_user(user.id, user.username, user.first_name, user.last_name, user.language_code)
    token = get_user_token(user_id)
    # Всегда ведёт на /dashboard
    url = f"{WEB_APP_URL}/dashboard"
    if token:
        url += f"?token={token}"
    text = f"""
👤 <b>Мой аккаунт</b>

<b>Пользователь:</b> {user.full_name}
<b>Username:</b> @{user.username or 'не указан'}
<b>ID:</b> {user.id}

<b>Статус:</b> ✅ Активен
<b>Дата регистрации:</b> {datetime.now().strftime('%d.%m.%Y')}
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="📄 Получить конфиг", callback_data="get_config")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    user = callback.from_user
    user_id = create_user(user.id, user.username, user.first_name, user.last_name, user.language_code)
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard(user_id))
    await callback.answer()

# -------------------- Отправка конфига --------------------
def get_latest_paid_order_for_telegram(telegram_id):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, conf_file, plan, expires_at
        FROM orders
        WHERE telegram_id = %s AND status = 'paid' AND conf_file IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (telegram_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "conf_file": row[1],
        "plan": row[2],
        "expires_at": row[3]
    }

INSTRUCTION_TEXT = (
    "Инструкция по подключению:\n"
    "1) Установите WireGuard (iOS/Android/macOS/Windows).\n"
    "2) Импортируйте присланный .conf файл.\n"
    "3) Включите соединение.\n"
    "Если возникнут вопросы — напишите в поддержку."
)

@dp.callback_query(lambda c: c.data == "get_config")
async def send_config(callback: types.CallbackQuery):
    user = callback.from_user
    order = get_latest_paid_order_for_telegram(user.id)
    if not order or not order.get("conf_file"):
        await callback.answer("Оплаченных конфигов не найдено", show_alert=True)
        return
    conf_path = order["conf_file"]
    try:
        doc = FSInputFile(conf_path, filename=f"securelink_{order['id']}.conf")
        caption = f"Тариф: {order['plan']}\n" + INSTRUCTION_TEXT
        await bot.send_document(chat_id=user.id, document=doc, caption=caption)
        await callback.answer("Конфиг отправлен")
    except Exception as e:
        logger.error(f"Failed to send config: {e}")
        await callback.answer("Ошибка отправки конфига", show_alert=True)

@dp.callback_query(lambda c: c.data == "get_qr")
async def send_qr(callback: types.CallbackQuery):
    user = callback.from_user
    order = get_latest_paid_order_for_telegram(user.id)
    if not order or not order.get("conf_file"):
        await callback.answer("Оплаченных конфигов не найдено", show_alert=True)
        return
    conf_path = order["conf_file"]
    try:
        with open(conf_path, "r") as f:
            conf_text = f.read()
        buf = BytesIO()
        qrcode.make(conf_text).save(buf, format="PNG")
        buf.seek(0)
        photo = BufferedInputFile(buf.read(), filename=f"securelink_{order['id']}.png")
        caption = f"QR для импорта конфига (тариф: {order['plan']}).\n" + INSTRUCTION_TEXT
        await bot.send_photo(chat_id=user.id, photo=photo, caption=caption)
        await callback.answer("QR отправлен")
    except Exception as e:
        logger.error(f"Failed to send qr: {e}")
        await callback.answer("Ошибка отправки QR", show_alert=True)

# -------------------- Запуск бота --------------------
async def main():
    logger.info("Starting SecureLink Telegram Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())#
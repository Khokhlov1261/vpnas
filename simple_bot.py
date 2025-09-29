#BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"




#!/usr/bin/env python3
"""
SecureLink VPN Telegram Bot (aiogram 3) с WebApp токеном
"""
import os
import logging
import asyncio
import psycopg2
import secrets
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()  # Загружает переменные из .env

# -------------------- Настройка логирования --------------------
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# -------------------- Конфигурация --------------------
BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://truesocial.ru")

# Тарифы
PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

# -------------------- Работа с БД --------------------
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("PG_DB", "securelink_db"),
            user=os.environ.get("PG_USER", "securelink"),
            password=os.environ.get("PG_PASSWORD"),
            host=os.environ.get("PG_HOST", "localhost"),
            port=os.environ.get("PG_PORT", 5432)
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def create_user(telegram_id, username, first_name, last_name, language_code):
    try:
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            cursor.execute("UPDATE users SET last_login = NOW() WHERE telegram_id = %s", (telegram_id,))
            conn.commit()
            conn.close()
            return existing_user[0]
        cursor.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, language_code, created_at, last_login)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
        """, (telegram_id, username, first_name, last_name, language_code))
        user_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        logger.info(f"Created new user: {user_id} (telegram_id: {telegram_id})")
        return user_id
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return None

# -------------------- Генерация токена для WebApp --------------------
def generate_dashboard_token(telegram_id):
    token = secrets.token_urlsafe(16)
    expires_at = datetime.now() + timedelta(minutes=10)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO dashboard_tokens (telegram_id, token, expires_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE
        SET token = EXCLUDED.token, expires_at = EXCLUDED.expires_at
    """, (telegram_id, token, expires_at))
    conn.commit()
    conn.close()
    return token

# -------------------- Инициализация бота --------------------
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# -------------------- Клавиатуры --------------------
def main_keyboard(user_id=None):
    buttons = [
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="📊 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard" if not user_id else f"{WEB_APP_URL}/dashboard?token={generate_dashboard_token(user_id)}")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def plans_keyboard(user_id):
    keyboard = []
    for plan_id, plan in PLANS.items():
        keyboard.append([InlineKeyboardButton(text=f"{plan['emoji']} {plan['name']} - {plan['price']} ₽", callback_data=f"plan_{plan_id}")])
    keyboard.append([InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard?token={generate_dashboard_token(user_id)}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start")])
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
    create_user(user.id, user.username, user.first_name, user.last_name, user.language_code)
    welcome_text = f"""
🔒 <b>Добро пожаловать в SecureLink VPN!</b>

Привет, {user.first_name}! 👋

Я помогу вам подключиться к нашему быстрому и безопасному VPN с протоколом WireGuard.

<b>Что я умею:</b>
• 🚀 Подключить к VPN за 30 секунд
• 💳 Принять оплату через YooKassa
• 📱 Отправить конфигурацию и QR-код
• 📊 Показать статистику использования
• 🔧 Управлять подписками

<b>Выберите действие:</b>
"""
    await message.answer(welcome_text, reply_markup=main_keyboard(user.id))

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        f"🔒 <b>SecureLink VPN - Помощь</b>\n\n"
        "/start - Начать работу с ботом\n"
        "/plans - Показать тарифы\n"
        "/account - Мой аккаунт\n"
        "/help - Эта справка\n\n"
        f"Для управления подписками используйте личный кабинет: {WEB_APP_URL}/dashboard",
        reply_markup=main_keyboard()
    )

@dp.callback_query(lambda c: c.data == "show_plans")
async def show_plans_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💰 <b>Тарифы SecureLink VPN</b>\n\nВыберите подходящий тариф:",
        reply_markup=plans_keyboard(callback.from_user.id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("plan_"))
async def plan_details(callback: types.CallbackQuery):
    plan_id = int(callback.data.split("_")[1])
    plan = PLANS.get(plan_id)
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

<b>Что включено:</b>
✅ Протокол WireGuard
✅ Неограниченный трафик
✅ Все серверы
✅ Техническая поддержка
✅ Автоматическое продление
✅ QR-код для быстрой установки
"""
    await callback.message.edit_text(plan_text, reply_markup=plan_detail_keyboard(plan_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pay_"))
async def create_payment(callback: types.CallbackQuery):
    plan_id = int(callback.data.split("_")[1])
    plan = PLANS.get(plan_id)
    if not plan:
        await callback.answer("Неверный тариф", show_alert=True)
        return
    if plan['price'] == 0:
        text = "🎉 <b>Бесплатный тариф активирован!</b>\n\nВаш VPN готов к использованию на 3 дня."
    else:
        text = f"💳 Оплата тарифа {plan['name']}\n<b>Сумма:</b> {plan['price']} ₽\n<b>Срок:</b> {plan['days']} дней\n\nПерейдите в личный кабинет для оплаты: {WEB_APP_URL}/dashboard?token={generate_dashboard_token(callback.from_user.id)}"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="show_plans")]
    ]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "my_account")
async def my_account(callback: types.CallbackQuery):
    user = callback.from_user
    text = f"""
👤 <b>Мой аккаунт</b>

<b>Пользователь:</b> {user.full_name}
<b>Username:</b> @{user.username or 'не указан'}
<b>ID:</b> {user.id}

<b>Статус:</b> ✅ Активен
<b>Дата регистрации:</b> {datetime.now().strftime('%d.%m.%Y')}
"""
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard?token={generate_dashboard_token(user.id)}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ]))
    await callback.answer()

# -------------------- Запуск бота --------------------
async def main():
    logger.info("Starting SecureLink Telegram Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
Простой Telegram Bot для SecureLink VPN на aiogram 3
"""
import os
import logging
import asyncio
import psycopg2
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()  # загружает переменные из .env в os.environ

# Настройка логирования
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://147.45.117.195:9000")

# Тарифы
PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

# -------------------- Работа с базой --------------------
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

# -------------------- Инициализация бота --------------------
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# -------------------- Клавиатуры --------------------
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="📊 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def get_plans_keyboard():
    keyboard = []
    for plan_id, plan in PLANS.items():
        button_text = f"{plan['emoji']} {plan['name']} - {plan['price']} ₽"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"plan_{plan_id}")])
    keyboard.append([InlineKeyboardButton(text="🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = f"""
🔒 <b>SecureLink VPN - Помощь</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/plans - Показать тарифы
/account - Мой аккаунт
/help - Эта справка

<b>Для управления подписками используйте личный кабинет:</b>
🚀 Личный кабинет: {WEB_APP_URL}/dashboard
    """
    await message.answer(help_text)

@dp.callback_query(lambda c: c.data == "show_plans")
async def show_plans_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💰 <b>Тарифы SecureLink VPN</b>\n\nВыберите подходящий тариф:",
        reply_markup=get_plans_keyboard()
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{plan_id}")],
        [InlineKeyboardButton(text="🔙 Назад к тарифам", callback_data="show_plans")]
    ])
    await callback.message.edit_text(plan_text, reply_markup=keyboard)
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
        text = f"💳 Оплата тарифа {plan['name']}\n<b>Сумма:</b> {plan['price']} ₽\n<b>Срок:</b> {plan['days']} дней\n\nДля оплаты перейдите в личный кабинет: {WEB_APP_URL}/dashboard"

    await callback.message.edit_text(text)
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# -------------------- Запуск бота --------------------
async def main():
    logger.info("Starting SecureLink Telegram Bot (aiogram 3)...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
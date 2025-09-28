#!/usr/bin/env python3
import os
import logging
import psycopg2
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.dispatcher.router import Router

# ----------------- Настройка -----------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://147.45.117.195:9000")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://alexanderkhokhlov@localhost/securelink")

PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

# ----------------- БД -----------------
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        return None

def create_user(user: types.User):
    try:
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user.id,))
        existing_user = cursor.fetchone()
        if existing_user:
            cursor.execute("UPDATE users SET last_login = NOW() WHERE telegram_id = %s", (user.id,))
            conn.commit()
            conn.close()
            return existing_user[0]
        cursor.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, language_code, created_at, last_login)
            VALUES (%s,%s,%s,%s,%s,NOW(),NOW()) RETURNING id
        """, (user.id, user.username, user.first_name, user.last_name, user.language_code))
        user_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        logging.info(f"Created new user: {user_id}")
        return user_id
    except Exception as e:
        logging.error(f"Error creating user: {e}")
        return None

# ----------------- Бот -----------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ----------------- Команды -----------------
@router.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    create_user(message.from_user)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="📊 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    await message.answer(
        f"🔒 <b>Добро пожаловать в SecureLink VPN!</b>\n\nПривет, {message.from_user.first_name}! 👋\n\n<b>Выберите действие:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(Command(commands=["help"]))
async def help_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]
    ])
    await message.answer(
        "🔒 <b>SecureLink VPN - Помощь</b>\n\n<b>Основные команды:</b>\n/start, /plans, /account, /help",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(Command(commands=["plans"]))
async def plans_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{plan['emoji']} {plan['name']} - {plan['price']} ₽", callback_data=f"plan_{pid}")]
            for pid, plan in PLANS.items()
        ] + [[InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]]
    )
    await message.answer(
        "💰 <b>Тарифы SecureLink VPN</b>\nВыберите тариф:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(Command(commands=["account"]))
async def account_command(message: types.Message):
    user = message.from_user
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]
    ])
    await message.answer(
        f"👤 <b>Мой аккаунт</b>\n<b>Пользователь:</b> {user.first_name} {user.last_name or ''}\n<b>Username:</b> @{user.username or 'не указан'}\n<b>ID:</b> {user.id}",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ----------------- Callback -----------------
@router.callback_query()
async def callback_handler(query: types.CallbackQuery):
    await query.answer()
    data = query.data

    if data == "show_plans":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"{plan['emoji']} {plan['name']} - {plan['price']} ₽", callback_data=f"plan_{pid}")]
                for pid, plan in PLANS.items()
            ] + [[InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]]
        )
        await query.message.edit_text("💰 <b>Тарифы SecureLink VPN</b>\nВыберите тариф:", parse_mode="HTML", reply_markup=keyboard)

    elif data.startswith("plan_"):
        plan_id = int(data.split("_")[1])
        plan = PLANS.get(plan_id)
        if plan:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{plan_id}")],
                [InlineKeyboardButton(text="🔙 Назад к тарифам", callback_data="show_plans")]
            ])
            await query.message.edit_text(
                f"{plan['emoji']} <b>{plan['name']}</b>\n<b>Цена:</b> {plan['price']} ₽\n<b>Срок:</b> {plan['days']} дней",
                parse_mode="HTML",
                reply_markup=keyboard
            )

    elif data.startswith("pay_"):
        plan_id = int(data.split("_")[1])
        plan = PLANS.get(plan_id)
        if plan:
            text = "🎉 Бесплатный тариф активирован!" if plan['price'] == 0 else f"💳 Оплата тарифа {plan['name']} за {plan['price']} ₽"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="show_plans")]
            ])
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data == "my_account":
        user = query.from_user
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
            [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")]
        ])
        await query.message.edit_text(
            f"👤 <b>Мой аккаунт</b>\n<b>Пользователь:</b> {user.first_name} {user.last_name or ''}\n<b>Username:</b> @{user.username or 'не указан'}\n<b>ID:</b> {user.id}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    elif data == "show_stats":
        user = query.from_user
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="my_account")]
        ])
        await query.message.edit_text(
            f"📊 <b>Статистика</b>\n<b>Пользователь:</b> {user.first_name}\nТрафик: 0 MB",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    elif data == "help":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Тарифы", callback_data="show_plans")],
            [InlineKeyboardButton(text="🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]
        ])
        await query.message.edit_text(
            "🔒 <b>Помощь SecureLink VPN</b>\nОсновные команды: /start, /plans, /account",
            parse_mode="HTML",
            reply_markup=keyboard
        )

# ----------------- Запуск -----------------
if __name__ == "__main__":
    import asyncio
    logging.info("Bot started...")
    asyncio.run(dp.start_polling(bot))
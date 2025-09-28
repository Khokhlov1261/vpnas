#!/usr/bin/env python3
import os
import logging
import psycopg2
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# Загрузка .env
load_dotenv()

# Логирование
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://147.45.117.195:9000")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://alexanderkhokhlov@localhost/securelink")

# Тарифы
PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
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
            VALUES (%s,%s,%s,%s,%s,NOW(),NOW()) RETURNING id
        """, (telegram_id, username, first_name, last_name, language_code))
        user_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        logger.info(f"Created new user: {user_id}")
        return user_id
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return None

# ------------------- Команды -------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name, user.language_code)

    welcome_text = f"""
🔒 <b>Добро пожаловать в SecureLink VPN!</b>

Привет, {user.first_name}! 👋

<b>Выберите действие:</b>
"""
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("📊 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML,
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🔒 <b>SecureLink VPN - Помощь</b>

<b>Основные команды:</b>
/start, /plans, /account, /help
"""
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]
    ]
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML,
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_plans_callback(update, context)

async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_account_callback(update, context)

# ------------------- Callback -------------------
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "show_plans":
        await show_plans_callback(update, context)
    elif data == "my_account":
        await show_account_callback(update, context)
    elif data == "help":
        await help_callback(update, context)
    elif data.startswith("plan_"):
        plan_id = int(data.split("_")[1])
        await show_plan_details_callback(update, context, plan_id)
    elif data.startswith("pay_"):
        plan_id = int(data.split("_")[1])
        await create_payment_callback(update, context, plan_id)
    elif data == "show_stats":
        await show_stats_callback(update, context)

# ------------------- Callback Handlers -------------------
async def show_plans_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💰 <b>Тарифы SecureLink VPN</b>\nВыберите тариф:"
    keyboard = [
        [InlineKeyboardButton(f"{plan['emoji']} {plan['name']} - {plan['price']} ₽",
                              callback_data=f"plan_{pid}")]
        for pid, plan in PLANS.items()
    ]
    keyboard.append([InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def show_plan_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
    query = update.callback_query
    plan = PLANS.get(plan_id)
    if not plan:
        return
    text = f"""
{plan['emoji']} <b>{plan['name']}</b>
<b>Цена:</b> {plan['price']} ₽
<b>Срок:</b> {plan['days']} дней
<b>Трафик:</b> Безлимитный
<b>Серверы:</b> Все
<b>Поддержка:</b> 24/7
"""
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{plan_id}")],
        [InlineKeyboardButton("🔙 Назад к тарифам", callback_data="show_plans")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def create_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
    query = update.callback_query
    plan = PLANS.get(plan_id)
    if not plan:
        await query.edit_message_text("❌ Неверный тариф")
        return
    if plan['price'] == 0:
        text = "🎉 Бесплатный тариф активирован! Используйте личный кабинет для конфигурации."
    else:
        text = f"💳 Оплата тарифа {plan['name']}, сумма: {plan['price']} ₽\nПерейдите в личный кабинет для оплаты."
    keyboard = [
        [InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
        [InlineKeyboardButton("🔙 Назад", callback_data="show_plans")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def show_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    text = f"""
👤 <b>Мой аккаунт</b>
<b>Пользователь:</b> {user.first_name} {user.last_name or ''}
<b>Username:</b> @{user.username or 'не указан'}
<b>ID:</b> {user.id}
"""
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
        [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def show_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    text = f"📊 <b>Статистика</b>\n<b>Пользователь:</b> {user.first_name}\nТрафик: 0 MB"
    keyboard = [
        [InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_account")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = "🔒 <b>Помощь SecureLink VPN</b>\nОсновные команды: /start, /plans, /account"
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("🚀 Личный кабинет", url=f"{WEB_APP_URL}/dashboard")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}")

# ------------------- Main -------------------
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("plans", plans_command))
    app.add_handler(CommandHandler("account", account_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_error_handler(error_handler)
    logger.info("Bot started...")
    app.run_polling()
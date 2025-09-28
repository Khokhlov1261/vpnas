#!/usr/bin/env python3
"""
Простой Telegram Bot для SecureLink VPN
(исправленный вариант — подключается из .env как App.py)
"""
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

import psycopg2
from psycopg2 import sql

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# --- load .env ---
load_dotenv()

# --- logging ---
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- config (from .env) ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("BOT_TOKEN", "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"))
WEB_APP_URL = os.getenv("WEB_APP_URL", os.getenv("APP_URL", "https://127.0.0.1:9000"))

# Database config: prefer DATABASE_URL, else use PG_* vars (same style as App.py)
DATABASE_URL = os.getenv("DATABASE_URL")
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", os.getenv("PG_DB", "securelink_db"))
PG_USER = os.getenv("PG_USER", os.getenv("PG_USER", "securelink"))
PG_PASSWORD = os.getenv("PG_PASSWORD", os.getenv("PG_PASSWORD", ""))

# Plans
PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

def build_conninfo():
    """Собираем строку подключения так же как в App.py"""
    if DATABASE_URL:
        return DATABASE_URL
    # psycopg2 accepts DSN like: host=.. port=.. dbname=.. user=.. password=..
    return f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} user={PG_USER} password={PG_PASSWORD}"

CONNINFO = build_conninfo()

def get_db_connection():
    """Получение соединения к Postgres — возвращает psycopg2 connection или None"""
    try:
        conn = psycopg2.connect(CONNINFO)
        return conn
    except Exception as e:
        logger.error("Database connection error: %s", e)
        return None

def ensure_users_table():
    """Опционально: поможет создать простую таблицу users если её нет (без разрушения)"""
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    created_at TIMESTAMP WITH TIME ZONE,
                    last_login TIMESTAMP WITH TIME ZONE
                );
                """)
        logger.info("Ensured users table exists")
    except Exception as e:
        logger.exception("Failed to ensure users table: %s", e)
    finally:
        conn.close()

def create_user(telegram_id, username, first_name, last_name, language_code):
    """Создание/обновление пользователя в БД, возвращает id пользователя или None"""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
                row = cur.fetchone()
                if row:
                    user_id = row[0]
                    cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))
                    return user_id
                cur.execute(
                    "INSERT INTO users (telegram_id, username, first_name, last_name, language_code, created_at, last_login) "
                    "VALUES (%s, %s, %s, %s, %s, NOW(), NOW()) RETURNING id",
                    (telegram_id, username, first_name, last_name, language_code)
                )
                user_id = cur.fetchone()[0]
                return user_id
    except Exception as e:
        logger.exception("Error creating user: %s", e)
        return None
    finally:
        conn.close()

def make_dashboard_button(path="/dashboard"):
    """Возвращает InlineKeyboardButton: если WEB_APP_URL HTTPS -> WebAppInfo, иначе обычная url-кнопка"""
    url_full = WEB_APP_URL.rstrip("/") + path
    if url_full.startswith("https://"):
        return InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=url_full))
    else:
        # Telegram требует https для web_app; для локалки используем обычную url кнопку (откроется в браузере)
        return InlineKeyboardButton("🚀 Личный кабинет", url=url_full)

# --- Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code
    )
    if not user_id:
        await update.message.reply_text("❌ Ошибка инициализации. Попробуйте позже.")
        return

    welcome_text = f"""
🔒 <b>Добро пожаловать в SecureLink VPN!</b>

Привет, {user.first_name or 'пользователь'}! 👋

Выберите действие:
    """
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("📊 Мой аккаунт", callback_data="my_account"), make_dashboard_button("/dashboard")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔒 <b>SecureLink VPN - Помощь</b>\n\n"
        "/start - Начать\n"
        "/plans - Показать тарифы\n"
        "/account - Мой аккаунт\n"
    )
    keyboard = [[InlineKeyboardButton("💰 Тарифы", callback_data="show_plans"), make_dashboard_button("/dashboard")]]
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_plans(update, context)

async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_account(update, context)

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans_text = "💰 <b>Тарифы SecureLink VPN</b>\n\nВыберите тариф:"
    keyboard = []
    for plan_id, plan in PLANS.items():
        button_text = f"{plan['emoji']} {plan['name']} - {plan['price']} ₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"plan_{plan_id}")])
    keyboard.append([make_dashboard_button("/dashboard")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(plans_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(plans_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def show_plan_details(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
    plan = PLANS.get(plan_id)
    if not plan:
        return
    text = (
        f"{plan['emoji']} <b>{plan['name']}</b>\n\n"
        f"<b>Цена:</b> {plan['price']} ₽\n"
        f"<b>Срок:</b> {plan['days']} дней\n\n"
        "Готовы подключиться?"
    )
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{plan_id}")],
        [InlineKeyboardButton("🔙 Назад к тарифам", callback_data="show_plans")]
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👤 <b>Мой аккаунт</b>\n\n"
        f"<b>Пользователь:</b> {user.first_name} {user.last_name or ''}\n"
        f"<b>Username:</b> @{user.username or '—'}\n"
        f"<b>ID:</b> {user.id}\n"
    )
    keyboard = [[InlineKeyboardButton("💰 Тарифы", callback_data="show_plans"), make_dashboard_button("/dashboard")]]
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📊 Статистика: (пока пусто в демо)"
    await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="my_account")]]))

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "show_plans":
        await show_plans(update, context)
    elif data == "my_account":
        await show_account(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data.startswith("plan_"):
        plan_id = int(data.split("_", 1)[1])
        await show_plan_details(update, context, plan_id)
    elif data.startswith("pay_"):
        plan_id = int(data.split("_", 1)[1])
        # Для демонстрации — просто показать сообщение об оплате
        await query.edit_message_text(f"Платеж для тарифа {PLANS.get(plan_id, {}).get('name', '')} — откройте личный кабинет для оплаты.", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[make_dashboard_button("/dashboard")]]))
    elif data == "show_stats":
        await show_stats(update, context)
    else:
        # fallback
        logger.info("Unknown callback data: %s", data)
        await query.edit_message_text("Действие не распознано. Попробуйте команду /help")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Update %s caused error %s", update, context.error)

# --- bootstrapping & run ---
def main():
    # ensure users table (optional)
    ensure_users_table()

    application = Application.builder().token(BOT_TOKEN).build()

    # handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("account", account_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_error_handler(error_handler)

    # run polling (close_loop=False чтобы не пытаться закрывать loop в окружениях где уже запущен loop)
    logger.info("Starting SecureLink Telegram Bot...")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
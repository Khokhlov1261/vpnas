#!/usr/bin/env python3
"""
Простой Telegram Bot для SecureLink VPN
"""
import os
import sys
import json
import logging
import asyncio
import psycopg2
from datetime import datetime

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"
WEB_APP_URL = "http://127.0.0.1:9000"

# Тарифы
PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

def get_db_connection():
    """Получение соединения с базой данных"""
    try:
        conninfo = os.environ.get("DATABASE_URL", "postgresql://alexanderkhokhlov@localhost/securelink")
        return psycopg2.connect(conninfo)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def create_user(telegram_id, username, first_name, last_name, language_code):
    """Создание пользователя в базе данных"""
    try:
        conn = get_db_connection()
        if not conn:
            return None
            
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            # Обновляем last_login
            cursor.execute("UPDATE users SET last_login = NOW() WHERE telegram_id = %s", (telegram_id,))
            conn.commit()
            conn.close()
            return existing_user[0]
        
        # Создаем нового пользователя
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    
    # Создаем пользователя в БД
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
    
    # Приветственное сообщение
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
    
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("📊 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /help"""
    help_text = """
🔒 <b>SecureLink VPN - Помощь</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/plans - Показать тарифы
/account - Мой аккаунт
/help - Эта справка

<b>Как подключиться:</b>
1️⃣ Выберите тариф
2️⃣ Оплатите подписку
3️⃣ Получите конфигурацию
4️⃣ Установите WireGuard
5️⃣ Наслаждайтесь быстрым VPN!

<b>Поддержка:</b>
📧 mailrealeden@yahoo.com
🤖 Этот бот

<b>Протокол:</b> WireGuard
<b>Шифрование:</b> ChaCha20, Poly1305, Curve25519
    """
    
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /plans"""
    await show_plans(update, context)

async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /account"""
    await show_account(update, context)

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    plans_text = """
💰 <b>Тарифы SecureLink VPN</b>

Выберите подходящий тариф:
    """
    
    keyboard = []
    for plan_id, plan in PLANS.items():
        if plan_id == 9:  # Бесплатный тариф
            button_text = f"{plan['emoji']} {plan['name']} - {plan['price']} ₽"
        else:
            button_text = f"{plan['emoji']} {plan['name']} - {plan['price']} ₽"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"plan_{plan_id}")])
    
    keyboard.append([InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            plans_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            plans_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def show_plan_details(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
    """Показать детали тарифа"""
    if plan_id not in PLANS:
        return
    
    plan = PLANS[plan_id]
    
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

<b>Готовы подключиться?</b>
    """
    
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{plan_id}")],
        [InlineKeyboardButton("🔙 Назад к тарифам", callback_data="show_plans")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            plan_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            plan_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию об аккаунте"""
    user = update.effective_user
    
    account_text = f"""
👤 <b>Мой аккаунт</b>

<b>Пользователь:</b> {user.first_name} {user.last_name or ''}
<b>Username:</b> @{user.username or 'не указан'}
<b>ID:</b> {user.id}

<b>Статус:</b> ✅ Активен
<b>Дата регистрации:</b> {datetime.now().strftime('%d.%m.%Y')}

<b>Для управления подписками используйте личный кабинет:</b>
    """
    
    keyboard = [
        [InlineKeyboardButton("💰 Тарифы", callback_data="show_plans")],
        [InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))],
        [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            account_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            account_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    user = update.effective_user
    
    stats_text = f"""
📊 <b>Статистика использования</b>

<b>Пользователь:</b> {user.first_name}
<b>Дата регистрации:</b> {datetime.now().strftime('%d.%m.%Y')}

<b>Трафик за месяц:</b>
• 📥 Скачано: 0 MB
• 📤 Загружено: 0 MB
• 📊 Всего: 0 MB

<b>Активные сессии:</b> 0

<b>Для детальной статистики используйте личный кабинет:</b>
    """
    
    keyboard = [
        [InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_account")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        stats_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "show_plans":
        await show_plans(update, context)
    elif data == "my_account":
        await show_account(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data.startswith("plan_"):
        plan_id = int(data.split("_")[1])
        await show_plan_details(update, context, plan_id)
    elif data.startswith("pay_"):
        plan_id = int(data.split("_")[1])
        await create_payment(update, context, plan_id)
    elif data == "show_stats":
        await show_stats(update, context)

async def create_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
    """Создание платежа"""
    if plan_id not in PLANS:
        await update.callback_query.reply_text("❌ Неверный тариф")
        return
    
    plan = PLANS[plan_id]
    
    if plan['price'] == 0:
        # Бесплатный тариф
        await update.callback_query.edit_message_text(
            "🎉 <b>Бесплатный тариф активирован!</b>\n\n"
            "Ваш VPN готов к использованию на 3 дня.\n"
            "Используйте личный кабинет для получения конфигурации.",
            parse_mode=ParseMode.HTML
        )
    else:
        # Платный тариф
        payment_text = f"""
💳 <b>Оплата тарифа "{plan['name']}"</b>

<b>Сумма:</b> {plan['price']} ₽
<b>Срок:</b> {plan['days']} дней

<b>Способы оплаты:</b>
• 💳 Банковская карта
• 📱 СБП (Система быстрых платежей)
• 🏦 Банковский перевод

<b>Для оплаты перейдите в личный кабинет:</b>
        """
        
        keyboard = [
            [InlineKeyboardButton("🚀 Личный кабинет", web_app=WebAppInfo(url=f"{WEB_APP_URL}/dashboard"))],
            [InlineKeyboardButton("🔙 Назад", callback_data="show_plans")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            payment_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Update {update} caused error {context.error}")

async def main():
    """Главная функция"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("account", account_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Starting SecureLink Telegram Bot...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

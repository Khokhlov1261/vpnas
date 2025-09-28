#!/usr/bin/env python3
"""
Telegram Bot для SecureLink VPN
Полнофункциональный бот с управлением подписками, платежами и конфигурациями
"""

import os
import sys
import json
import logging
import asyncio
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Импортируем наши модули
from user_manager import UserManager
from App import create_order_internal, get_conn

# Настройка логирования
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://a2c4260d9b8d.ngrok-free.app")
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY")

# Тарифы
PLANS = {
    9: {"name": "3 дня", "price": 0, "days": 3, "emoji": "🆓"},
    1: {"name": "1 месяц", "price": 99, "days": 30, "emoji": "📅"},
    2: {"name": "6 месяцев", "price": 499, "days": 180, "emoji": "📆"},
    3: {"name": "12 месяцев", "price": 999, "days": 365, "emoji": "🗓️"}
}

class SecureLinkBot:
    def __init__(self):
        self.application = None
        self.user_manager = None
        
    def init_db(self):
        """Инициализация подключения к базе данных"""
        try:
            conninfo = os.environ.get("DATABASE_URL", "postgresql://alexanderkhokhlov@localhost/securelink")
            self.user_manager = UserManager(lambda: psycopg2.connect(conninfo))
            logger.info("Database connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Получаем параметр из команды (например, /start plan_1)
        args = context.args
        selected_plan = None
        
        if args and args[0].startswith('plan_'):
            try:
                selected_plan = int(args[0].split('_')[1])
            except (ValueError, IndexError):
                pass
        
        # Создаем или получаем пользователя
        try:
            user_data = self.user_manager.get_or_create_telegram_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code
            )
            logger.info(f"User {user.id} ({user.username}) started bot")
        except Exception as e:
            logger.error(f"Error creating user: {e}")
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
        
        # Если выбран план, показываем его
        if selected_plan and selected_plan in PLANS:
            await self.show_plan_details(update, context, selected_plan)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    async def plans_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /plans"""
        await self.show_plans(update, context)
    
    async def account_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /account"""
        await self.show_account(update, context)
    
    async def show_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    async def show_plan_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
        """Показать детали тарифа"""
        if plan_id not in PLANS:
            return
        
        plan = PLANS[plan_id]
        user = update.effective_user
        
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
    
    async def show_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию об аккаунте"""
        user = update.effective_user
        
        try:
            # Получаем данные пользователя
            user_data = self.user_manager.get_user_by_telegram_id(user.id)
            if not user_data:
                await update.message.reply_text("❌ Пользователь не найден. Используйте /start")
                return
            
            # Получаем подписки
            subscriptions = self.user_manager.get_user_subscriptions(user_data['id'])
            
            account_text = f"""
👤 <b>Мой аккаунт</b>

<b>Пользователь:</b> {user.first_name} {user.last_name or ''}
<b>Username:</b> @{user.username or 'не указан'}
<b>ID:</b> {user.id}

<b>Активные подписки:</b>
            """
            
            if subscriptions:
                for sub in subscriptions:
                    status_emoji = "✅" if sub['status'] == 'active' else "❌"
                    account_text += f"\n{status_emoji} {sub['plan']} - до {sub['expires_at']}"
            else:
                account_text += "\n❌ Нет активных подписок"
            
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
                
        except Exception as e:
            logger.error(f"Error showing account: {e}")
            await update.message.reply_text("❌ Ошибка получения данных аккаунта")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "show_plans":
            await self.show_plans(update, context)
        elif data == "my_account":
            await self.show_account(update, context)
        elif data == "help":
            await self.help_command(update, context)
        elif data.startswith("plan_"):
            plan_id = int(data.split("_")[1])
            await self.show_plan_details(update, context, plan_id)
        elif data.startswith("pay_"):
            plan_id = int(data.split("_")[1])
            await self.create_payment(update, context, plan_id)
        elif data == "show_stats":
            await self.show_stats(update, context)
    
    async def create_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
        """Создание платежа"""
        if plan_id not in PLANS:
            await update.callback_query.reply_text("❌ Неверный тариф")
            return
        
        plan = PLANS[plan_id]
        user = update.effective_user
        
        try:
            # Создаем заказ
            order = create_order_internal(
                email=f"{user.id}@telegram.user",
                plan_id=plan_id,
                user_id=None,  # Будет установлен после создания пользователя
                telegram_id=user.id
            )
            
            if plan['price'] == 0:
                # Бесплатный тариф - сразу активируем
                await self.activate_free_plan(update, context, order)
            else:
                # Платный тариф - создаем платеж
                await self.create_yookassa_payment(update, context, order, plan)
                
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            await update.callback_query.reply_text("❌ Ошибка создания заказа. Попробуйте позже.")
    
    async def activate_free_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order):
        """Активация бесплатного тарифа"""
        try:
            # Здесь должна быть логика активации бесплатного тарифа
            # Пока что просто показываем сообщение
            await update.callback_query.edit_message_text(
                "🎉 <b>Бесплатный тариф активирован!</b>\n\n"
                "Ваш VPN готов к использованию на 3 дня.\n"
                "Используйте личный кабинет для получения конфигурации.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error activating free plan: {e}")
    
    async def create_yookassa_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order, plan):
        """Создание платежа через YooKassa"""
        try:
            # Здесь должна быть интеграция с YooKassa
            # Пока что показываем заглушку
            payment_text = f"""
💳 <b>Оплата тарифа "{plan['name']}"</b>

<b>Сумма:</b> {plan['price']} ₽
<b>Заказ:</b> #{order['id']}

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
            
        except Exception as e:
            logger.error(f"Error creating YooKassa payment: {e}")
    
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        user = update.effective_user
        
        try:
            user_data = self.user_manager.get_user_by_telegram_id(user.id)
            if not user_data:
                await update.callback_query.reply_text("❌ Пользователь не найден")
                return
            
            # Получаем статистику трафика
            traffic_stats = self.user_manager.get_user_traffic_stats(user_data['id'])
            
            stats_text = f"""
📊 <b>Статистика использования</b>

<b>Пользователь:</b> {user.first_name}
<b>Дата регистрации:</b> {user_data['created_at']}

<b>Трафик за месяц:</b>
• 📥 Скачано: {traffic_stats.get('download', 0)} MB
• 📤 Загружено: {traffic_stats.get('upload', 0)} MB
• 📊 Всего: {traffic_stats.get('total', 0)} MB

<b>Активные сессии:</b> {traffic_stats.get('sessions', 0)}
            """
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="my_account")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                stats_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error showing stats: {e}")
            await update.callback_query.reply_text("❌ Ошибка получения статистики")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ошибок"""
        logger.error(f"Update {update} caused error {context.error}")
    
    async def run(self):
        """Запуск бота"""
        self.init_db()
        
        # Создаем приложение
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("plans", self.plans_command))
        self.application.add_handler(CommandHandler("account", self.account_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
        
        # Запускаем бота
        logger.info("Starting SecureLink Telegram Bot...")
        await self.application.run_polling()

async def main():
    """Главная функция"""
    bot = SecureLinkBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())

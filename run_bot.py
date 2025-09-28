#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота без конфликтов
"""
import os
import sys
import asyncio
import logging

# Устанавливаем переменные окружения
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o")
os.environ.setdefault("DATABASE_URL", "postgresql://alexanderkhokhlov@localhost/securelink")
os.environ.setdefault("WEB_APP_URL", "https://a2c4260d9b8d.ngrok-free.app")

# Настройка логирования
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

def run_bot():
    """Запуск бота"""
    try:
        # Импортируем и запускаем бота
        from simple_bot import main
        
        print("🤖 Запуск SecureLink Telegram Bot...")
        print(f"📱 Bot Token: {os.environ['TELEGRAM_BOT_TOKEN'][:20]}...")
        print(f"🌐 Web App URL: {os.environ['WEB_APP_URL']}")
        print(f"🗄️ Database: {os.environ['DATABASE_URL']}")
        print()
        
        # Запускаем бота
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_bot()

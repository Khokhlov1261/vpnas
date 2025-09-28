#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота
"""
import os
import sys
import asyncio
from telegram_bot import main

if __name__ == "__main__":
    # Устанавливаем переменные окружения
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o")
    os.environ.setdefault("DATABASE_URL", "postgresql://alexanderkhokhlov@localhost/securelink")
    os.environ.setdefault("WEB_APP_URL", "https://a2c4260d9b8d.ngrok-free.app")
    os.environ.setdefault("JWT_SECRET", "dev-secret-key-change-in-production")
    
    print("🤖 Запуск SecureLink Telegram Bot...")
    print(f"📱 Bot Token: {os.environ['TELEGRAM_BOT_TOKEN'][:20]}...")
    print(f"🌐 Web App URL: {os.environ['WEB_APP_URL']}")
    print(f"🗄️ Database: {os.environ['DATABASE_URL']}")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        sys.exit(1)

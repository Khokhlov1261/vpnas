#!/usr/bin/env python3
"""
Скрипт для настройки Telegram Bot Web App
"""
import requests
import json
import os

BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5o"
WEB_APP_URL = "https://yourdomain.com"  # Замените на ваш домен

def setup_web_app():
    """Настройка Web App для бота"""
    
    # 1. Создание Web App
    web_app_data = {
        "title": "SecureLink VPN",
        "description": "Безопасный VPN с WireGuard",
        "photo": {
            "url": "https://via.placeholder.com/640x360/6366f1/ffffff?text=SecureLink+VPN"
        },
        "web_app": {
            "url": f"{WEB_APP_URL}/dashboard"
        }
    }
    
    print("🤖 Настройка Telegram Bot Web App...")
    print(f"📱 Bot: @Securelinkvpn_bot")
    print(f"🌐 Web App URL: {WEB_APP_URL}/dashboard")
    print()
    
    # 2. Установка меню кнопки
    menu_button_data = {
        "type": "web_app",
        "text": "🚀 Открыть VPN",
        "web_app": {
            "url": f"{WEB_APP_URL}/dashboard"
        }
    }
    
    try:
        # Устанавливаем меню кнопку
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
            json=menu_button_data
        )
        
        if response.json().get("ok"):
            print("✅ Меню кнопка установлена!")
        else:
            print(f"❌ Ошибка установки меню: {response.json()}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print()
    print("📋 Инструкции для ручной настройки:")
    print("1. Откройте @BotFather в Telegram")
    print("2. Отправьте команду /mybots")
    print("3. Выберите вашего бота @Securelinkvpn_bot")
    print("4. Нажмите 'Bot Settings' → 'Menu Button'")
    print("5. Выберите 'Configure menu button'")
    print("6. Введите текст: 🚀 Открыть VPN")
    print(f"7. Введите URL: {WEB_APP_URL}/dashboard")
    print()
    print("🔗 Альтернативно, используйте команды:")
    print(f"/setmenubutton")
    print(f"web_app")
    print(f"🚀 Открыть VPN")
    print(f"{WEB_APP_URL}/dashboard")
    print()
    print("🌐 Для локального тестирования:")
    print("1. Используйте ngrok для туннелирования:")
    print("   ngrok http 8000")
    print("2. Замените WEB_APP_URL на ngrok URL")
    print("3. Обновите настройки бота")

def test_web_app():
    """Тестирование Web App"""
    print("🧪 Тестирование Web App...")
    
    # Проверяем, что приложение доступно
    try:
        response = requests.get(f"{WEB_APP_URL}/dashboard", timeout=5)
        if response.status_code == 200:
            print("✅ Web App доступен!")
        else:
            print(f"⚠️  Web App недоступен (статус: {response.status_code})")
    except Exception as e:
        print(f"❌ Web App недоступен: {e}")
        print("💡 Убедитесь, что приложение запущено и доступно по указанному URL")

if __name__ == "__main__":
    setup_web_app()
    print()
    test_web_app()

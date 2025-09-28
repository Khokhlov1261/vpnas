#!/bin/bash

# SecureLink VPN - Скрипт запуска
echo "🚀 Запуск SecureLink VPN приложения"
echo "=================================="

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установите Python 3.8+"
    exit 1
fi

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
if [ ! -f "requirements.txt" ]; then
    echo "❌ Файл requirements.txt не найден"
    exit 1
fi

# Установка зависимостей
echo "📥 Установка зависимостей..."
pip3 install -r requirements.txt

# Проверка переменных окружения
echo "🔧 Проверка конфигурации..."

if [ -z "$DATABASE_URL" ] && [ -z "$PG_HOST" ]; then
    echo "⚠️  Переменные базы данных не настроены"
    echo "   Установите DATABASE_URL или PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD"
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  TELEGRAM_BOT_TOKEN не настроен"
fi

if [ -z "$JWT_SECRET" ]; then
    echo "⚠️  JWT_SECRET не настроен (используется значение по умолчанию)"
fi

# Применение миграции базы данных
echo "🗄️  Проверка миграции базы данных..."
python3 migrate_db.py

if [ $? -eq 0 ]; then
    echo "✅ База данных готова"
else
    echo "❌ Ошибка миграции базы данных"
    exit 1
fi

# Запуск приложения
echo "🎯 Запуск приложения..."
echo "   Доступно по адресу: http://localhost:8000"
echo "   Личный кабинет: http://localhost:8000/dashboard"
echo "   Админ-панель: http://localhost:8000/admin"
echo ""
echo "Для остановки нажмите Ctrl+C"
echo ""

python3 App.py

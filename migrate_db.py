#!/usr/bin/env python3
"""
Скрипт для применения миграций базы данных
"""
import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def get_db_connection():
    """Получение соединения с базой данных"""
    DATABASE_URL = os.environ.get("DATABASE_URL")
    PG_HOST = os.environ.get("PG_HOST", "localhost")
    PG_PORT = int(os.environ.get("PG_PORT", 5432))
    PG_DB = os.environ.get("PG_DB", "securelink")
    PG_USER = os.environ.get("PG_USER", "securelink")
    PG_PASSWORD = os.environ.get("PG_PASSWORD", "password")
    
    if DATABASE_URL:
        conninfo = DATABASE_URL
    else:
        conninfo = f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} user={PG_USER} password={PG_PASSWORD}"
    
    return psycopg2.connect(conninfo)

def apply_migration():
    """Применение миграции"""
    try:
        # Читаем SQL файл миграции
        migration_file = os.path.join(os.path.dirname(__file__), 'database_migration.sql')
        
        if not os.path.exists(migration_file):
            print(f"❌ Файл миграции не найден: {migration_file}")
            return False
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        # Подключаемся к базе данных
        conn = get_db_connection()
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        with conn.cursor() as cur:
            print("🔄 Применяем миграцию базы данных...")
            
            # Выполняем миграцию
            cur.execute(migration_sql)
            
            print("✅ Миграция успешно применена!")
            
            # Проверяем созданные таблицы
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            
            tables = cur.fetchall()
            print(f"\n📋 Созданные таблицы ({len(tables)}):")
            for table in tables:
                print(f"  - {table[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка применения миграции: {e}")
        return False

def check_migration_status():
    """Проверка статуса миграции"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Проверяем существование новых таблиц
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('users', 'user_sessions', 'telegram_auth_data', 'user_traffic_logs', 'user_notifications', 'user_activity_log')
                ORDER BY table_name;
            """)
            
            new_tables = cur.fetchall()
            
            if len(new_tables) == 6:
                print("✅ Все новые таблицы созданы")
                return True
            else:
                print(f"⚠️  Создано {len(new_tables)} из 6 новых таблиц")
                return False
                
    except Exception as e:
        print(f"❌ Ошибка проверки статуса: {e}")
        return False

def main():
    """Основная функция"""
    print("🚀 Миграция базы данных SecureLink VPN")
    print("=" * 50)
    
    # Проверяем текущий статус
    print("\n📊 Проверяем текущий статус...")
    if check_migration_status():
        print("✅ Миграция уже применена")
        return
    
    # Применяем миграцию
    print("\n🔄 Применяем миграцию...")
    if apply_migration():
        print("\n🎉 Миграция завершена успешно!")
        print("\n📝 Следующие шаги:")
        print("1. Установите зависимости: pip install -r requirements.txt")
        print("2. Настройте переменные окружения:")
        print("   - TELEGRAM_BOT_TOKEN=your_bot_token")
        print("   - JWT_SECRET=your_jwt_secret")
        print("   - DATABASE_URL=your_database_url")
        print("3. Запустите приложение: python App.py")
    else:
        print("\n❌ Миграция не удалась")
        sys.exit(1)

if __name__ == "__main__":
    main()

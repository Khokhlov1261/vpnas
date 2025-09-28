#!/usr/bin/env python3
"""
Скрипт для создания тестового пользователя
"""
import os
import sys
import psycopg2
from datetime import datetime, timezone, timedelta
import jwt

# Настройки
DATABASE_URL = "postgresql://alexanderkhokhlov@localhost/securelink"
JWT_SECRET = "dev-secret-key-change-in-production"

def create_test_user():
    """Создание тестового пользователя"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Создаем тестового пользователя
        cursor.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, language_code, last_login)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_login = EXCLUDED.last_login
            RETURNING id
        """, (123456789, "testuser", "Test", "User", "ru", datetime.now(timezone.utc).isoformat()))
        
        user_id = cursor.fetchone()[0]
        
        # Создаем тестовую подписку
        cursor.execute("""
            INSERT INTO orders (user_id, telegram_id, email, plan, price, status, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id, 
            123456789, 
            "test@example.com", 
            "1 месяц", 
            99.0, 
            "paid", 
            datetime.now(timezone.utc).isoformat(),
            (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        ))
        
        order_id = cursor.fetchone()[0]
        
        # Создаем JWT токен
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24 * 7)  # 7 дней
        
        payload = {
            'user_id': user_id,
            'iat': now,
            'exp': expires_at,
            'type': 'access_token'
        }
        
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        
        # Сохраняем сессию
        cursor.execute("""
            INSERT INTO user_sessions (user_id, session_token, expires_at)
            VALUES (%s, %s, %s)
        """, (user_id, token, expires_at))
        
        conn.commit()
        conn.close()
        
        print("✅ Тестовый пользователь создан!")
        print(f"📧 Email: test@example.com")
        print(f"🆔 User ID: {user_id}")
        print(f"🔑 JWT Token: {token}")
        print(f"📱 Telegram ID: 123456789")
        print(f"👤 Username: @testuser")
        print(f"📋 Order ID: {order_id}")
        print()
        print("🌐 Для тестирования API используйте:")
        print(f"curl -H 'Authorization: Bearer {token}' http://localhost:8000/auth/me")
        print()
        print("🔗 Для тестирования в браузере:")
        print("1. Откройте Developer Tools (F12)")
        print("2. В Console выполните:")
        print(f"   localStorage.setItem('authToken', '{token}')")
        print("3. Обновите страницу /dashboard")
        
        return token
        
    except Exception as e:
        print(f"❌ Ошибка создания тестового пользователя: {e}")
        return None

if __name__ == "__main__":
    create_test_user()

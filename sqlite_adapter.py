"""
SQLite адаптер для разработки
"""
import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

class SQLiteAdapter:
    """Адаптер для работы с SQLite вместо PostgreSQL"""
    
    def __init__(self, db_path: str = "orders.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Создаем таблицы, если их нет
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                language_code TEXT DEFAULT 'ru',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                settings TEXT DEFAULT '{}'
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_token TEXT UNIQUE,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_auth_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                auth_date INTEGER,
                hash TEXT,
                query_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_traffic_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                public_key TEXT,
                rx_bytes INTEGER DEFAULT 0,
                tx_bytes INTEGER DEFAULT 0,
                speed_rx REAL DEFAULT 0,
                speed_tx REAL DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                title TEXT,
                message TEXT,
                is_read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT DEFAULT '{}',
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Обновляем таблицу orders, добавляя новые колонки если их нет
        cursor.execute("PRAGMA table_info(orders)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER")
        if 'telegram_id' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN telegram_id INTEGER")
        if 'payment_method' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'yookassa'")
        if 'auto_renewal' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN auto_renewal BOOLEAN DEFAULT 0")
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Получение соединения с базой данных"""
        return sqlite3.connect(self.db_path)
    
    def execute_query(self, query: str, params: tuple = ()):
        """Выполнение запроса"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            if query.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
                return [dict(row) for row in result]
            else:
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по Telegram ID"""
        result = self.execute_query(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        return result[0] if result else None
    
    def create_user(self, telegram_id: int, username: str = None, first_name: str = None, 
                   last_name: str = None, language_code: str = 'ru') -> int:
        """Создание нового пользователя"""
        cursor = self.get_connection().cursor()
        cursor.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, language_code, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (telegram_id, username, first_name, last_name, language_code, datetime.now(timezone.utc).isoformat()))
        
        user_id = cursor.lastrowid
        cursor.connection.commit()
        cursor.connection.close()
        return user_id
    
    def update_user_login(self, user_id: int):
        """Обновление времени последнего входа"""
        self.execute_query(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), user_id)
        )
    
    def create_session(self, user_id: int, token: str, expires_at: str) -> bool:
        """Создание сессии пользователя"""
        try:
            self.execute_query(
                "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at)
            )
            return True
        except:
            return False
    
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Получение сессии по токену"""
        result = self.execute_query(
            "SELECT * FROM user_sessions WHERE session_token = ? AND expires_at > ?",
            (token, datetime.now(timezone.utc).isoformat())
        )
        return result[0] if result else None
    
    def delete_session(self, token: str) -> bool:
        """Удаление сессии"""
        try:
            self.execute_query("DELETE FROM user_sessions WHERE session_token = ?", (token,))
            return True
        except:
            return False
    
    def get_user_subscriptions(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение подписок пользователя"""
        return self.execute_query(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
    
    def cleanup_expired_sessions(self) -> int:
        """Очистка истекших сессий"""
        return self.execute_query(
            "DELETE FROM user_sessions WHERE expires_at < ?",
            (datetime.now(timezone.utc).isoformat(),)
        )

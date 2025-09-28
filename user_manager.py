"""
Модуль для управления пользователями и авторизацией
"""
import os
import json
import hashlib
import hmac
import time
import jwt
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import parse_qs, unquote
import logging

logger = logging.getLogger("securelink")

# JWT настройки
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 дней

# Telegram Bot настройки
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL")

class UserManager:
    """Класс для управления пользователями и авторизацией"""
    
    def __init__(self, db_connection_func):
        """
        Инициализация менеджера пользователей
        
        Args:
            db_connection_func: Функция для получения соединения с БД
        """
        self.get_conn = db_connection_func
    
    def validate_telegram_data(self, init_data: str, bot_token: str) -> bool:
        """
        Валидация данных от Telegram Web App
        
        Args:
            init_data: Строка с данными от Telegram
            bot_token: Токен бота
            
        Returns:
            bool: True если данные валидны
        """
        try:
            # Парсим данные
            parsed_data = parse_qs(init_data)
            
            # Извлекаем hash
            received_hash = parsed_data.get('hash', [None])[0]
            if not received_hash:
                return False
            
            # Удаляем hash из данных для проверки
            data_check_string = init_data.replace(f'&hash={received_hash}', '').replace(f'hash={received_hash}&', '').replace(f'hash={received_hash}', '')
            
            # Создаем секретный ключ
            secret_key = hmac.new(
                "WebAppData".encode(),
                bot_token.encode(),
                hashlib.sha256
            ).digest()
            
            # Вычисляем hash
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return calculated_hash == received_hash
            
        except Exception as e:
            logger.error(f"Ошибка валидации Telegram данных: {e}")
            return False
    
    def parse_telegram_user_data(self, init_data: str) -> Optional[Dict[str, Any]]:
        """
        Парсинг данных пользователя из Telegram
        
        Args:
            init_data: Строка с данными от Telegram
            
        Returns:
            dict: Данные пользователя или None
        """
        try:
            parsed_data = parse_qs(init_data)
            user_data = parsed_data.get('user', [None])[0]
            
            if user_data:
                return json.loads(unquote(user_data))
            return None
            
        except Exception as e:
            logger.error(f"Ошибка парсинга данных пользователя: {e}")
            return None
    
    def get_or_create_telegram_user(self, telegram_user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Получение или создание пользователя по данным Telegram
        
        Args:
            telegram_user: Данные пользователя из Telegram
            
        Returns:
            dict: Данные пользователя из БД или None
        """
        try:
            telegram_id = telegram_user.get('id')
            username = telegram_user.get('username')
            first_name = telegram_user.get('first_name', '')
            last_name = telegram_user.get('last_name', '')
            language_code = telegram_user.get('language_code', 'ru')
            
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    # Ищем существующего пользователя
                    cur.execute("""
                        SELECT id, telegram_id, username, first_name, last_name, email, 
                               language_code, created_at, last_login, is_active, settings
                        FROM users 
                        WHERE telegram_id = %s
                    """, (telegram_id,))
                    
                    row = cur.fetchone()
                    
                    if row:
                        # Обновляем данные существующего пользователя
                        cur.execute("""
                            UPDATE users 
                            SET username = %s, first_name = %s, last_name = %s, 
                                language_code = %s, last_login = %s
                            WHERE telegram_id = %s
                        """, (username, first_name, last_name, language_code, 
                              datetime.now(timezone.utc), telegram_id))
                        
                        user_data = {
                            'id': row[0],
                            'telegram_id': row[1],
                            'username': username,
                            'first_name': first_name,
                            'last_name': last_name,
                            'email': row[5],
                            'language_code': language_code,
                            'created_at': row[7].isoformat() if row[7] else None,
                            'last_login': datetime.now(timezone.utc).isoformat(),
                            'is_active': row[9],
                            'settings': json.loads(row[10]) if row[10] else {}
                        }
                    else:
                        # Создаем нового пользователя
                        cur.execute("""
                            INSERT INTO users (telegram_id, username, first_name, last_name, language_code, last_login)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id, created_at
                        """, (telegram_id, username, first_name, last_name, language_code, 
                              datetime.now(timezone.utc)))
                        
                        new_row = cur.fetchone()
                        user_data = {
                            'id': new_row[0],
                            'telegram_id': telegram_id,
                            'username': username,
                            'first_name': first_name,
                            'last_name': last_name,
                            'email': None,
                            'language_code': language_code,
                            'created_at': new_row[1].isoformat(),
                            'last_login': datetime.now(timezone.utc).isoformat(),
                            'is_active': True,
                            'settings': {}
                        }
                    
                    # Логируем активность
                    cur.execute("""
                        SELECT log_user_activity(%s, %s, %s, %s, %s)
                    """, (user_data['id'], 'login', json.dumps({'method': 'telegram'}), 
                          None, None))  # IP и User-Agent можно добавить позже
                    
                    return user_data
                    
        except Exception as e:
            logger.error(f"Ошибка создания/получения пользователя: {e}")
            return None
    
    def create_jwt_token(self, user_id: int, additional_claims: Dict[str, Any] = None) -> str:
        """
        Создание JWT токена для пользователя
        
        Args:
            user_id: ID пользователя
            additional_claims: Дополнительные claims для токена
            
        Returns:
            str: JWT токен
        """
        try:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=JWT_EXPIRATION_HOURS)
            
            payload = {
                'user_id': user_id,
                'iat': now,
                'exp': expires_at,
                'type': 'access_token'
            }
            
            if additional_claims:
                payload.update(additional_claims)
            
            token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
            
            # Сохраняем сессию в БД
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_sessions (user_id, session_token, expires_at)
                        VALUES (%s, %s, %s)
                    """, (user_id, token, expires_at))
            
            return token
            
        except Exception as e:
            logger.error(f"Ошибка создания JWT токена: {e}")
            return None
    
    def validate_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Валидация JWT токена
        
        Args:
            token: JWT токен
            
        Returns:
            dict: Данные токена или None
        """
        try:
            # Проверяем токен в БД
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT us.user_id, us.expires_at, u.is_active, u.username, u.first_name
                        FROM user_sessions us
                        JOIN users u ON us.user_id = u.id
                        WHERE us.session_token = %s AND us.expires_at > %s
                    """, (token, datetime.now(timezone.utc)))
                    
                    row = cur.fetchone()
                    if not row:
                        return None
                    
                    user_id, expires_at, is_active, username, first_name = row
                    
                    if not is_active:
                        return None
                    
                    # Декодируем JWT
                    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                    
                    return {
                        'user_id': user_id,
                        'username': username,
                        'first_name': first_name,
                        'expires_at': expires_at.isoformat(),
                        'payload': payload
                    }
                    
        except jwt.ExpiredSignatureError:
            logger.info("JWT токен истек")
            return None
        except jwt.InvalidTokenError:
            logger.info("Невалидный JWT токен")
            return None
        except Exception as e:
            logger.error(f"Ошибка валидации JWT токена: {e}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: Данные пользователя или None
        """
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, telegram_id, username, first_name, last_name, email,
                               language_code, created_at, last_login, is_active, settings
                        FROM users 
                        WHERE id = %s
                    """, (user_id,))
                    
                    row = cur.fetchone()
                    if not row:
                        return None
                    
                    return {
                        'id': row[0],
                        'telegram_id': row[1],
                        'username': row[2],
                        'first_name': row[3],
                        'last_name': row[4],
                        'email': row[5],
                        'language_code': row[6],
                        'created_at': row[7].isoformat() if row[7] else None,
                        'last_login': row[8].isoformat() if row[8] else None,
                        'is_active': row[9],
                        'settings': json.loads(row[10]) if row[10] else {}
                    }
                    
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
    
    def get_user_subscriptions(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получение подписок пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            list: Список подписок
        """
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, plan, price, status, created_at, expires_at, conf_file, public_key, client_ip
                        FROM orders 
                        WHERE user_id = %s 
                        ORDER BY created_at DESC
                    """, (user_id,))
                    
                    subscriptions = []
                    for row in cur.fetchall():
                        subscriptions.append({
                            'id': row[0],
                            'plan': row[1],
                            'price': float(row[2]),
                            'status': row[3],
                            'created_at': row[4].isoformat() if row[4] else None,
                            'expires_at': row[5].isoformat() if row[5] else None,
                            'has_config': bool(row[6]),
                            'public_key': row[7],
                            'client_ip': row[8]
                        })
                    
                    return subscriptions
                    
        except Exception as e:
            logger.error(f"Ошибка получения подписок: {e}")
            return []
    
    def cleanup_expired_sessions(self) -> int:
        """
        Очистка истекших сессий
        
        Returns:
            int: Количество удаленных сессий
        """
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT cleanup_expired_sessions()")
                    result = cur.fetchone()
                    return result[0] if result else 0
                    
        except Exception as e:
            logger.error(f"Ошибка очистки сессий: {e}")
            return 0
    
    def revoke_user_session(self, token: str) -> bool:
        """
        Отзыв сессии пользователя
        
        Args:
            token: JWT токен
            
        Returns:
            bool: True если сессия отозвана
        """
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM user_sessions 
                        WHERE session_token = %s
                    """, (token,))
                    
                    return cur.rowcount > 0
                    
        except Exception as e:
            logger.error(f"Ошибка отзыва сессии: {e}")
            return False

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение пользователя по Telegram ID (асинхронная версия)
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            Dict с данными пользователя или None
        """
        try:
            conn = self.get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, telegram_id, username, first_name, last_name, 
                       email, language_code, is_bot, is_premium, 
                       allows_write_to_pm, photo_url, settings, 
                       created_at, last_login
                FROM users 
                WHERE telegram_id = %s
            """, (telegram_id,))
            
            result = cursor.fetchone()
            
            if result:
                return {
                    'id': result[0],
                    'telegram_id': result[1],
                    'username': result[2],
                    'first_name': result[3],
                    'last_name': result[4],
                    'email': result[5],
                    'language_code': result[6],
                    'is_bot': result[7],
                    'is_premium': result[8],
                    'allows_write_to_pm': result[9],
                    'photo_url': result[10],
                    'settings': result[11],
                    'created_at': result[12],
                    'last_login': result[13]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by telegram_id: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def get_or_create_telegram_user(self, telegram_id: int, username: str = None, 
                                        first_name: str = None, last_name: str = None,
                                        language_code: str = None) -> Dict[str, Any]:
        """
        Получение или создание пользователя по Telegram данным (асинхронная версия)
        
        Args:
            telegram_id: Telegram ID пользователя
            username: Username пользователя
            first_name: Имя пользователя
            last_name: Фамилия пользователя
            language_code: Код языка
            
        Returns:
            Dict с данными пользователя
        """
        try:
            # Сначала пытаемся найти существующего пользователя
            user = self.get_user_by_telegram_id(telegram_id)
            
            if user:
                # Обновляем last_login
                self.update_user_last_login(user['id'])
                return user
            
            # Создаем нового пользователя
            conn = self.get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name, language_code, created_at, last_login)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id, telegram_id, username, first_name, last_name, 
                         email, language_code, is_bot, is_premium, 
                         allows_write_to_pm, photo_url, settings, 
                         created_at, last_login
            """, (telegram_id, username, first_name, last_name, language_code))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                return {
                    'id': result[0],
                    'telegram_id': result[1],
                    'username': result[2],
                    'first_name': result[3],
                    'last_name': result[4],
                    'email': result[5],
                    'language_code': result[6],
                    'is_bot': result[7],
                    'is_premium': result[8],
                    'allows_write_to_pm': result[9],
                    'photo_url': result[10],
                    'settings': result[11],
                    'created_at': result[12],
                    'last_login': result[13]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating telegram user: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def update_user_last_login(self, user_id: int):
        """
        Обновление времени последнего входа (асинхронная версия)
        
        Args:
            user_id: ID пользователя
        """
        try:
            conn = self.get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users 
                SET last_login = NOW() 
                WHERE id = %s
            """, (user_id,))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error updating user last login: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

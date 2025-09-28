# SecureLink VPN - Модернизированное приложение

Современное VPN приложение с авторизацией через Telegram, личным кабинетом и удобным интерфейсом.

## 🚀 Новые возможности

### ✅ Реализовано
- **Авторизация через Telegram** - безопасная аутентификация через Telegram Web App
- **Личный кабинет** - полнофункциональный dashboard для пользователей
- **API для личного кабинета** - RESTful API для всех операций
- **Расширенная база данных** - поддержка пользователей, сессий, уведомлений
- **JWT токены** - безопасные сессии пользователей
- **Современный UI/UX** - адаптивный дизайн с темной темой

### 🔄 В разработке
- **Real-time обновления** - WebSocket для live статистики
- **PWA функциональность** - работа в офлайн режиме
- **Расширенная аналитика** - детальная статистика трафика

## 📋 Требования

- Python 3.8+
- PostgreSQL 12+
- WireGuard
- Telegram Bot Token

## 🛠 Установка

### 1. Клонирование и зависимости

```bash
# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка базы данных

```bash
# Применение миграции
python migrate_db.py
```

### 3. Переменные окружения

Создайте файл `.env` или установите переменные окружения:

```bash
# База данных
DATABASE_URL=postgresql://user:password@localhost:5432/securelink
# или отдельно:
PG_HOST=localhost
PG_PORT=5432
PG_DB=securelink
PG_USER=securelink
PG_PASSWORD=password

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_URL=https://yourdomain.com/webhook

# JWT
JWT_SECRET=your_very_secure_jwt_secret_key

# WireGuard
WG_CONFIG_PATH=/etc/wireguard/wg0.conf
WG_INTERFACE=wg0
SERVER_PUBLIC_KEY=your_server_public_key
SERVER_ENDPOINT=yourdomain.com:51820
WG_CLIENT_NET_PREFIX=10.0.0.
WG_CLIENT_MIN=2
WG_CLIENT_MAX=254
DNS_ADDR=8.8.8.8

# YooKassa
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key

# SMTP
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
FROM_EMAIL=your_email@gmail.com

# Админ
ADMIN_USER=admin
ADMIN_PASS=secure_password

# Приложение
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
```

### 4. Создание Telegram Bot

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Получите токен бота
3. Настройте Web App:
   ```
   /newapp
   /setmenubutton
   ```

### 5. Запуск приложения

```bash
# Разработка
python App.py

# Продакшн с Gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 App:app
```

## 📱 Использование

### Для пользователей

1. **Авторизация**: Откройте приложение через Telegram Web App
2. **Личный кабинет**: Просматривайте подписки, конфигурации, статистику
3. **Управление**: Скачивайте конфигурации, отслеживайте трафик

### Для администраторов

- **Админ-панель**: `/admin` - мониторинг сервера и клиентов
- **API**: RESTful API для интеграций

## 🔧 API Endpoints

### Авторизация
- `POST /auth/telegram` - Авторизация через Telegram
- `GET /auth/me` - Получение данных пользователя
- `POST /auth/logout` - Выход из системы

### Личный кабинет
- `GET /api/user/subscriptions` - Подписки пользователя
- `GET /api/user/traffic` - Статистика трафика
- `GET /api/user/configs` - Конфигурации
- `GET /api/user/notifications` - Уведомления

### Публичные
- `GET /` - Главная страница
- `GET /dashboard` - Личный кабинет
- `GET /download/{order_id}` - Скачивание конфигурации
- `GET /qr/{order_id}` - QR-код конфигурации

## 🎨 UI/UX Особенности

### Дизайн
- **Темная тема** - современный dark mode
- **Адаптивность** - работает на всех устройствах
- **Анимации** - плавные переходы и эффекты
- **Иконки** - SVG иконки для лучшей производительности

### UX
- **Интуитивная навигация** - понятная структура меню
- **Быстрая загрузка** - оптимизированные запросы
- **Уведомления** - toast сообщения для обратной связи
- **Модальные окна** - для дополнительных действий

## 🔒 Безопасность

- **JWT токены** - безопасные сессии
- **Валидация Telegram** - проверка данных от Telegram
- **HTTPS** - обязательное шифрование
- **Rate limiting** - защита от злоупотреблений
- **Валидация данных** - проверка всех входных данных

## 📊 Мониторинг

### Логирование
- Структурированные логи
- Уровни логирования
- Ротация логов

### Метрики
- Статистика трафика
- Использование ресурсов
- Активность пользователей

## 🚀 Развертывание

### Docker (рекомендуется)

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "App:app"]
```

### Nginx конфигурация

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔄 Обновления

### Миграции базы данных
```bash
python migrate_db.py
```

### Обновление зависимостей
```bash
pip install -r requirements.txt --upgrade
```

## 🐛 Отладка

### Логи
```bash
# Просмотр логов
tail -f /var/log/securelink/app.log

# Уровень отладки
export DEBUG=true
```

### Проверка статуса
```bash
# Проверка WireGuard
wg show

# Проверка базы данных
psql -d securelink -c "SELECT COUNT(*) FROM users;"

# Проверка Telegram Bot
curl -X GET "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
```

## 📞 Поддержка

- **Email**: mailrealeden@yahoo.com
- **Telegram**: @your_support_bot
- **Документация**: [Wiki](https://github.com/your-repo/wiki)

## 📄 Лицензия

© 2025 Secure-Link.ru ИНН: 591906696848

---

**Версия**: 2.0.0  
**Последнее обновление**: Январь 2025

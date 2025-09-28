# Архитектура SecureLink VPN

## 🏗 Общая схема

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram      │    │   Web Browser   │    │   Mobile App    │
│   Web App       │    │   (Desktop)     │    │   (iOS/Android) │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │ HTTPS/WebSocket      │ HTTPS                │ HTTPS
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx Reverse Proxy                         │
│                    (SSL Termination)                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Flask Application                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Auth      │  │   API       │  │   Admin     │            │
│  │   Routes    │  │   Routes    │  │   Routes    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   User      │  │   Order     │  │   WireGuard │            │
│  │   Manager   │  │   Manager   │  │   Manager   │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │    users    │  │    orders   │  │  sessions   │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │notifications│  │traffic_logs │  │activity_log │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  Telegram   │  │  YooKassa   │  │    SMTP     │            │
│  │  Bot API    │  │  Payments   │  │   Server    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

## 🔐 Поток авторизации

```
1. Пользователь открывает Telegram Web App
   ↓
2. Telegram передает initData в приложение
   ↓
3. Приложение валидирует данные через HMAC
   ↓
4. Создается/находится пользователь в БД
   ↓
5. Генерируется JWT токен
   ↓
6. Токен сохраняется в localStorage
   ↓
7. Пользователь авторизован
```

## 📊 Поток данных в личном кабинете

```
1. Загрузка dashboard
   ↓
2. Проверка JWT токена
   ↓
3. Запрос данных пользователя
   ↓
4. Запрос подписок
   ↓
5. Запрос статистики трафика
   ↓
6. Запрос уведомлений
   ↓
7. Отображение данных в UI
```

## 🗄 Схема базы данных

### Основные таблицы

```sql
-- Пользователи
users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    email VARCHAR(255),
    language_code VARCHAR(10),
    created_at TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN,
    settings JSONB
)

-- Сессии
user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    session_token VARCHAR(255) UNIQUE,
    expires_at TIMESTAMP,
    created_at TIMESTAMP,
    last_activity TIMESTAMP,
    user_agent TEXT,
    ip_address INET
)

-- Заказы (расширенная)
orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    telegram_id BIGINT,
    email TEXT,
    plan TEXT,
    price NUMERIC,
    status TEXT,
    conf_file TEXT,
    public_key TEXT,
    client_ip TEXT,
    access_token TEXT,
    payment_method VARCHAR(50),
    auto_renewal BOOLEAN,
    created_at TIMESTAMP,
    expires_at TIMESTAMP
)

-- Логи трафика
user_traffic_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    public_key VARCHAR(255),
    rx_bytes BIGINT,
    tx_bytes BIGINT,
    speed_rx REAL,
    speed_tx REAL,
    last_seen TIMESTAMP,
    logged_at TIMESTAMP
)

-- Уведомления
user_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    type VARCHAR(50),
    title VARCHAR(255),
    message TEXT,
    is_read BOOLEAN,
    created_at TIMESTAMP,
    read_at TIMESTAMP
)

-- Лог активности
user_activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP
)
```

## 🔄 API Endpoints

### Авторизация
```
POST /auth/telegram     - Авторизация через Telegram
GET  /auth/me          - Получение данных пользователя
POST /auth/logout      - Выход из системы
```

### Личный кабинет
```
GET  /api/user/subscriptions           - Подписки пользователя
GET  /api/user/traffic                - Статистика трафика
GET  /api/user/configs                - Конфигурации
GET  /api/user/notifications          - Уведомления
POST /api/user/notifications/{id}/read - Отметить уведомление
```

### Публичные
```
GET  /                    - Главная страница
GET  /dashboard          - Личный кабинет
GET  /download/{id}      - Скачивание конфигурации
GET  /qr/{id}           - QR-код конфигурации
POST /create-payment    - Создание платежа
POST /free-trial        - Бесплатный пробный период
```

### Админ
```
GET  /admin             - Админ-панель
GET  /admin/stats       - Статистика сервера
POST /admin/delete/{key} - Удаление клиента
```

## 🎨 Frontend архитектура

### Структура компонентов

```
dashboard.html
├── Sidebar Navigation
│   ├── User Info
│   ├── Navigation Menu
│   └── Logout Button
├── Main Content
│   ├── Dashboard Section
│   │   ├── Stats Cards
│   │   └── Traffic Chart
│   ├── Subscriptions Section
│   │   └── Subscriptions List
│   ├── Configs Section
│   │   └── Configs List
│   ├── Traffic Section
│   │   └── Traffic Stats
│   ├── Notifications Section
│   │   └── Notifications List
│   └── Settings Section
│       └── Settings Form
└── Modals
    └── Config Modal (QR Code)
```

### JavaScript классы

```javascript
DashboardApp
├── init()                    - Инициализация
├── checkAuth()              - Проверка авторизации
├── authenticateWithTelegram() - Авторизация через Telegram
├── showSection()            - Переключение секций
├── loadSectionData()        - Загрузка данных секции
├── apiCall()               - HTTP запросы
├── showToast()             - Уведомления
└── formatBytes()           - Форматирование данных
```

## 🔒 Безопасность

### Аутентификация
- **JWT токены** с коротким временем жизни
- **Валидация Telegram данных** через HMAC
- **Автоматическая очистка** истекших сессий

### Авторизация
- **Middleware** для проверки токенов
- **Роли пользователей** (user, admin)
- **Rate limiting** для API endpoints

### Защита данных
- **HTTPS** для всех соединений
- **Валидация входных данных**
- **SQL injection** защита через параметризованные запросы
- **XSS** защита через экранирование

## 📈 Мониторинг

### Логирование
- **Структурированные логи** в JSON формате
- **Уровни логирования** (DEBUG, INFO, WARNING, ERROR)
- **Ротация логов** для предотвращения переполнения

### Метрики
- **Статистика трафика** в реальном времени
- **Использование ресурсов** сервера
- **Активность пользователей**
- **Ошибки и исключения**

## 🚀 Развертывание

### Docker
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "App:app"]
```

### Nginx
```nginx
upstream app {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔄 CI/CD

### Автоматизация
- **Автоматические тесты** при каждом коммите
- **Автоматическое развертывание** при merge в main
- **Миграции базы данных** в процессе деплоя
- **Health checks** для проверки работоспособности

### Мониторинг
- **Uptime monitoring** для отслеживания доступности
- **Performance monitoring** для отслеживания производительности
- **Error tracking** для отслеживания ошибок
- **Log aggregation** для централизованного логирования

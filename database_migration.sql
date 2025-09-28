-- ============================================
-- МИГРАЦИЯ БАЗЫ ДАННЫХ ДЛЯ VPN ПРИЛОЖЕНИЯ
-- ============================================

-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    email VARCHAR(255),
    language_code VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}'::jsonb
);

-- Создание таблицы сессий пользователей
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_agent TEXT,
    ip_address INET
);

-- Создание таблицы для хранения Telegram Web App данных
CREATE TABLE IF NOT EXISTS telegram_auth_data (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    auth_date INTEGER NOT NULL,
    hash VARCHAR(255) NOT NULL,
    query_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создание таблицы orders (если не существует)
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    email TEXT,
    plan TEXT,
    price NUMERIC,
    status TEXT,
    conf_file TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    public_key TEXT,
    client_ip TEXT,
    access_token TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_id BIGINT,
    payment_method VARCHAR(50) DEFAULT 'yookassa',
    auto_renewal BOOLEAN DEFAULT FALSE
);

-- Создание таблицы для отслеживания трафика пользователей
CREATE TABLE IF NOT EXISTS user_traffic_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    public_key VARCHAR(255) NOT NULL,
    rx_bytes BIGINT DEFAULT 0,
    tx_bytes BIGINT DEFAULT 0,
    speed_rx REAL DEFAULT 0,
    speed_tx REAL DEFAULT 0,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создание таблицы для уведомлений пользователей
CREATE TABLE IF NOT EXISTS user_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL, -- 'subscription_expiring', 'traffic_limit', 'payment_success', etc.
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    read_at TIMESTAMP WITH TIME ZONE
);

-- Создание таблицы для истории действий пользователей
CREATE TABLE IF NOT EXISTS user_activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL, -- 'login', 'download_config', 'view_traffic', etc.
    details JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_telegram_id ON orders(telegram_id);
CREATE INDEX IF NOT EXISTS idx_traffic_logs_user_id ON user_traffic_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_traffic_logs_public_key ON user_traffic_logs(public_key);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON user_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON user_notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_activity_log_user_id ON user_activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON user_activity_log(created_at);

-- Функция для очистки истекших сессий
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_sessions WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Функция для логирования активности пользователя
CREATE OR REPLACE FUNCTION log_user_activity(
    p_user_id INTEGER,
    p_action VARCHAR(100),
    p_details JSONB DEFAULT '{}'::jsonb,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO user_activity_log (user_id, action, details, ip_address, user_agent)
    VALUES (p_user_id, p_action, p_details, p_ip_address, p_user_agent);
END;
$$ LANGUAGE plpgsql;

-- Функция для создания уведомления пользователю
CREATE OR REPLACE FUNCTION create_user_notification(
    p_user_id INTEGER,
    p_type VARCHAR(50),
    p_title VARCHAR(255),
    p_message TEXT
)
RETURNS INTEGER AS $$
DECLARE
    notification_id INTEGER;
BEGIN
    INSERT INTO user_notifications (user_id, type, title, message)
    VALUES (p_user_id, p_type, p_title, p_message)
    RETURNING id INTO notification_id;
    RETURN notification_id;
END;
$$ LANGUAGE plpgsql;

-- Триггер для автоматического обновления last_activity в сессиях
CREATE OR REPLACE FUNCTION update_session_activity()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE user_sessions 
    SET last_activity = NOW() 
    WHERE user_id = NEW.user_id AND session_token = NEW.session_token;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создание триггера (будет активирован при логировании активности)
-- CREATE TRIGGER trigger_update_session_activity
--     AFTER INSERT ON user_activity_log
--     FOR EACH ROW
--     EXECUTE FUNCTION update_session_activity();

-- Комментарии к таблицам
COMMENT ON TABLE users IS 'Основная таблица пользователей с данными из Telegram';
COMMENT ON TABLE user_sessions IS 'Сессии пользователей для JWT токенов';
COMMENT ON TABLE telegram_auth_data IS 'Данные авторизации через Telegram Web App';
COMMENT ON TABLE user_traffic_logs IS 'Логи трафика пользователей';
COMMENT ON TABLE user_notifications IS 'Уведомления для пользователей';
COMMENT ON TABLE user_activity_log IS 'Лог активности пользователей';

-- Комментарии к полям
COMMENT ON COLUMN users.telegram_id IS 'ID пользователя в Telegram';
COMMENT ON COLUMN users.settings IS 'JSON с настройками пользователя';
COMMENT ON COLUMN user_sessions.session_token IS 'JWT токен сессии';
COMMENT ON COLUMN user_traffic_logs.public_key IS 'Публичный ключ WireGuard';
COMMENT ON COLUMN user_notifications.type IS 'Тип уведомления для группировки';

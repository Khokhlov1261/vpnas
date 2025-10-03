import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# -------------------
# App
# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 9000))
DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")
CONF_DIR = os.getenv("CONF_DIR", "/securelink/SecureLink/configs")

# -------------------
# Database
DATABASE_URL = os.getenv("DATABASE_URL")
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_DB = os.getenv("PG_DB", "securelink")
PG_USER = os.getenv("PG_USER", "securelink")
PG_PASSWORD = os.getenv("PG_PASSWORD")

# -------------------
# WireGuard
WG_CONFIG_PATH = os.getenv("WG_CONFIG_PATH", "/etc/wireguard/wg0.conf")
WG_INTERFACE = os.getenv("WG_INTERFACE", "wg0")
SERVER_PUBLIC_KEY = os.getenv("SERVER_PUBLIC_KEY")
SERVER_ENDPOINT = os.getenv("SERVER_ENDPOINT")  # <- подтянется из .env
DNS_ADDR = os.getenv("DNS_ADDR", "8.8.8.8")
WG_CLIENT_NETWORK_CIDR = os.getenv("WG_CLIENT_NETWORK_CIDR", "10.0.0.0/24")
WG_CLIENT_NETWORK6_CIDR = os.getenv("WG_CLIENT_NETWORK6_CIDR", "")

# -------------------
# YooKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# -------------------
# SMTP
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

# -------------------
# JWT / Telegram
JWT_SECRET = os.getenv("JWT_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL")
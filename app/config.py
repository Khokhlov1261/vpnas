import os
from dotenv import load_dotenv


load_dotenv()

# App
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "9000"))
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")

CONF_DIR = os.environ.get("CONF_DIR", "configs")

# DB
DATABASE_URL = os.environ.get("DATABASE_URL")
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_DB = os.environ.get("PG_DB", "securelink")
PG_USER = os.environ.get("PG_USER", "securelink")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "password")

# WireGuard
WG_CONFIG_PATH = os.environ.get("WG_CONFIG_PATH", "/etc/wireguard/wg0.conf")
WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
SERVER_PUBLIC_KEY = os.environ.get("SERVER_PUBLIC_KEY", "")
SERVER_ENDPOINT = os.environ.get("SERVER_ENDPOINT", "vpn.example.com:51820")
DNS_ADDR = os.environ.get("DNS_ADDR", "8.8.8.8")

# New: large pools via CIDR
# Example: 10.0.0.0/16 gives up to ~65534 IPv4 clients
WG_CLIENT_NETWORK_CIDR = os.environ.get("WG_CLIENT_NETWORK_CIDR", os.environ.get("WG_CLIENT_NET_CIDR", "10.0.0.0/24"))
# Optional IPv6 prefix for near-unlimited clients
WG_CLIENT_NETWORK6_CIDR = os.environ.get("WG_CLIENT_NETWORK6_CIDR", "")

# YooKassa
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY", "")

# SMTP
SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER)

# JWT / Telegram
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL")


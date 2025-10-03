import os
from dotenv import load_dotenv


load_dotenv()

import os

# App
APP_HOST = "0.0.0.0"
APP_PORT = 9000
DEBUG = True

CONF_DIR = "configs"

# DB
DATABASE_URL = None  # не использовался напрямую
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "securelink"
PG_USER = "securelink"
PG_PASSWORD = "uisdvh(uisdyv-sdjvsdjv12312-sdm)nbm.jdjd-hjshq"

# WireGuard
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
WG_INTERFACE = "wg0"
SERVER_PUBLIC_KEY = "JobMGKt7trpUtrwfs/XJ7OqIrjfJH4H4vfmsXjeiIX0="
SERVER_ENDPOINT = "truesocial.ru:51820"
DNS_ADDR = "8.8.8.8"

# New: large pools via CIDR
WG_CLIENT_NETWORK_CIDR = "10.0.0.0/24"
WG_CLIENT_NETWORK6_CIDR = ""

# YooKassa
YOOKASSA_SHOP_ID = "1172066"
YOOKASSA_SECRET_KEY = "live_ZEFkKFfMMXm4yQzVpsyRDwaNnTlx3jpTeGqX5Dkrezk"

# SMTP
SMTP_SERVER = "smtp.mail.yahoo.com"
SMTP_PORT = 587
SMTP_USER = "mailrealeden@yahoo.com"
SMTP_PASSWORD = "imkofnsgwnkiclaq"
FROM_EMAIL = SMTP_USER

# JWT / Telegram
JWT_SECRET = "uisdvh(uisdyv-sdjvsdjv12312-sdm)nbm.jdjd-hjshq"
TELEGRAM_BOT_TOKEN = "8271035383:AAHTbW40nfLzucEU7ZYWQziGv16kDx4ph5"
TELEGRAM_WEBHOOK_URL = None  # если не используешь вебхук


import os
import sys
import threading
import time
import subprocess
import logging
import json
import base64
import qrcode
from io import BytesIO
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from urllib.parse import quote, unquote
from flask import Flask, request, jsonify, render_template, send_file, url_for, Response
import psutil
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
# Postgres
import psycopg2
import psycopg2.pool
import psycopg2.extras
# Yookassa
from yookassa import Configuration, Payment
# User management
from user_manager import UserManager
from services.orders import OrderService, PLANS
from dotenv import load_dotenv

from app.db import init_db_pool as _init_db_pool, get_conn as _get_conn
from app import wg as wgmod

#

load_dotenv()  # это заставит Python читать .env

# ---------------------------
# CONFIG
# ---------------------------
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
# WireGuard / service settings
WG_CONFIG_PATH = os.getenv("WG_CONFIG_PATH", "/etc/wireguard/wg0.conf")
WG_INTERFACE = os.getenv("WG_INTERFACE", "wg0")
SERVER_PUBLIC_KEY = os.getenv("SERVER_PUBLIC_KEY")
SERVER_ENDPOINT = os.getenv("SERVER_ENDPOINT")
DNS_ADDR = os.getenv("DNS_ADDR", "8.8.8.8")
WG_CLIENT_NETWORK_CIDR = os.getenv("WG_CLIENT_NETWORK_CIDR", "10.0.0.0/24")
WG_CLIENT_NETWORK6_CIDR = os.getenv("WG_CLIENT_NETWORK6_CIDR", "")

# -------------------
# Yookassa credentials
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# Если используешь класс Configuration из SDK:
try:
    from yookassa import Configuration
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
except ImportError:
    pass  # если SDK нет — просто пропускаем

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


# Logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger("securelink")

# Ensure configs dir
os.makedirs(CONF_DIR, exist_ok=True)

# ---------------------------
# Postgres connection pool
# ---------------------------
user_manager = None

def init_db_pool():
    try:
        _init_db_pool()
    except Exception as e:
        logger.exception("Failed to initialize Postgres pool: %s", e)
        sys.exit(1)

def get_conn():
    return _get_conn()

# ---------------------------
# DB initialization (safe: won't clobber existing)
# ---------------------------
def init_db():
    """
    Create table if not exists. This is safe for existing DBs.
    """
    create_sql = """
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
        user_id INTEGER,
        telegram_id BIGINT,
        payment_method VARCHAR(50) DEFAULT 'yookassa',
        auto_renewal BOOLEAN DEFAULT FALSE
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
    logger.info("DB init (ensured orders table)")

# ---------------------------
# WireGuard helpers
# ---------------------------
def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def wg_set_peer(public_key: str, allowed_ips: str) -> bool:
    ok = wgmod.wg_set_peer(public_key, allowed_ips)
    if not ok:
        logger.error("wg_set_peer failed")
    return ok

def wg_remove_peer(public_key: str) -> bool:
    ok = wgmod.wg_remove_peer(public_key)
    if not ok:
        logger.error("wg_remove_peer failed")
    return ok

def append_peer_to_conf(public_key: str, client_ip: str):
    try:
        wgmod.append_peer_to_conf(public_key, client_ip)
        logger.info("Appended peer %s -> %s to %s", public_key, client_ip, WG_CONFIG_PATH)
    except Exception as e:
        logger.exception("Failed to append peer to conf: %s", e)

def get_used_ips() -> set:
    return wgmod.get_used_ips()

def get_next_free_ip() -> str:
    return wgmod.get_next_free_ip()

def wg_gen_keypair():
    return wgmod.wg_gen_keypair()

def parse_conf(conf_path: str):
    result = {"PrivateKey": None, "Address": None}
    if not os.path.exists(conf_path):
        return result
    with open(conf_path) as f:
        for line in f:
            if line.strip().startswith("PrivateKey"):
                result["PrivateKey"] = line.split("=",1)[1].strip()
            elif line.strip().startswith("Address"):
                result["Address"] = line.split("=",1)[1].strip()
    return result

# ---------------------------
# Client config creation
# ---------------------------
def create_client_conf(order_id: int, email: str, plan_name: str):
    private_key, public_key = wg_gen_keypair()
    client_ip = get_next_free_ip()

    if wg_set_peer(public_key, client_ip):
        append_peer_to_conf(public_key, client_ip)
        logger.info("Peer %s -> %s added for %s", public_key, client_ip, email)
    else:
        logger.warning("Failed to add peer for %s", email)

    conf_text = (
        f"[Interface]\nPrivateKey = {private_key}\nAddress = {client_ip}\nDNS = {DNS_ADDR}\n\n"
        f"[Peer]\nPublicKey = {SERVER_PUBLIC_KEY}\nEndpoint = {SERVER_ENDPOINT}\nAllowedIPs = 0.0.0.0/0\n"
        f"# Email: {email}\n# Plan: {plan_name}\n"
    )

    conf_path = os.path.join(CONF_DIR, f"wg_{order_id}.conf")
    with open(conf_path, "w") as f:
        f.write(conf_text)
    os.chmod(conf_path, 0o600)
    logger.info("Saved client config: %s", conf_path)
    return conf_path, public_key, client_ip

# ---------------------------
# Subscriptions checker (background)
# ---------------------------
def check_subscriptions():
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, public_key, expires_at FROM orders WHERE status='paid';")
            rows = cur.fetchall()
            for row in rows:
                order_id, public_key, expires_at = row
                if not expires_at:
                    continue
                try:
                    exp_dt = expires_at
                    if isinstance(exp_dt, str):
                        exp_dt = datetime.fromisoformat(exp_dt)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    logger.warning("Invalid expires_at for order %s: %s", order_id, expires_at)
                    continue
                if now > exp_dt and public_key:
                    if wg_remove_peer(public_key):
                        logger.info("Peer %s removed for order %s", public_key, order_id)
                    cur.execute("UPDATE orders SET status='expired' WHERE id=%s;", (order_id,))
        # commit by context manager

def subscription_loop():
    while True:
        try:
            check_subscriptions()
        except Exception as e:
            logger.exception("Subscription checker error: %s", e)
        time.sleep(10)

# ---------------------------
# Plans and order logic
# ---------------------------
PLANS = PLANS

def calculate_expiry_extended(plan_type: str, current_expiry):
    now = datetime.now(timezone.utc)
    base = now
    if current_expiry:
        try:
            exp_dt = current_expiry
            if isinstance(exp_dt, str):
                exp_dt = datetime.fromisoformat(exp_dt)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt > now:
                base = exp_dt
        except Exception:
            pass
    if plan_type == "month1":
        return (base + relativedelta(months=1)).isoformat()
    elif plan_type == "month6":
        return (base + relativedelta(months=6)).isoformat()
    elif plan_type == "year":
        return (base + relativedelta(years=1)).isoformat()
    return base.isoformat()

order_service: OrderService = None

def create_order_internal(email: str, plan_id: int):
    try:
        plan_name, price, duration = PLANS.get(plan_id, ("неизвестно", 0, None))
        if price <= 0:
            return None, None, "Некорректный тариф"

        # путь к конфигу
        conf_file = os.path.join(CONF_DIR, f"{email}_{plan_id}.conf")

        # генерация конфига
        generate_wireguard_conf(conf_file, email, plan_id)

        # запись в БД
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders (email, plan, status, conf_file)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email, plan) DO UPDATE
                        SET status=EXCLUDED.status,
                            conf_file=EXCLUDED.conf_file
                    RETURNING id;
                    """,
                    (email, plan_name, "pending", conf_file)
                )
                conn.commit()

        return conf_file, plan_name, None
    except Exception as e:
        logger.exception("Ошибка при создании заказа")
        return None, None, str(e)

# ---------------------------
# Flask app & routes
# ---------------------------
app = Flask(__name__)
def send_telegram_doc_and_qr(bot_token: str, chat_id: int, conf_file: str, plan_name: str):
    try:
        api = f"https://api.telegram.org/bot{bot_token}"
        caption = f"Тариф: {plan_name}\nИнструкция: установите WireGuard, импортируйте файл, включите."
        # sendDocument
        with open(conf_file, 'rb') as f:
            files = {"document": (os.path.basename(conf_file), f, "text/plain")}
            data = {"chat_id": str(chat_id), "caption": caption}
            requests.post(f"{api}/sendDocument", data=data, files=files, timeout=20)
        # sendPhoto (QR)
        with open(conf_file, 'r') as f:
            conf_text = f.read()
        buf = BytesIO()
        qrcode.make(conf_text).save(buf, "PNG")
        buf.seek(0)
        files = {"photo": (f"securelink_{chat_id}.png", buf, "image/png")}
        data = {"chat_id": str(chat_id), "caption": "QR для импорта"}
        requests.post(f"{api}/sendPhoto", data=data, files=files, timeout=20)
    except Exception:
        logger.exception("Failed to send to Telegram via HTTP API")
app.config["CONF_DIR"] = CONF_DIR

# ProxyFix if behind nginx
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Helper: send email with conf attachment
def send_conf_email(to_email, conf_path, expires_at=None):
    try:
        subject = "SecureLink — Ваша WireGuard конфигурация"
        body = "Здравствуйте!\n\nВ приложении находится ваш новый конфигурационный файл WireGuard."

        if expires_at:
            dt_utc = expires_at
            if isinstance(dt_utc, str):
                dt_utc = datetime.fromisoformat(dt_utc)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            # локализуем в МСК
            try:
                from zoneinfo import ZoneInfo
                dt_local = dt_utc.astimezone(ZoneInfo("Europe/Moscow"))
            except Exception:
                dt_local = dt_utc
            body += f"\n\nСрок действия вашей подписки (МСК) до: {dt_local.strftime('%Y-%m-%d %H:%M:%S')}"

        body += "\n\nПриятного пользования!"

        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with open(conf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(conf_path))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(conf_path)}"'
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())

        logger.info("Конфиг отправлен на почту: %s", to_email)
    except Exception as e:
        logger.exception("Ошибка при отправке конфигурации на почту: %s", e)

# Basic auth for admin
def check_auth(username, password):
    return username == os.environ.get("ADMIN_USER", "khokhlov1261") and password == os.environ.get("ADMIN_PASS", "uisdvh(uisdyv-sdjvsdjv12312-sdm)nbm.jdjd-hjshq")

def requires_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response('Нужна авторизация', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

def require_user_auth(f):
    """Декоратор для проверки авторизации пользователя через JWT"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Токен авторизации не предоставлен"}), 401
        
        token = auth_header.split(' ')[1]
        user_data = user_manager.validate_jwt_token(token)
        
        if not user_data:
            return jsonify({"error": "Недействительный токен авторизации"}), 401
        
        # Добавляем данные пользователя в request
        request.current_user = user_data
        return f(*args, **kwargs)
    return decorated

def get_current_user_id():
    """Получение ID текущего пользователя из request"""
    if hasattr(request, 'current_user'):
        return request.current_user['user_id']
    return None

# Routes (kept logic similar to original)
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    """Личный кабинет пользователя"""
    return render_template("dashboard.html")

@app.route("/demo")
def telegram_demo():
    """Демо страница для тестирования авторизации"""
    return render_template("telegram_demo.html")

@app.route("/auth")
def telegram_auth_page():
    """Страница авторизации через Telegram"""
    return render_template("telegram_auth.html")

# ==============================
# TELEGRAM AUTH ROUTES
# ==============================

@app.route("/auth/telegram", methods=["POST"])
def telegram_auth():
    """Авторизация через Telegram Web App"""
    try:
        data = request.json or {}
        init_data = data.get("init_data")
        
        if not init_data:
            return jsonify({"error": "Данные Telegram не предоставлены"}), 400
        
        if not TELEGRAM_BOT_TOKEN:
            return jsonify({"error": "Telegram Bot не настроен"}), 500
        
        # Валидация данных от Telegram
        if not user_manager.validate_telegram_data(init_data, TELEGRAM_BOT_TOKEN):
            return jsonify({"error": "Недействительные данные от Telegram"}), 400
        
        # Парсинг данных пользователя
        telegram_user = user_manager.parse_telegram_user_data(init_data)
        if not telegram_user:
            return jsonify({"error": "Не удалось получить данные пользователя"}), 400
        
        # Получение или создание пользователя
        user_data = user_manager.get_or_create_telegram_user(telegram_user)
        if not user_data:
            return jsonify({"error": "Ошибка создания пользователя"}), 500
        
        # Создание JWT токена
        token = user_manager.create_jwt_token(user_data['id'])
        if not token:
            return jsonify({"error": "Ошибка создания токена"}), 500
        
        return jsonify({
            "token": token,
            "user": {
                "id": user_data['id'],
                "username": user_data['username'],
                "first_name": user_data['first_name'],
                "last_name": user_data['last_name'],
                "language_code": user_data['language_code']
            }
        })

    except Exception as e:
        logger.exception("Ошибка авторизации через Telegram: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/auth/logout", methods=["POST"])
@require_user_auth
def logout():
    """Выход из системы"""
    try:
        auth_header = request.headers.get('Authorization')
        token = auth_header.split(' ')[1]
        
        if user_manager.revoke_user_session(token):
            return jsonify({"message": "Успешный выход из системы"})
        else:
            return jsonify({"error": "Ошибка выхода из системы"}), 500
            
    except Exception as e:
        logger.exception("Ошибка выхода: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/auth/me", methods=["GET"])
@require_user_auth
def get_current_user():
    """Получение данных текущего пользователя"""
    try:
        user_id = get_current_user_id()
        user_data = user_manager.get_user_by_id(user_id)
        
        if not user_data:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        return jsonify({
            "user": {
                "id": user_data['id'],
                "username": user_data['username'],
                "first_name": user_data['first_name'],
                "last_name": user_data['last_name'],
                "email": user_data['email'],
                "language_code": user_data['language_code'],
                "created_at": user_data['created_at'],
                "last_login": user_data['last_login'],
                "settings": user_data['settings']
            }
        })
        
    except Exception as e:
        logger.exception("Ошибка получения данных пользователя: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# ==============================
# USER DASHBOARD API
# ==============================

@app.route("/api/user/subscriptions", methods=["GET"])
@require_user_auth
def get_user_subscriptions():
    """Получение подписок пользователя"""
    try:
        user_id = get_current_user_id()
        subscriptions = user_manager.get_user_subscriptions(user_id)
        
        return jsonify({
            "subscriptions": subscriptions,
            "total": len(subscriptions)
        })
        
    except Exception as e:
        logger.exception("Ошибка получения подписок: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/api/user/traffic", methods=["GET"])
@require_user_auth
def get_user_traffic():
    """Получение статистики трафика пользователя"""
    try:
        user_id = get_current_user_id()
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Получаем активные подписки пользователя
                cur.execute("""
                    SELECT public_key, client_ip, plan, expires_at
                    FROM orders 
                    WHERE user_id = %s AND status = 'paid'
                    ORDER BY created_at DESC
                """, (user_id,))
                
                traffic_data = []
                wg_stats = get_wg_stats()
                
                for row in cur.fetchall():
                    public_key, client_ip, plan, expires_at = row
                    stats = wg_stats.get(public_key, {})
                    
                    # Проверяем, не истекла ли подписка
                    is_expired = False
                    if expires_at:
                        try:
                            exp_dt = expires_at
                            if isinstance(exp_dt, str):
                                exp_dt = datetime.fromisoformat(exp_dt)
                                if exp_dt.tzinfo is None:
                                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            is_expired = datetime.now(timezone.utc) > exp_dt
                        except Exception:
                            pass
                    
                    traffic_data.append({
                        "client_ip": client_ip,
                        "plan": plan,
                        "rx_bytes": stats.get("rx_bytes", 0),
                        "tx_bytes": stats.get("tx_bytes", 0),
                        "speed_rx": stats.get("speed_rx", 0),
                        "speed_tx": stats.get("speed_tx", 0),
                        "online": (time.time() - stats.get("last_seen", 0)) < 60 if stats.get("last_seen") else False,
                        "last_seen": stats.get("last_seen", 0),
                        "expires_at": expires_at.isoformat() if expires_at else None,
                        "is_expired": is_expired
                    })
        
        return jsonify({
            "traffic": traffic_data,
            "total_rx": sum(item["rx_bytes"] for item in traffic_data),
            "total_tx": sum(item["tx_bytes"] for item in traffic_data)
        })
        
    except Exception as e:
        logger.exception("Ошибка получения статистики трафика: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/api/user/configs", methods=["GET"])
@require_user_auth
def get_user_configs():
    """Получение конфигураций пользователя"""
    try:
        user_id = get_current_user_id()
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, plan, conf_file, created_at, expires_at, status
                    FROM orders 
                    WHERE user_id = %s AND conf_file IS NOT NULL
                    ORDER BY created_at DESC
                """, (user_id,))
                
                configs = []
                for row in cur.fetchall():
                    order_id, plan, conf_file, created_at, expires_at, status = row
                    
                    # Проверяем существование файла
                    has_file = os.path.exists(conf_file) if conf_file else False
                    
                    configs.append({
                        "id": order_id,
                        "plan": plan,
                        "created_at": created_at.isoformat() if created_at else None,
                        "expires_at": expires_at.isoformat() if expires_at else None,
                        "status": status,
                        "has_file": has_file,
                        "download_url": url_for("download", order_id=order_id) if has_file else None,
                        "qr_url": url_for("qr", order_id=order_id) if has_file else None
                    })
        
        return jsonify({
            "configs": configs,
            "total": len(configs)
        })
        
    except Exception as e:
        logger.exception("Ошибка получения конфигураций: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/api/user/notifications", methods=["GET"])
@require_user_auth
def get_user_notifications():
    """Получение уведомлений пользователя"""
    try:
        user_id = get_current_user_id()
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, type, title, message, is_read, created_at, read_at
                    FROM user_notifications 
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 50
                """, (user_id,))
                
                notifications = []
                for row in cur.fetchall():
                    notifications.append({
                        "id": row[0],
                        "type": row[1],
                        "title": row[2],
                        "message": row[3],
                        "is_read": row[4],
                        "created_at": row[5].isoformat() if row[5] else None,
                        "read_at": row[6].isoformat() if row[6] else None
                    })
        
        return jsonify({
            "notifications": notifications,
            "unread_count": sum(1 for n in notifications if not n["is_read"])
        })
        
    except Exception as e:
        logger.exception("Ошибка получения уведомлений: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/api/user/notifications/<int:notification_id>/read", methods=["POST"])
@require_user_auth
def mark_notification_read(notification_id):
    """Отметить уведомление как прочитанное"""
    try:
        user_id = get_current_user_id()
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_notifications 
                    SET is_read = TRUE, read_at = %s
                    WHERE id = %s AND user_id = %s
                """, (datetime.now(timezone.utc), notification_id, user_id))
                
                if cur.rowcount == 0:
                    return jsonify({"error": "Уведомление не найдено"}), 404
        
        return jsonify({"message": "Уведомление отмечено как прочитанное"})
        
    except Exception as e:
        logger.exception("Ошибка обновления уведомления: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@app.route("/create-order", methods=["POST"])
def create_order():
    data = request.json or {}
    email = data.get("email")
    plan_id = data.get("plan_id")

    if not isinstance(plan_id, int):
        return jsonify({"error": "Неверный plan_id"}), 400

    plan_name, price, _ = PLANS.get(plan_id, ("неизвестно", 0, None))
    if not email or price <= 0:
        return jsonify({"error": "Неверные данные"}), 400

    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders(email, plan, price, status, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                (email, plan_name, price, "pending", now.isoformat())
            )
            order_id = cur.fetchone()[0]

    order_token = request.args.get("order", "").strip()
    if not order_token:
        return "Токен не передан", 403

    return jsonify({
        "order_token": order_token,
        "order_id": order_id,
        "plan_name": plan_name,
        "price": price
    })

@app.route("/download/<int:order_id>")
def download(order_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT conf_file, status FROM orders WHERE id=%s;", (order_id,))
            row = cur.fetchone()
            if not row:
                return ".conf не найден", 404
            conf_path, status = row
            if status != "paid":
                return ".conf не найден или оплата не завершена", 403
    return send_file(conf_path, as_attachment=True)

@app.route("/qr/<int:order_id>")
def qr(order_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT conf_file FROM orders WHERE id=%s;", (order_id,))
            row = cur.fetchone()
            if not row or not row[0] or not os.path.exists(row[0]):
                return "Конфиг не найден", 404
            conf_text = open(row[0]).read()
    buf = BytesIO()
    qrcode.make(conf_text).save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/check-subscription", methods=["POST"])
def check_subscription():
    email = (request.json or {}).get("email")
    if not email:
        return jsonify({"error": "Email не указан"}), 400
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, expires_at FROM orders WHERE email=%s ORDER BY id DESC LIMIT 1;", (email,))
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "не найдена"}), 200
            status, expires_at = row
            if expires_at:
                try:
                    exp_dt = expires_at
                    if isinstance(exp_dt, str):
                        exp_dt = datetime.fromisoformat(exp_dt)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > exp_dt:
                        status = "истекла"
                except Exception:
                    pass
    return jsonify({"status": status, "expires_at": expires_at})

# Yookassa integration
@app.route("/create-payment", methods=["POST"])
def create_payment():
    data = request.json or {}
    email = (data.get("email") or "").strip()
    plan_id = data.get("plan_id")

    if not isinstance(plan_id, int):
        return jsonify({"error": "Некорректный plan_id"}), 400

    plan_name, price, _ = PLANS.get(plan_id, ("неизвестно", 0, None))
    if not email or price <= 0:
        return jsonify({"error": "Неверные данные"}), 400

    try:
        # Возврат в Telegram через deep-link после оплаты
        # Передаём plan_id и phone (в нашем поле email) для последующей выдачи конфига
        return_url = f"https://t.me/{os.environ.get('BOT_USERNAME','Securelinkvpn_bot')}?start=paid_{plan_id}_{quote(email)}"

        payment = Payment.create({
            "amount": {"value": f"{price:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": f"Оплата тарифа {plan_name} для {email}",
            "metadata": {"email": email, "plan_id": plan_id},
        })

        logger.info("Created payment: %s", payment.id)
        return jsonify({"confirmation_url": payment.confirmation.confirmation_url})

    except Exception as e:
        logger.exception("Ошибка при создании платежа")
        return jsonify({"error": str(e)}), 500

@app.route("/bot/link-email", methods=["POST"])
def bot_link_email():
    """Привязывает telegram_id к email (для автодоставки конфига в боте)."""
    try:
        data = request.json or {}
        email = (data.get("email") or "").strip()
        telegram_id = data.get("telegram_id")
        if not email or not telegram_id:
            return jsonify({"error": "email и telegram_id обязательны"}), 400
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE orders SET telegram_id=%s WHERE email=%s AND status IN ('pending','paid');",
                    (telegram_id, email)
                )
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("link-email error: %s", e)
        return jsonify({"error": "internal"}), 500

@app.route("/yookassa-webhook", methods=["POST"])
def yookassa_webhook():
    try:
        event = request.json
        logger.info("Webhook received: %s", event)

        if not event or "object" not in event:
            return jsonify({"error": "Неверный формат"}), 400

        payment = event["object"]
        if payment.get("status") == "succeeded":
            email = payment.get("metadata", {}).get("email")
            plan_id = payment.get("metadata", {}).get("plan_id")

            if email and plan_id:
                try:
                    plan_id = int(plan_id)

                    # создаём заказ и получаем путь к конфигу
                    conf_file, plan_name, err = create_order_internal(email, plan_id)
                    if err or not conf_file:
                        logger.error("Ошибка при создании заказа: %s", err or "conf_file is empty")
                        return jsonify({"error": "Не удалось создать заказ"}), 500

                    # обновляем заказ как оплаченный
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE orders
                                SET status='paid', conf_file=%s
                                WHERE email=%s AND plan=%s
                                RETURNING id, telegram_id;
                                """,
                                (conf_file, email, plan_name)
                            )
                            row = cur.fetchone()
                            conn.commit()

                    if row:
                        order_id, telegram_id = row
                        bot_token = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")

                        # если юзер уже запускал бота → отправляем конфиг
                        if bot_token and telegram_id and os.path.exists(conf_file):
                            try:
                                send_telegram_doc_and_qr(bot_token, int(telegram_id), conf_file, plan_name)
                            except Exception:
                                logger.exception("Не удалось отправить конфиг в Telegram")
                        else:
                            logger.info("telegram_id отсутствует — конфиг доступен только в ЛК")

                except Exception:
                    logger.exception("Ошибка обработки webhook")

        return jsonify({"status": "ok"})

    except Exception:
        logger.exception("Ошибка в webhook")
        return jsonify({"error": "internal"}), 500


@app.route("/payment-callback")
def payment_callback():
    email = request.args.get("email")
    plan_id = request.args.get("plan_id")
    if not email or not plan_id:
        return "Ошибка: данные не переданы", 400
    try:
        plan_id = int(plan_id)
    except Exception:
        return "Ошибка: некорректный plan_id", 400

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM orders WHERE email=%s AND plan=%s AND status='paid' ORDER BY id DESC LIMIT 1;",
                (email, PLANS.get(plan_id, ("", 0, ""))[0])
            )
            row = cur.fetchone()
            if not row:
                return "Оплата не завершена", 403
            order_id = row[0]
            token = base64.urlsafe_b64encode(os.urandom(24)).decode()
            cur.execute("UPDATE orders SET access_token=%s WHERE id=%s;", (token, order_id))

    token_safe = quote(token)
    return f"""
    <script>
        window.location.href = "/config.html?order={token_safe}";
    </script>
    """

@app.route("/config.html")
def config_page():
    order_token = request.args.get("order", "").strip()
    if not order_token:
        return "Токен не передан", 403

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, conf_file FROM orders WHERE access_token=%s AND status='paid';", (order_token,))
            row = cur.fetchone()
            if not row:
                return "Токен недействителен или уже использован", 403
            order_id, conf_path = row
            cur.execute("UPDATE orders SET access_token=NULL WHERE id=%s;", (order_id,))

    if not os.path.exists(conf_path):
        return "Файл конфигурации отсутствует", 404

    with open(conf_path) as f:
        conf_text = f.read()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT plan, price FROM orders WHERE id=%s;", (order_id,))
            row = cur.fetchone()
            order = {"id": order_id, "plan": {"name": row[0], "price": float(row[1])} if row else {"name": "Неизвестно", "price": 0}}

    return render_template(
        "config.html",
        conf_text=conf_text,
        order=order,
        download_url=url_for("download", order_id=order_id),
        qr_url=url_for("qr", order_id=order_id)
    )

# Admin endpoints & stats
@app.route("/admin")
@requires_auth
def admin_dashboard():
    return render_template("admin.html")

@app.route("/admin/stats")
@requires_auth
def admin_stats():
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    wg_stats = get_wg_stats()
    now_ts = time.time()
    clients = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT email, public_key, client_ip, plan, created_at, expires_at FROM orders WHERE status='paid';")
            for row in cur.fetchall():
                email, pubkey, ip, plan, created, expires = row
                rx = wg_stats.get(pubkey, {}).get("rx_bytes", 0)
                tx = wg_stats.get(pubkey, {}).get("tx_bytes", 0)
                speed_rx = wg_stats.get(pubkey, {}).get("speed_rx", 0)
                speed_tx = wg_stats.get(pubkey, {}).get("speed_tx", 0)
                last_seen = wg_stats.get(pubkey, {}).get("last_seen", 0)
                online = (now_ts - last_seen) < 60
                clients.append({
                    "email": email,
                    "public_key": pubkey,
                    "client_ip": ip,
                    "plan": plan,
                    "rx_bytes": rx,
                    "tx_bytes": tx,
                    "speed_rx": speed_rx,
                    "speed_tx": speed_tx,
                    "online": online,
                    "last_seen": last_seen,
                    "start_date": created,
                    "end_date": expires
                })
    return jsonify({
        "cpu_percent": cpu,
        "ram_percent": ram,
        "disk_percent": disk,
        "clients": clients
    })

@app.route("/admin/delete/<path:public_key>", methods=["POST"])
@requires_auth
def delete_client(public_key):
    try:
        public_key = unquote(public_key)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT conf_file FROM orders WHERE public_key=%s LIMIT 1;", (public_key,))
                row = cur.fetchone()
                if row:
                    conf_file = row[0]
                    wg_remove_peer(public_key)
                    if conf_file and os.path.exists(conf_file):
                        os.remove(conf_file)
                    cur.execute("UPDATE orders SET conf_file=NULL, status='expired' WHERE public_key=%s;", (public_key,))
        logger.info("Клиент %s удалён", public_key)
        return jsonify({"status": "ok"})
    except Exception:
        logger.exception("Ошибка при удалении клиента")
        return jsonify({"status": "error"}), 500

# WG stats (transfer)
wg_prev_stats = {}
wg_prev_time = time.time()

def get_wg_stats():
    global wg_prev_stats, wg_prev_time
    stats = {}
    res = subprocess.run(["wg", "show", WG_INTERFACE, "transfer"], capture_output=True, text=True)
    now = time.time()
    if res.returncode == 0:
        for line in res.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) == 3:
                pubkey, rx, tx = parts
                try:
                    rx = int(rx); tx = int(tx)
                except Exception:
                    continue
                prev = wg_prev_stats.get(pubkey, {"rx": rx, "tx": tx, "last_seen": now})
                dt = max(now - wg_prev_time, 1)
                speed_rx = (rx - prev["rx"]) / dt
                speed_tx = (tx - prev["tx"]) / dt
                stats[pubkey] = {"rx_bytes": rx, "tx_bytes": tx, "speed_rx": speed_rx, "speed_tx": speed_tx, "last_seen": prev.get("last_seen", now)}
                if speed_rx > 0 or speed_tx > 0:
                    stats[pubkey]["last_seen"] = now
    wg_prev_stats = {k: {"rx": v["rx_bytes"], "tx": v["tx_bytes"], "last_seen": v["last_seen"]} for k,v in stats.items()}
    wg_prev_time = now
    return stats

# Free trial endpoint
@app.route("/free-trial", methods=["POST"])
def free_trial():
    data = request.json or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "Email не указан"}), 400

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM orders WHERE email=%s AND plan=%s LIMIT 1;", (email, "3 дня бесплатно"))
            if cur.fetchone():
                return jsonify({"error": "Вы уже использовали бесплатный пробный период"}), 400

            now = datetime.now(timezone.utc)
            expires_at = (now + timedelta(days=3)).isoformat()
            plan_name = "3 дня бесплатно"
            price = 0.0

            cur.execute(
                "INSERT INTO orders(email, plan, price, status, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                (email, plan_name, price, "paid", now.isoformat(), expires_at)
            )
            order_id = cur.fetchone()[0]
            conf_path, public_key, client_ip = create_client_conf(order_id, email, plan_name)
            cur.execute("UPDATE orders SET conf_file=%s, public_key=%s, client_ip=%s WHERE id=%s;", (conf_path, public_key, client_ip, order_id))

    try:
        send_conf_email(email, conf_path, expires_at)
    except Exception:
        logger.exception("Failed to send free-trial email")

    return jsonify({"message": "Бесплатный пробный период активирован! Конфигурация отправлена на email (Иногда письмо приходит в СПАМ)."})


import os
import secrets

CONF_DIR = os.environ.get("CONF_DIR", "configs")

def generate_wireguard_conf(conf_path: str, email: str, plan_id: int):
    """Генерация файла WireGuard-конфига"""
    private_key = secrets.token_urlsafe(32)[:32]  # псевдо-ключ для примера
    public_key = ""  # можно добавить если будешь хранить
    endpoint = os.environ.get("WG_ENDPOINT", "vpn.example.com:51820")

    conf_text = f"""[Interface]
PrivateKey = {private_key}
Address = 10.0.{plan_id}.{secrets.randbelow(200)+2}/32
DNS = 8.8.8.8

[Peer]
PublicKey = {public_key}
Endpoint = {endpoint}
AllowedIPs = 0.0.0.0/0
# Email: {email}
# Plan: {plan_id}
"""

    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
    with open(conf_path, "w") as f:
        f.write(conf_text)

    return conf_path


# ---------------------------
# Startup
# ---------------------------
def start_background_tasks():
    t = threading.Thread(target=subscription_loop, daemon=True)
    t.start()
    logger.info("Subscription checker started")


# ProxyFix if behind nginx
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# init DB pool also when imported (Gunicorn case)
if True:
    init_db_pool()
    init_db()
    user_manager = UserManager(get_conn)
    # Инициализация общего OrderService
    order_service = OrderService(
        get_conn,
        wg_set_peer=wg_set_peer,
        append_peer_to_conf=append_peer_to_conf,
        wg_remove_peer=wg_remove_peer,
        parse_conf=parse_conf,
        send_conf_email=send_conf_email,
        wg_gen_keypair=wg_gen_keypair,
        get_next_free_ip=get_next_free_ip,
        conf_dir=CONF_DIR,
        server_public_key=SERVER_PUBLIC_KEY,
        server_endpoint=SERVER_ENDPOINT,
        dns_addr=DNS_ADDR,
    )
    start_background_tasks()

# ---------------------------
# Startup (only for local run)
# ---------------------------
if __name__ == "__main__":
    logger.info("Starting app on %s:%s", APP_HOST, APP_PORT)
    app.run(host=APP_HOST, port=APP_PORT, debug=DEBUG)




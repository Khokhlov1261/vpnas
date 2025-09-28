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

from dotenv import load_dotenv
import os

load_dotenv()  # это заставит Python читать .env
# ---------------------------
# CONFIG
# ---------------------------
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "9000"))
DEBUG = os.environ.get("DEBUG", "true").lower() in ("1", "true", "yes")

CONF_DIR = os.environ.get("CONF_DIR", "configs")
# Для sqlite у тебя было orders.db — теперь берем Postgres URL:
DATABASE_URL = os.environ.get("DATABASE_URL")  # preferred
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_DB = os.environ.get("PG_DB", "securelink")
PG_USER = os.environ.get("PG_USER", "securelink")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "password")

# WireGuard / service settings
WG_CONFIG_PATH = os.environ.get("WG_CONFIG_PATH", "/etc/wireguard/wg0.conf")
WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
SERVER_PUBLIC_KEY = os.environ.get("SERVER_PUBLIC_KEY", "JobMGKt7trpUtrwfs/XJ7OqIrjfJH4H4vfmsXjeiIX0=")
SERVER_ENDPOINT = os.environ.get("SERVER_ENDPOINT", "secure-link.ru:51820")
WG_CLIENT_NET_PREFIX = os.environ.get("WG_CLIENT_NET_PREFIX", "10.0.0.")
WG_CLIENT_MIN = int(os.environ.get("WG_CLIENT_MIN", 2))
WG_CLIENT_MAX = int(os.environ.get("WG_CLIENT_MAX", 254))
DNS_ADDR = os.environ.get("DNS_ADDR", "8.8.8.8")

# Yookassa credentials
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID", "1172066")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY", "live_ZEFkKFfMMXm4yQzVpsyRDwaNnTlx3jpTeGqX5Dkrezk")
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# SMTP
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.mail.yahoo.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "mailrealeden@yahoo.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "imkofnsgwnkiclaq")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER)

# JWT and Telegram
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-in-production")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL")

# Logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger("securelink")

# Ensure configs dir
os.makedirs(CONF_DIR, exist_ok=True)

# ---------------------------
# Postgres connection pool
# ---------------------------
POOL = None
user_manager = None

def init_db_pool():
    global POOL, user_manager
    if DATABASE_URL:
        conninfo = DATABASE_URL
    else:
        conninfo = f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} user={PG_USER} password={PG_PASSWORD}"
    try:
        POOL = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=conninfo)
        user_manager = UserManager(get_conn)
        logger.info("Postgres pool and user manager initialized")
    except Exception as e:
        logger.exception("Failed to initialize Postgres pool: %s", e)
        sys.exit(1)

def get_conn():
    """
    Context manager that yields a connection from pool and returns it after use.
    Use: with get_conn() as conn: ...
    """
    class _ConnCtx:
        def __enter__(self):
            self.conn = POOL.getconn()
            # use autocommit=False by default; we commit explicitly where needed
            self.conn.autocommit = False
            return self.conn
        def __exit__(self, exc_type, exc, tb):
            try:
                if exc_type:
                    self.conn.rollback()
                else:
                    self.conn.commit()
            finally:
                POOL.putconn(self.conn)
    return _ConnCtx()

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
        access_token TEXT
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
    return subprocess.run(cmd, capture_output=True, text=True)t

def wg_set_peer(public_key: str, allowed_ips: str) -> bool:
    res = run_cmd(["wg", "set", WG_INTERFACE, "peer", public_key, "allowed-ips", allowed_ips])
    if res.returncode != 0:
        logger.error("wg_set_peer failed: %s", (res.stderr or res.stdout).strip())
        return False
    return True

def wg_remove_peer(public_key: str) -> bool:
    res = run_cmd(["wg", "set", WG_INTERFACE, "peer", public_key, "remove"])
    if res.returncode != 0:
        logger.error("wg_remove_peer failed: %s", (res.stderr or res.stdout).strip())
        return False
    return True

def append_peer_to_conf(public_key: str, client_ip: str):
    try:
        if os.path.exists(WG_CONFIG_PATH):
            with open(WG_CONFIG_PATH, "r") as f:
                contents = f.read()
            if public_key in contents:
                return
        with open(WG_CONFIG_PATH, "a") as f:
            f.write(f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {client_ip}\n")
        logger.info("Appended peer %s -> %s to %s", public_key, client_ip, WG_CONFIG_PATH)
    except Exception as e:
        logger.exception("Failed to append peer to conf: %s", e)

def get_used_ips() -> set:
    ips = set()
    if os.path.exists(WG_CONFIG_PATH):
        with open(WG_CONFIG_PATH) as f:
            for line in f:
                if line.strip().startswith("AllowedIPs"):
                    ip = line.split("=", 1)[1].strip().split("/")[0]
                    ips.add(ip)
    # also take any client_ip from DB
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT client_ip FROM orders WHERE client_ip IS NOT NULL;")
            for row in cur.fetchall():
                ip = row[0]
                if ip:
                    ips.add(ip.split("/")[0])
    return ips

def get_next_free_ip() -> str:
    used = get_used_ips()
    for i in range(WG_CLIENT_MIN, WG_CLIENT_MAX + 1):
        ip = f"{WG_CLIENT_NET_PREFIX}{i}"
        if ip not in used:
            return f"{ip}/32"
    raise RuntimeError("No free IP addresses left")

def wg_gen_keypair():
    private = subprocess.check_output(["wg", "genkey"]).decode().strip()
    public = subprocess.check_output(["wg", "pubkey"], input=private.encode()).decode().strip()
    return private, public

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
PLANS = {
    1: ("1 месяц", 99.0, "month1"),
    2: ("6 месяцев", 499.0, "month6"),
    3: ("1 год", 999.0, "year"),
}

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

def create_order_internal(email: str, plan_id: int, user_id: int = None, telegram_id: int = None):
    """
    Main logic for creating/updating orders after payment (webhook).
    Works with existing DB table structure.
    Returns (token, None) or (None, error_message)
    """
    try:
        plan_name, price, plan_type = PLANS.get(plan_id, ("неизвестно", 0, None))
        if not email or price <= 0:
            return None, "Неверные данные"

        now = datetime.now(timezone.utc)

        with get_conn() as conn:
            with conn.cursor() as cur:
                # get last order for this email
                cur.execute(
                    "SELECT id, conf_file, public_key, client_ip, status, expires_at "
                    "FROM orders WHERE email=%s ORDER BY id DESC LIMIT 1;",
                    (email,)
                )
                row = cur.fetchone()
                current_expiry = None

                if row:
                    order_id, conf_file, public_key, client_ip, status, current_expiry = row

                    # Если конфиг отсутствует — создаём новый
                    if not conf_file or not os.path.exists(conf_file):
                        conf_path, public_key, client_ip = create_client_conf(order_id, email, plan_name)
                        cur.execute(
                            "UPDATE orders SET conf_file=%s, public_key=%s, client_ip=%s WHERE id=%s;",
                            (conf_path, public_key, client_ip, order_id)
                        )
                        logger.info("Updated order %s with new conf", order_id)
                        # отправляем письмо
                        try:
                            send_conf_email(email, conf_path)
                        except Exception:
                            logger.exception("Failed to send conf email")

                    # Восстанавливаем peer и статус для истекшего заказа
                    if status == "expired":
                        if conf_file and os.path.exists(conf_file):
                            conf_path = conf_file
                            fields = parse_conf(conf_path)
                            private_key = fields.get("PrivateKey")
                            address = fields.get("Address")
                            if not public_key and private_key:
                                try:
                                    public_key = subprocess.check_output(
                                        ["wg", "pubkey"], input=private_key.encode()
                                    ).decode().strip()
                                except Exception as e:
                                    logger.exception("Failed to derive public key: %s", e)
                            if address and public_key:
                                wg_set_peer(public_key, address)
                                append_peer_to_conf(public_key, address)
                            cur.execute(
                                "UPDATE orders SET status='paid', public_key=COALESCE(public_key,%s), "
                                "client_ip=COALESCE(client_ip,%s) WHERE id=%s;",
                                (public_key, address, order_id)
                            )
                            logger.info("Reactivated expired order %s", order_id)
                            try:
                                send_conf_email(email, conf_path)
                            except Exception:
                                logger.exception("Failed to send conf email on reactivation")

                expires_at = calculate_expiry_extended(plan_type, current_expiry)

                # Обновляем существующий заказ или создаём новый
                if row:
                    cur.execute(
                        "UPDATE orders SET expires_at=%s, plan=%s, price=%s, status='paid' WHERE id=%s;",
                        (expires_at, plan_name, price, order_id)
                    )
                    logger.info("Extended order %s until %s", order_id, expires_at)
                else:
                    cur.execute(
                        "INSERT INTO orders(email, plan, price, status, created_at, expires_at, user_id, telegram_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;",
                        (email, plan_name, price, "paid", now.isoformat(), expires_at, user_id, telegram_id)
                    )
                    order_id = cur.fetchone()[0]
                    conf_path, public_key, client_ip = create_client_conf(order_id, email, plan_name)
                    cur.execute(
                        "UPDATE orders SET conf_file=%s, public_key=%s, client_ip=%s WHERE id=%s;",
                        (conf_path, public_key, client_ip, order_id)
                    )
                    logger.info("Created new order %s", order_id)
                    try:
                        send_conf_email(email, conf_path)
                    except Exception:
                        logger.exception("Failed to send conf email on new order")

        token_data = {
            "id": order_id,
            "email": email,
            "plan": {"name": plan_name, "price": float(price)},
            "status": "paid"
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        return token, None

    except Exception as e:
        logger.exception("Ошибка создания заказа")
        return None, str(e)

# ---------------------------
# Flask app & routes
# ---------------------------
app = Flask(__name__)
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
        return_url = f"http://secure-link.ru/payment-callback?email={quote(email)}&plan_id={plan_id}"

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
                    token, err = create_order_internal(email, plan_id)
                    if err:
                        logger.error("Ошибка при создании заказа из webhook: %s", err)
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
if POOL is None:
    init_db_pool()
    init_db()
    start_background_tasks()

# ---------------------------
# Startup (only for local run)
# ---------------------------
if __name__ == "__main__":
    logger.info("Starting app on %s:%s", APP_HOST, APP_PORT)
    app.run(host=APP_HOST, port=APP_PORT, debug=DEBUG)




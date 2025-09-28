#!/usr/bin/env python3
"""
Flask service for WireGuard subscription management.
Preserves original logic with improvements in structure and error handling.
"""
#
import os
import sqlite3
import threading
import time
import subprocess
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from flask import Flask, request, jsonify, render_template, send_file, url_for
import qrcode
from io import BytesIO
import json
import base64
import logging
from yookassa import Configuration, Payment  # 🔑 ЮKassa SDK
from urllib.parse import quote
from functools import wraps
from flask import request, Response
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import redirect, url_for
from urllib.parse import unquote
import psutil
import subprocess
import time
from flask import jsonify
from urllib.parse import quote

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

SMTP_SERVER = "smtp.mail.yahoo.com"  # SMTP сервер Yahoo
SMTP_PORT = 587                       # порт TLS
SMTP_USER = "mailrealeden@yahoo.com" # ваш Yahoo email
SMTP_PASSWORD = "imkofnsgwnkiclaq"
FROM_EMAIL = "mailrealeden@yahoo.com"


# Сохраняем предыдущие значения трафика для расчета скорости
wg_prev_stats = {}
wg_prev_time = time.time()

# ---------------------------
# CONFIGURATION
# ---------------------------
APP_HOST = "0.0.0.0"
APP_PORT = 8000
DEBUG = True

CONF_DIR = "configs"
DB_FILE = "orders.db"

WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
WG_INTERFACE = "wg0"
SERVER_PUBLIC_KEY = "JobMGKt7trpUtrwfs/XJ7OqIrjfJH4H4vfmsXjeiIX0="
SERVER_ENDPOINT = "secure-link.ru:51820"
WG_CLIENT_NET_PREFIX = "10.0.0."
WG_CLIENT_MIN = 2
WG_CLIENT_MAX = 254 # всего клиентов может быть подключено
DNS_ADDR = "8.8.8.8"

# 🔑 ЮKassa  ключи
YOOKASSA_SHOP_ID = "1153646"  #  shopId
YOOKASSA_SECRET_KEY = "live_IEJ7tPhQseCj2w1J8kP8fIBoe9HSOC8-NBqMofXbywQ"

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

os.makedirs(CONF_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

app = Flask(__name__)
app.config["CONF_DIR"] = CONF_DIR
# --- ProxyFix для реальных IP через Nginx ---
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# ---------------------------
# DATABASE
# ---------------------------
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                plan TEXT,
                price REAL,
                status TEXT,
                conf_file TEXT,
                created_at TEXT,
                expires_at TEXT,
                public_key TEXT,
                client_ip TEXT,
                access_token TEXT  -- новая колонка для одноразового токена
            )
        """)
        # Убедимся, что все колонки на месте
        columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()]
        for col in ["public_key", "client_ip", "access_token"]:
            if col not in columns:
                try:
                    conn.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT")
                except Exception:
                    pass


# ---------------------------
# WIREGUARD HELPERS
# ---------------------------
def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def wg_set_peer(public_key: str, allowed_ips: str) -> bool:
    res = run_cmd(["wg", "set", WG_INTERFACE, "peer", public_key, "allowed-ips", allowed_ips])
    if res.returncode != 0:
        logging.error("wg_set_peer failed: %s", res.stderr.strip() or res.stdout.strip())
        return False
    return True

def wg_remove_peer(public_key: str) -> bool:
    res = run_cmd(["wg", "set", WG_INTERFACE, "peer", public_key, "remove"])
    if res.returncode != 0:
        logging.error("wg_remove_peer failed: %s", res.stderr.strip() or res.stdout.strip())
        return False
    return True

def append_peer_to_conf(public_key: str, client_ip: str):
    if os.path.exists(WG_CONFIG_PATH):
        with open(WG_CONFIG_PATH) as f:
            if public_key in f.read():
                return
    with open(WG_CONFIG_PATH, "a") as f:
        f.write(f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {client_ip}\n")
    logging.info("Appended peer %s -> %s to %s", public_key, client_ip, WG_CONFIG_PATH)

def get_used_ips() -> set:
    ips = set()
    if os.path.exists(WG_CONFIG_PATH):
        with open(WG_CONFIG_PATH) as f:
            for line in f:
                if line.strip().startswith("AllowedIPs"):
                    ip = line.split("=", 1)[1].strip().split("/")[0]
                    ips.add(ip)
    with sqlite3.connect(DB_FILE) as conn:
        for (ip,) in conn.execute("SELECT client_ip FROM orders WHERE client_ip IS NOT NULL"):
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
# CLIENT CONFIGURATION
# ---------------------------
def create_client_conf(order_id: int, email: str, plan_name: str):
    private_key, public_key = wg_gen_keypair()
    client_ip = get_next_free_ip()

    if wg_set_peer(public_key, client_ip):
        append_peer_to_conf(public_key, client_ip)
        logging.info("Peer %s -> %s added for %s", public_key, client_ip, email)
    else:
        logging.warning("Failed to add peer for %s", email)

    conf_text = (
        f"[Interface]\nPrivateKey = {private_key}\nAddress = {client_ip}\nDNS = {DNS_ADDR}\n\n"
        f"[Peer]\nPublicKey = {SERVER_PUBLIC_KEY}\nEndpoint = {SERVER_ENDPOINT}\nAllowedIPs = 0.0.0.0/0\n"
        f"# Email: {email}\n# Plan: {plan_name}\n"
    )

    conf_path = os.path.join(CONF_DIR, f"wg_{order_id}.conf")
    with open(conf_path, "w") as f:
        f.write(conf_text)
    os.chmod(conf_path, 0o600)
    logging.info("Saved client config: %s", conf_path)
    return conf_path, public_key, client_ip

# ---------------------------
# SUBSCRIPTION CHECKER
# ---------------------------
def check_subscriptions():
    now = datetime.now(timezone.utc)
    with sqlite3.connect(DB_FILE) as conn:
        for order_id, public_key, expires_at in conn.execute(
            "SELECT id, public_key, expires_at FROM orders WHERE status='paid'"
        ):
            if not expires_at:
                continue
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            except Exception:
                logging.warning("Invalid expires_at for order %s: %s", order_id, expires_at)
                continue
            if now > exp_dt and public_key:
                if wg_remove_peer(public_key):
                    logging.info("Peer %s removed for order %s", public_key, order_id)
                conn.execute("UPDATE orders SET status='expired' WHERE id=?", (order_id,))
        conn.commit()

def subscription_loop():
    while True:
        try:
            check_subscriptions()
        except Exception as e:
            logging.exception("Subscription checker error: %s", e)
        time.sleep(10)

threading.Thread(target=subscription_loop, daemon=True).start()

# ---------------------------
# PLANS AND ORDER LOGIC
# ---------------------------
PLANS = {
    1: ("1 месяц", 99.0, "month1"),
    2: ("6 месяцев", 499.0, "month6"),
    3: ("1 год", 999.0, "year"),
}

def calculate_expiry_extended(plan_type: str, current_expiry: str | None):
    now = datetime.now(timezone.utc)
    base = now
    if current_expiry:
        try:
            exp_dt = datetime.fromisoformat(current_expiry)
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

def create_order_internal(email: str, plan_id: int):
    try:
        plan_name, price, plan_type = PLANS.get(plan_id, ("неизвестно", 0, None))
        if not email or price <= 0:
            return None, "Неверные данные"

        now = datetime.now(timezone.utc)
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, conf_file, public_key, client_ip, status, expires_at "
                "FROM orders WHERE email=? ORDER BY id DESC LIMIT 1", (email,)
            )
            row = cur.fetchone()
            current_expiry = None

            if row:
                order_id, conf_file, public_key, client_ip, status, current_expiry = row

                # Если конфиг отсутствует — создаём новый
                if not conf_file or not os.path.exists(conf_file):
                    conf_path, public_key, client_ip = create_client_conf(order_id, email, plan_name)
                    cur.execute(
                        "UPDATE orders SET conf_file=?, public_key=?, client_ip=? WHERE id=?",
                        (conf_path, public_key, client_ip, order_id)
                    )
                    conn.commit()
                    send_conf_email(email, conf_path)

                # Восстанавливаем peer и статус для истекшего заказа
                if status == "expired":
                    if conf_file and os.path.exists(conf_file):
                        conf_path = conf_file
                        fields = parse_conf(conf_path)
                        private_key = fields.get("PrivateKey")
                        address = fields.get("Address")
                        if not public_key and private_key:
                            public_key = subprocess.check_output(
                                ["wg", "pubkey"], input=private_key.encode()
                            ).decode().strip()
                        if address and public_key:
                            wg_set_peer(public_key, address)
                            append_peer_to_conf(public_key, address)
                        cur.execute(
                            "UPDATE orders SET status='paid', public_key=COALESCE(public_key,?), "
                            "client_ip=COALESCE(client_ip,?) WHERE id=?",
                            (public_key, address, order_id)
                        )
                        conn.commit()
                        send_conf_email(email, conf_path)

            expires_at = calculate_expiry_extended(plan_type, current_expiry)

            # Обновляем существующий заказ или создаём новый
            if row:
                cur.execute(
                    "UPDATE orders SET expires_at=?, plan=?, price=? WHERE id=?",
                    (expires_at, plan_name, price, order_id)
                )
                conn.commit()
            else:
                cur.execute(
                    "INSERT INTO orders(email, plan, price, status, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (email, plan_name, price, "paid", now.isoformat(), expires_at)
                )
                order_id = cur.lastrowid
                conf_path, public_key, client_ip = create_client_conf(order_id, email, plan_name)
                cur.execute(
                    "UPDATE orders SET conf_file=?, public_key=?, client_ip=? WHERE id=?",
                    (conf_path, public_key, client_ip, order_id)
                )
                conn.commit()
                send_conf_email(email, conf_path)

        token_data = {
            "id": order_id,
            "email": email,
            "plan": {"name": plan_name, "price": price},
            "status": "paid"
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        return token, None

    except Exception as e:
        logging.exception("Ошибка создания заказа")
        return None, str(e)

# ---------------------------
# FLASK ROUTES
# ---------------------------
@app.route("/")
def index():
    return render_template("index.html")

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

    # Создаём запись в БД с статусом pending
    now = datetime.now(timezone.utc)
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders(email, plan, price, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (email, plan_name, price, "pending", now.isoformat())
        )
        order_id = cur.lastrowid
        conn.commit()

    # Создаём Base64 токен, чтобы JS мог передать его в URL
    token_data = {
        "id": order_id,
        "email": email,
        "plan": {"name": plan_name, "price": price},
        "status": "pending"
    }
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
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT conf_file, status FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return ".conf не найден", 404
        conf_path, status = row
        if status != "paid":
            return ".conf не найден или оплата не завершена", 403
    return send_file(conf_path, as_attachment=True)

@app.route("/qr/<int:order_id>")
def qr(order_id):
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT conf_file FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row or not os.path.exists(row[0]):
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
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT status, expires_at FROM orders WHERE email=? ORDER BY id DESC LIMIT 1", (email,)
        ).fetchone()
        if not row:
            return jsonify({"status": "не найдена"}), 200
        status, expires_at = row
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp_dt:
                    status = "истекла"
            except Exception:
                pass
    return jsonify({"status": status, "expires_at": expires_at})

# ---------------------------
# YOOKASSA REAL + WEBHOOK
# ---------------------------
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
        # return_url с email и plan_id
        return_url = f"http://secure-link.ru/payment-callback?email={quote(email)}&plan_id={plan_id}"

        # 🔑 Добавляем корректный receipt
        receipt = {
            "customer": {
                "email": email,
                "phone": "80000000000"
            },
            "items": [
                {
                    "description": f"Тариф {plan_name}",
                    "quantity": "1.00",  # строка с дробным значением
                    "amount": {"value": f"{price:.2f}", "currency": "RUB"},
                    "vat_code": 1
                }
            ]
        }

        payment = Payment.create({
            "amount": {"value": f"{price:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": f"Оплата тарифа {plan_name} для {email}",
            "metadata": {"email": email, "plan_id": plan_id},
        })

        logging.info(f"Created payment: {payment.id}")
        return jsonify({"confirmation_url": payment.confirmation.confirmation_url})

    except Exception as e:
        logging.exception("Ошибка при создании платежа")
        return jsonify({"error": str(e)}), 500

@app.route("/yookassa-webhook", methods=["POST"])
def yookassa_webhook():
    try:
        event = request.json
        logging.info(f"Webhook received: {event}")

        if not event or "object" not in event:
            return jsonify({"error": "Неверный формат"}), 400

        payment = event["object"]

        # Создаём заказ только после успешной оплаты
        if payment.get("status") == "succeeded":
            email = payment.get("metadata", {}).get("email")
            plan_id = payment.get("metadata", {}).get("plan_id")

            if email and plan_id:
                try:
                    plan_id = int(plan_id)
                    token, err = create_order_internal(email, plan_id)
                    if err:
                        logging.error(f"Ошибка при создании заказа из webhook: {err}")
                except Exception as e:
                    logging.exception("Ошибка обработки webhook")

        return jsonify({"status": "ok"})

    except Exception as e:
        logging.exception("Ошибка в webhook")
        return jsonify({"error": str(e)}), 500


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

    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        # Находим последний оплаченный заказ
        row = cur.execute(
            "SELECT id FROM orders WHERE email=? AND plan=? AND status='paid' ORDER BY id DESC LIMIT 1",
            (email, PLANS.get(plan_id, ("", 0, ""))[0])
        ).fetchone()
        if not row:
            return "Оплата не завершена", 403

        order_id = row[0]

        # Генерируем одноразовый токен для страницы конфигурации
        token = base64.urlsafe_b64encode(os.urandom(24)).decode()
        cur.execute("UPDATE orders SET access_token=? WHERE id=?", (token, order_id))
        conn.commit()

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

    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        # Проверяем токен и статус
        row = cur.execute(
            "SELECT id, conf_file FROM orders WHERE access_token=? AND status='paid'",
            (order_token,)
        ).fetchone()
        if not row:
            return "Токен недействителен или уже использован", 403

        order_id, conf_path = row

        # Сразу обнуляем токен, чтобы нельзя было повторно открыть страницу
        cur.execute("UPDATE orders SET access_token=NULL WHERE id=?", (order_id,))
        conn.commit()

    if not os.path.exists(conf_path):
        return "Файл конфигурации отсутствует", 404

    with open(conf_path) as f:
        conf_text = f.read()

    # Формируем объект order для шаблона
    row = cur.execute("SELECT plan, price FROM orders WHERE id=?", (order_id,)).fetchone()
    order = {"id": order_id, "plan": {"name": row[0], "price": row[1]} if row else {"name": "Неизвестно", "price": 0}}

    return render_template(
        "config.html",
        conf_text=conf_text,
        order=order,
        download_url=url_for("download", order_id=order_id),
        qr_url=url_for("qr", order_id=order_id)
    )


def get_active_clients():
    stats = get_wg_stats()
    clients = []
    now = time.time()
    with sqlite3.connect(DB_FILE) as conn:
        for row in conn.execute(
                "SELECT email, plan, public_key, client_ip, created_at, expires_at "
                "FROM orders WHERE status='paid'"
        ):
            email, plan, pubkey, ip, created, expires = row
            rx = tx = 0
            last_active = False
            last_seen = 0  # по умолчанию
            if pubkey in stats:
                rx = stats[pubkey]["rx_bytes"]
                tx = stats[pubkey]["tx_bytes"]
                last_seen = stats[pubkey].get("last_seen", 0)
                if now - last_seen < 60:  # онлайн, если активность за последние 60 секунд
                    last_active = True
                stats[pubkey]["last_seen"] = now  # обновляем "последнюю активность"

            clients.append({
                "email": email,
                "plan": plan,
                "public_key": pubkey,
                "client_ip": ip,
                "rx_bytes": rx,
                "tx_bytes": tx,
                "online": last_active,
                "last_seen": last_seen,  # добавили поле для фронтенда
                "start_date": created,
                "end_date": expires
            })
    return clients

def check_auth(username, password):
    return username == "khokhlov1261" and password == "uisdvh(uisdyv-sdjvsdjv12312-sdm)nbm.jdjd-hjshq"

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                'Нужна авторизация', 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'}
            )
        return f(*args, **kwargs)
    return decorated

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
                rx = int(rx)
                tx = int(tx)

                # Берем старое значение для скорости
                prev = wg_prev_stats.get(pubkey, {"rx": rx, "tx": tx, "last_seen": now})
                dt = max(now - wg_prev_time, 1)
                speed_rx = (rx - prev["rx"]) / dt  # байт/сек
                speed_tx = (tx - prev["tx"]) / dt

                stats[pubkey] = {
                    "rx_bytes": rx,
                    "tx_bytes": tx,
                    "speed_rx": speed_rx,
                    "speed_tx": speed_tx,
                    "last_seen": prev.get("last_seen", now)
                }

                # Обновляем last_seen если есть активность
                if speed_rx > 0 or speed_tx > 0:
                    stats[pubkey]["last_seen"] = now

    # Обновляем глобальные значения
    wg_prev_stats = {k: {"rx": v["rx_bytes"], "tx": v["tx_bytes"], "last_seen": v["last_seen"]} for k,v in stats.items()}
    wg_prev_time = now

    return stats

# HTML-шаблон для админа
@app.route("/admin")
@requires_auth
def admin_dashboard():
    return render_template("admin.html")  # HTML загружается пустой, данные тянутся через JS


# API для AJAX (обновление данных на странице)
@app.route("/admin/stats")
@requires_auth
def admin_stats():
    # Системные метрики
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    # Клиенты WireGuard
    wg_stats = get_wg_stats()
    now = time.time()
    clients = []

    with sqlite3.connect(DB_FILE) as conn:
        for row in conn.execute(
            "SELECT email, public_key, client_ip, plan, created_at, expires_at FROM orders WHERE status='paid'"
        ):
            email, pubkey, ip, plan, created, expires = row
            rx = wg_stats.get(pubkey, {}).get("rx_bytes", 0)
            tx = wg_stats.get(pubkey, {}).get("tx_bytes", 0)
            speed_rx = wg_stats.get(pubkey, {}).get("speed_rx", 0)
            speed_tx = wg_stats.get(pubkey, {}).get("speed_tx", 0)
            last_seen = wg_stats.get(pubkey, {}).get("last_seen", 0)
            online = (now - last_seen) < 60

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
        # Декодируем URL
        public_key = unquote(public_key)

        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT conf_file FROM orders WHERE public_key=?", (public_key,)).fetchone()
            if row:
                conf_file = row[0]
                wg_remove_peer(public_key)
                if conf_file and os.path.exists(conf_file):
                    os.remove(conf_file)
                cur.execute(
                    "UPDATE orders SET conf_file=NULL, status='expired' WHERE public_key=?",
                    (public_key,)
                )
                conn.commit()
        logging.info("Клиент %s удалён", public_key)
        return jsonify({"status": "ok"})
    except Exception as e:
        logging.exception("Ошибка при удалении клиента %s: %s", public_key, e)
        return jsonify({"status": "error"}), 500


from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

def send_conf_email(to_email, conf_path, expires_at=None):
    try:
        subject = "SecureLink — Ваша WireGuard конфигурация"
        body = "Здравствуйте!\n\nВ приложении находится ваш новый конфигурационный файл WireGuard."

        if expires_at:
            # Парсим ISO-строку в datetime
            dt_utc = datetime.fromisoformat(expires_at)
            # Конвертируем в локальное время (например, Москва)
            dt_local = dt_utc.astimezone(ZoneInfo("Europe/Moscow"))
            body += f"\n\nСрок действия вашей подписки (МСК) до: {dt_local.strftime('%Y-%m-%d %H:%M:%S')}"

        body += "\n\nПриятного пользования!"

        # Создаем письмо
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Прикрепляем конфиг
        with open(conf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(conf_path))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(conf_path)}"'
        msg.attach(part)

        # Отправка
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())

        logging.info("Конфиг отправлен на почту: %s", to_email)
    except Exception as e:
        logging.exception("Ошибка при отправке конфигурации на почту")

# FREE TRIAL
@app.route("/free-trial", methods=["POST"])
def free_trial():
    data = request.json or {}
    email = (data.get("email") or "").strip()

    if not email:
        return jsonify({"error": "Email не указан"}), 400

    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        # Проверяем, использовал ли уже бесплатный период
        row = cur.execute(
            "SELECT 1 FROM orders WHERE email=? AND plan=? LIMIT 1",
            (email, "3 дня бесплатно")
        ).fetchone()
        if row:
            return jsonify({"error": "Вы уже использовали бесплатный пробный период"}), 400

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=3)).isoformat()
        plan_name = "3 дня бесплатно"
        price = 0.0

        # Создаем заказ
        cur.execute(
            "INSERT INTO orders(email, plan, price, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (email, plan_name, price, "paid", now.isoformat(), expires_at)
        )
        order_id = cur.lastrowid

        # Создаем конфиг WireGuard
        conf_path, public_key, client_ip = create_client_conf(order_id, email, plan_name)
        cur.execute(
            "UPDATE orders SET conf_file=?, public_key=?, client_ip=? WHERE id=?",
            (conf_path, public_key, client_ip, order_id)
        )
        conn.commit()

    # Отправляем конфиг на почту с указанием даты окончания
    send_conf_email(email, conf_path, expires_at)

    return jsonify({"message": "Бесплатный пробный период активирован! Конфигурация отправлена на email (Иногда письмо приходит в'СПАМ')."})
# ---------------------------
# RUN APP
# ---------------------------
if __name__ == "__main__":
    logging.info("Starting app on %s:%s", APP_HOST, APP_PORT)
    app.run(host=APP_HOST, port=APP_PORT, debug=DEBUG)

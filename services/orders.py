import os
import json
import base64
import subprocess
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import logging
from app import config


logger = logging.getLogger("securelink")


# Общие тарифы (единый источник правды)
PLANS = {
    1: ("1 месяц", 99.0, "month1"),
    2: ("6 месяцев", 499.0, "month6"),
    3: ("1 год", 999.0, "year"),
}


class OrderService:
    """Сервис заказов/подписок, общий для Flask и Telegram-бота."""

    def __init__(
        self,
        get_conn,
        *,
        wg_set_peer,
        append_peer_to_conf,
        wg_remove_peer,
        parse_conf,
        send_conf_email,
        wg_gen_keypair,
        get_next_free_ip,
        conf_dir: str,
        server_public_key: str,
        server_endpoint: str,
        dns_addr: str,
    ) -> None:
        self.get_conn = get_conn
        self.wg_set_peer = wg_set_peer
        self.append_peer_to_conf = append_peer_to_conf
        self.wg_remove_peer = wg_remove_peer
        self.parse_conf = parse_conf
        self.send_conf_email = send_conf_email
        self.wg_gen_keypair = wg_gen_keypair
        self.get_next_free_ip = get_next_free_ip
        self.conf_dir = conf_dir
        self.server_public_key = server_public_key
        self.server_endpoint = server_endpoint
        self.dns_addr = dns_addr

    # ---------- Вспомогательные ----------
    @staticmethod
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

    def create_client_conf(self, order_id: int, email: str, plan_name: str):
        private_key, public_key = self.wg_gen_keypair()
        client_ip = self.get_next_free_ip()

        if self.wg_set_peer(public_key, client_ip):
            self.append_peer_to_conf(public_key, client_ip)
            logger.info("Peer %s -> %s added for %s", public_key, client_ip, email)
        else:
            logger.warning("Failed to add peer for %s", email)

        conf_text = (
            f"[Interface]\nPrivateKey = {private_key}\nAddress = {client_ip}\nDNS = {self.dns_addr}\n\n"
            f"[Peer]\nPublicKey = {self.server_public_key}\nEndpoint = {self.server_endpoint}\nAllowedIPs = 0.0.0.0/0\n"
            f"# Email: {email}\n# Plan: {plan_name}\n"
        )

        os.makedirs(self.conf_dir, exist_ok=True)
        conf_path = os.path.join(self.conf_dir, f"wg_{order_id}.conf")
        with open(conf_path, "w") as f:
            f.write(conf_text)
        os.chmod(conf_path, 0o600)
        logger.info("Saved client config: %s", conf_path)
        return conf_path, public_key, client_ip

    # ---------- Основная логика ----------
    def create_order_internal(self, email: str, plan_id: int, user_id: int = None, telegram_id: int = None):
        """
        Создание/продление заказа после успешной оплаты.
        Возвращает (token, None) или (None, error_message)
        """
        try:
            plan_name, price, plan_type = PLANS.get(plan_id, ("неизвестно", 0, None))
            if not email or price <= 0:
                return None, "Неверные данные"

            now = datetime.now(timezone.utc)

            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    # Последний заказ по email
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
                            conf_path, public_key, client_ip = self.create_client_conf(order_id, email, plan_name)
                            cur.execute(
                                "UPDATE orders SET conf_file=%s, public_key=%s, client_ip=%s WHERE id=%s;",
                                (conf_path, public_key, client_ip, order_id)
                            )
                            logger.info("Updated order %s with new conf", order_id)
                            try:
                                self.send_conf_email(email, conf_path)
                            except Exception:
                                logger.exception("Failed to send conf email")

                        # Реактивируем истекший заказ
                        if status == "expired":
                            if conf_file and os.path.exists(conf_file):
                                conf_path = conf_file
                                fields = self.parse_conf(conf_path)
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
                                    self.wg_set_peer(public_key, address)
                                    self.append_peer_to_conf(public_key, address)
                                cur.execute(
                                    "UPDATE orders SET status='paid', public_key=COALESCE(public_key,%s), "
                                    "client_ip=COALESCE(client_ip,%s) WHERE id=%s;",
                                    (public_key, address, order_id)
                                )
                                logger.info("Reactivated expired order %s", order_id)
                                try:
                                    self.send_conf_email(email, conf_path)
                                except Exception:
                                    logger.exception("Failed to send conf email on reactivation")

                    expires_at = self.calculate_expiry_extended(plan_type, current_expiry)

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
                        conf_path, public_key, client_ip = self.create_client_conf(order_id, email, plan_name)
                        cur.execute(
                            "UPDATE orders SET conf_file=%s, public_key=%s, client_ip=%s WHERE id=%s;",
                            (conf_path, public_key, client_ip, order_id)
                        )
                        logger.info("Created new order %s", order_id)
                        try:
                            self.send_conf_email(email, conf_path)
                        except Exception:
                            logger.exception("Failed to send conf email on new order")
                        # Сохраняем telegram_id, если передан (для выдачи в боте)
                        if telegram_id:
                            try:
                                cur.execute("UPDATE orders SET telegram_id=%s WHERE id=%s;", (telegram_id, order_id))
                            except Exception:
                                logger.exception("Failed to store telegram_id on order")

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



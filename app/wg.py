import os
import ipaddress
import subprocess
from typing import Set
from dotenv import load_dotenv
from .db import get_conn

# Загружаем .env
load_dotenv()

# -------------------
# WireGuard / service settings
WG_CONFIG_PATH = os.getenv("WG_CONFIG_PATH", "/etc/wireguard/wg0.conf")
WG_INTERFACE = os.getenv("WG_INTERFACE", "wg0")
SERVER_PUBLIC_KEY = os.getenv("SERVER_PUBLIC_KEY")
SERVER_ENDPOINT = os.getenv("SERVER_ENDPOINT")
DNS_ADDR = os.getenv("DNS_ADDR", "8.8.8.8")
WG_CLIENT_NETWORK_CIDR = os.getenv("WG_CLIENT_NETWORK_CIDR", "10.0.0.0/24")
WG_CLIENT_NETWORK6_CIDR = os.getenv("WG_CLIENT_NETWORK6_CIDR", "")


def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def wg_set_peer(public_key: str, allowed_ips: str) -> bool:
    res = run_cmd(["wg", "set", WG_INTERFACE, "peer", public_key, "allowed-ips", allowed_ips])
    return res.returncode == 0


def wg_remove_peer(public_key: str) -> bool:
    res = run_cmd(["wg", "set", WG_INTERFACE, "peer", public_key, "remove"])
    return res.returncode == 0


def wg_gen_keypair():
    private = subprocess.check_output(["wg", "genkey"]).decode().strip()
    public = subprocess.check_output(["wg", "pubkey"], input=private.encode()).decode().strip()
    return private, public


def append_peer_to_conf(public_key: str, client_ip: str):
    if os.path.exists(WG_CONFIG_PATH):
        with open(WG_CONFIG_PATH, "r") as f:
            contents = f.read()
        if public_key in contents:
            return
    with open(WG_CONFIG_PATH, "a") as f:
        f.write(f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {client_ip}\n")


def parse_conf(conf_path: str):
    result = {"PrivateKey": None, "Address": None}
    if not os.path.exists(conf_path):
        return result
    with open(conf_path) as f:
        for line in f:
            if line.strip().startswith("PrivateKey"):
                result["PrivateKey"] = line.split("=", 1)[1].strip()
            elif line.strip().startswith("Address"):
                result["Address"] = line.split("=", 1)[1].strip()
    return result


def get_used_ips() -> Set[str]:
    ips = set()
    if os.path.exists(WG_CONFIG_PATH):
        with open(WG_CONFIG_PATH) as f:
            for line in f:
                if line.strip().startswith("AllowedIPs"):
                    ip = line.split("=", 1)[1].strip().split("/")[0]
                    ips.add(ip)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT client_ip FROM orders WHERE client_ip IS NOT NULL;")
            for row in cur.fetchall():
                ip = row[0]
                if ip:
                    ips.add(ip.split("/")[0])
    return ips


def get_next_free_ip() -> str:
    network = ipaddress.ip_network(WG_CLIENT_NETWORK_CIDR, strict=False)
    used = get_used_ips()
    for host in network.hosts():
        ip_str = str(host)
        if ip_str not in used:
            return f"{ip_str}/32"
    raise RuntimeError("No free IP addresses left in network " + WG_CLIENT_NETWORK_CIDR)
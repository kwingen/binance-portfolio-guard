"""配置文件加密"""
import os
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DATA_DIR = "/app/data"
CONFIG_FILE = os.path.join(DATA_DIR, "secure.json")


def _get_cipher() -> Fernet:
    """从环境变量或密码派生加密密钥"""
    key_material = os.environ.get("SL_ENCRYPTION_KEY", os.environ.get("SL_PASSWORD", ""))
    if not key_material:
        # 无密码时用固定盐（仅用于 DEMO 模式）
        key_material = "demo-encryption-key"

    salt = b"binance-guard-salt-2024"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    key = base64.urlsafe_b64encode(kdf.derive(key_material.encode()))
    return Fernet(key)


def save_secure_config(data: dict):
    """加密保存配置到文件"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cipher = _get_cipher()
    plaintext = json.dumps(data).encode()
    encrypted = cipher.encrypt(plaintext)
    with open(CONFIG_FILE, "wb") as f:
        f.write(encrypted)
    os.chmod(CONFIG_FILE, 0o600)


def load_secure_config() -> dict:
    """解密加载配置"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    cipher = _get_cipher()
    with open(CONFIG_FILE, "rb") as f:
        encrypted = f.read()
    try:
        plaintext = cipher.decrypt(encrypted)
        return json.loads(plaintext)
    except Exception:
        return {}

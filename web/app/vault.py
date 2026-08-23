import base64
import json
import os
import secrets
import threading

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_LEN = 32
NONCE_LEN = 12
SALT_LEN = 16

# вывод ключа-обёртки. проверочный хеш пароля считается отдельным вызовом
# argon2 со своей солью, иначе хеш из базы, который хранится открыто, сам
# оказался бы ключом от сейфа
TIME_COST = 3
MEMORY_COST = 64 * 1024
PARALLELISM = 4

WRAP = b"netmap-key-wrap"

_key: bytes | None = None
_lock = threading.Lock()


def new_key() -> bytes:
    return os.urandom(KEY_LEN)


def new_salt() -> str:
    return base64.b64encode(os.urandom(SALT_LEN)).decode()


def new_recovery() -> str:
    return "-".join(secrets.token_hex(3) for _ in range(4))


def wrap(key: bytes, secret: str, salt: str) -> str:
    return _seal(_kek(secret, salt), key, WRAP)


def unwrap(blob: str, secret: str, salt: str) -> bytes | None:
    return _open(_kek(secret, salt), blob, WRAP)


def unlock(key: bytes) -> None:
    global _key
    with _lock:
        _key = key


def lock() -> None:
    global _key
    with _lock:
        _key = None


def unlocked() -> bool:
    with _lock:
        return _key is not None


def seal(ip: str, username: str, password: str) -> str | None:
    key = current()
    if key is None:
        return None
    plain = json.dumps({"username": username, "password": password}).encode()
    return _seal(key, plain, ip.encode())


def unseal(ip: str, box: str) -> tuple[str, str] | None:
    key = current()
    if key is None:
        return None
    plain = _open(key, box, ip.encode())
    if plain is None:
        return None
    data = json.loads(plain)
    return data["username"], data["password"]


def current() -> bytes | None:
    with _lock:
        return _key


def _kek(secret: str, salt: str) -> bytes:
    return hash_secret_raw(
        secret=secret.encode(),
        salt=base64.b64decode(salt),
        time_cost=TIME_COST,
        memory_cost=MEMORY_COST,
        parallelism=PARALLELISM,
        hash_len=KEY_LEN,
        type=Type.ID,
    )


def _seal(key: bytes, plain: bytes, aad: bytes) -> str:
    nonce = os.urandom(NONCE_LEN)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, plain, aad)).decode()


def _open(key: bytes, blob: str, aad: bytes) -> bytes | None:
    try:
        raw = base64.b64decode(blob)
        return AESGCM(key).decrypt(raw[:NONCE_LEN], raw[NONCE_LEN:], aad)
    except (InvalidTag, ValueError, TypeError):
        return None

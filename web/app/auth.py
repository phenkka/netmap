import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError
from fastapi import HTTPException, Request

from . import store, vault

COOKIE = "netmap_session"
KEEP = "keep_credentials"
RECOVERY_SALT = "recovery_salt"
RECOVERY_WRAP = "recovery_wrap"
IDLE_TIMEOUT = 12 * 3600
MIN_PASSWORD = 8

_hasher = PasswordHasher()
_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def configured() -> bool:
    return store.user_count() > 0


def create_user(
    login: str, password: str, role: str = "admin", key: bytes | None = None
) -> None:
    salt, wrapped = _wrap_for(password, key)
    store.save_user(login, _hasher.hash(password), role, salt, wrapped)


def set_password(login: str, password: str, key: bytes | None) -> None:
    """новый пароль и новая обёртка. пароли оборудования при этом не трогаются"""
    salt, wrapped = _wrap_for(password, key)
    store.save_password(login, _hasher.hash(password), salt, wrapped)


def _wrap_for(password: str, key: bytes | None) -> tuple[str | None, str | None]:
    if key is None:
        return None, None
    salt = vault.new_salt()
    return salt, vault.wrap(key, password, salt)


def first_run(login: str, password: str, keep: bool) -> str | None:
    """заводит администратора. в режиме хранения отдаёт ключ восстановления"""
    # нет ключа — нечего заворачивать, и на диск ничего не уходит, как было раньше
    key = vault.new_key() if keep else None
    create_user(login, password, key=key)
    store.save_setting(KEEP, "yes" if keep else "no")
    if key is None:
        return None

    vault.unlock(key)
    recovery = vault.new_recovery()
    salt = vault.new_salt()
    store.save_setting(RECOVERY_SALT, salt)
    store.save_setting(RECOVERY_WRAP, vault.wrap(key, recovery, salt))
    return recovery


def recovery_offered() -> bool:
    return bool(store.setting(RECOVERY_WRAP))


def recover(login: str, recovery: str, password: str) -> bool:
    """ключ восстановления открывает сейф и задаёт новый пароль"""
    salt = store.setting(RECOVERY_SALT)
    wrapped = store.setting(RECOVERY_WRAP)
    if not salt or not wrapped:
        return False

    key = vault.unwrap(wrapped, recovery, salt)
    if key is None:
        return False

    vault.unlock(key)
    set_password(login, password, key)
    return True


def open_vault(user: dict, password: str) -> int:
    """разворачивает копию ключа из обёртки администратора и возвращает доступы"""
    if not user.get("wrapped_key") or not user.get("key_salt"):
        return 0
    key = vault.unwrap(user["wrapped_key"], password, user["key_salt"])
    if key is None:
        return 0

    vault.unlock(key)
    return restore_credentials()


def restore_credentials() -> int:
    """сколько доступов к оборудованию вернулось в память"""
    return store.load_credentials() if vault.unlocked() else 0


def check(login: str, password: str) -> dict | None:
    user = store.user(login)
    if not user:
        return None
    try:
        _hasher.verify(user["password_hash"], password)
    except (VerificationError, InvalidHash):
        return None
    return user


def open_session(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = {
            "login": user["login"],
            "role": user["role"],
            "seen": time.time(),
        }
    return token


def close_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _sessions.pop(token, None)


def by_token(token: str | None) -> dict | None:
    if not token:
        return None
    now = time.time()
    with _lock:
        found = _sessions.get(token)
        if not found:
            return None
        if now - found["seen"] > IDLE_TIMEOUT:
            del _sessions[token]
            return None
        found["seen"] = now
        return dict(found)


def session(request: Request) -> dict | None:
    return by_token(request.cookies.get(COOKIE))


def require(request: Request) -> dict:
    found = session(request)
    if not found:
        raise HTTPException(401, "требуется вход")
    return found

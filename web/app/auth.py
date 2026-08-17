import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError
from fastapi import HTTPException, Request

from . import store

COOKIE = "netmap_session"
IDLE_TIMEOUT = 12 * 3600
MIN_PASSWORD = 8

_hasher = PasswordHasher()
_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def configured() -> bool:
    return store.user_count() > 0


def create_user(login: str, password: str, role: str = "admin") -> None:
    store.save_user(login, _hasher.hash(password), role)


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

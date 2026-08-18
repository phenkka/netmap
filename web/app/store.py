import hashlib
import os
import threading
import zlib
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import vault

DSN = os.environ.get("NETMAP_DB", "postgresql:///netmap?host=/var/run/postgresql&user=netmap")

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    ip           TEXT PRIMARY KEY,
    mac          TEXT,
    banner       TEXT,
    login_banner TEXT,
    status       TEXT NOT NULL DEFAULT 'detected',
    hostname     TEXT,
    vendor       TEXT,
    model        TEXT,
    version      TEXT,
    error        TEXT,
    lldp         TEXT,
    misses       INTEGER NOT NULL DEFAULT 0,
    first_seen   TEXT,
    last_seen    TEXT
);

ALTER TABLE devices ADD COLUMN IF NOT EXISTS lldp TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS misses INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS neighbors (
    ip           TEXT NOT NULL,
    local_port   TEXT NOT NULL,
    remote_name  TEXT NOT NULL,
    remote_port  TEXT NOT NULL,
    remote_addr  TEXT,
    capabilities TEXT,
    PRIMARY KEY (ip, local_port, remote_name, remote_port)
);

ALTER TABLE neighbors ADD COLUMN IF NOT EXISTS remote_addr TEXT;

CREATE TABLE IF NOT EXISTS configs (
    id     BIGSERIAL PRIMARY KEY,
    ip     TEXT NOT NULL,
    at     TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    lines  INTEGER NOT NULL,
    source TEXT NOT NULL,
    text   BYTEA NOT NULL
);

CREATE INDEX IF NOT EXISTS configs_by_device ON configs (ip, id DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    login         TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'admin',
    key_salt      TEXT,
    wrapped_key   TEXT,
    created_at    TEXT NOT NULL
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS key_salt TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS wrapped_key TEXT;

CREATE TABLE IF NOT EXISTS secrets (
    ip  TEXT PRIMARY KEY,
    box TEXT NOT NULL
);
"""

_pool = ConnectionPool(
    DSN, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
)

# в открытом виде учётные данные живут только здесь. на диск они уходят
# зашифрованными и только в режиме хранения
_credentials: dict[str, tuple[str, str]] = {}
_credentials_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init() -> None:
    _pool.open(wait=True, timeout=30)
    with _pool.connection() as conn:
        conn.execute(SCHEMA)
        conn.execute(
            """
            UPDATE devices
               SET status = 'detected', error = NULL
             WHERE status = 'authorized'
            """
        )


def save_detected(
    ip: str, mac: str | None, banner: str | None, login_banner: str | None
) -> None:
    with _pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO devices (ip, mac, banner, login_banner, status, first_seen, last_seen)
            VALUES (%s, %s, %s, %s, 'detected', %s, %s)
            ON CONFLICT (ip) DO UPDATE SET
                mac = EXCLUDED.mac,
                banner = EXCLUDED.banner,
                login_banner = EXCLUDED.login_banner,
                misses = 0,
                last_seen = EXCLUDED.last_seen
            """,
            (ip, mac, banner, login_banner, _now(), _now()),
        )


def bump_misses(ips: list[str]) -> None:
    """устройство не ответило на обходе, счётчик сбросит первый же ответ"""
    if not ips:
        return
    with _pool.connection() as conn:
        conn.execute(
            "UPDATE devices SET misses = misses + 1 WHERE ip = ANY(%s)", (ips,)
        )


def save_identity(ip: str, hostname: str, vendor: str, model: str, version: str) -> None:
    with _pool.connection() as conn:
        conn.execute(
            """
            UPDATE devices
               SET status = 'authorized', hostname = %s, vendor = %s, model = %s,
                   version = %s, error = NULL, last_seen = %s
             WHERE ip = %s
            """,
            (hostname, vendor, model, version, _now(), ip),
        )


def save_lldp(ip: str, state: str | None) -> None:
    with _pool.connection() as conn:
        conn.execute("UPDATE devices SET lldp = %s WHERE ip = %s", (state, ip))


def save_error(ip: str, message: str) -> None:
    save_status(ip, "failed", message)


def save_status(ip: str, status: str, message: str | None = None) -> None:
    with _pool.connection() as conn:
        conn.execute(
            "UPDATE devices SET status = %s, error = %s, last_seen = %s WHERE ip = %s",
            (status, message, _now(), ip),
        )


def devices() -> list[dict]:
    with _pool.connection() as conn:
        return conn.execute("SELECT * FROM devices ORDER BY ip").fetchall()


def device(ip: str) -> dict | None:
    with _pool.connection() as conn:
        return conn.execute("SELECT * FROM devices WHERE ip = %s", (ip,)).fetchone()


def save_neighbors(ip: str, links: list[dict]) -> None:
    with _pool.connection() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM neighbors WHERE ip = %s", (ip,))
        cursor.executemany(
            """
            INSERT INTO neighbors (ip, local_port, remote_name, remote_port, remote_addr, capabilities)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            [
                (
                    ip,
                    n["local_port"],
                    n["remote_name"],
                    n["remote_port"],
                    n.get("remote_addr") or None,
                    n.get("capabilities", ""),
                )
                for n in links
            ],
        )


def neighbors() -> list[dict]:
    with _pool.connection() as conn:
        return conn.execute("SELECT * FROM neighbors").fetchall()


def neighbors_of(ip: str) -> list[dict]:
    with _pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM neighbors WHERE ip = %s ORDER BY local_port", (ip,)
        ).fetchall()


def save_config(ip: str, text: str, source: str) -> dict | None:
    """пишет новую версию, если конфигурация изменилась, иначе отдаёт None"""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = text.count("\n") + 1

    with _pool.connection() as conn:
        last = conn.execute(
            "SELECT sha256 FROM configs WHERE ip = %s ORDER BY id DESC LIMIT 1", (ip,)
        ).fetchone()
        # без сравнения хешей за год накопится 365 одинаковых копий
        if last and last["sha256"] == digest:
            return None

        at = _now()
        row = conn.execute(
            """
            INSERT INTO configs (ip, at, sha256, lines, source, text)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (ip, at, digest, lines, source, zlib.compress(text.encode("utf-8"), 6)),
        ).fetchone()

    return {
        "id": row["id"],
        "ip": ip,
        "at": at,
        "sha256": digest,
        "lines": lines,
        "source": source,
    }


def configs(ip: str) -> list[dict]:
    with _pool.connection() as conn:
        return conn.execute(
            """
            SELECT id, ip, at, sha256, lines, source
              FROM configs
             WHERE ip = %s
             ORDER BY id DESC
            """,
            (ip,),
        ).fetchall()


def config(version_id: int) -> dict | None:
    with _pool.connection() as conn:
        row = conn.execute("SELECT * FROM configs WHERE id = %s", (version_id,)).fetchone()
    return _unpack(row)


def last_config(ip: str) -> dict | None:
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM configs WHERE ip = %s ORDER BY id DESC LIMIT 1", (ip,)
        ).fetchone()
    return _unpack(row)


def _unpack(row: dict | None) -> dict | None:
    if not row:
        return None
    row["text"] = zlib.decompress(row["text"]).decode("utf-8")
    return row


def setting(key: str) -> str | None:
    with _pool.connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else None


def save_setting(key: str, value: str) -> None:
    with _pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )


def forget_setting(key: str) -> None:
    with _pool.connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = %s", (key,))


def user_count() -> int:
    with _pool.connection() as conn:
        return conn.execute("SELECT count(*) AS total FROM users").fetchone()["total"]


def user(login: str) -> dict | None:
    with _pool.connection() as conn:
        return conn.execute("SELECT * FROM users WHERE login = %s", (login,)).fetchone()


def save_user(
    login: str,
    password_hash: str,
    role: str,
    key_salt: str | None = None,
    wrapped_key: str | None = None,
) -> None:
    with _pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO users (login, password_hash, role, key_salt, wrapped_key, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (login, password_hash, role, key_salt, wrapped_key, _now()),
        )


def save_password(
    login: str, password_hash: str, key_salt: str | None, wrapped_key: str | None
) -> None:
    """новый пароль и перезавёрнутая под него копия ключа, одной записью"""
    with _pool.connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET password_hash = %s, key_salt = %s, wrapped_key = %s
             WHERE login = %s
            """,
            (password_hash, key_salt, wrapped_key, login),
        )


def set_credentials(ip: str, username: str, password: str) -> None:
    with _credentials_lock:
        _credentials[ip] = (username, password)

    # в режиме без хранения ключа нет, и на диск ничего не уходит
    box = vault.seal(ip, username, password)
    if box is None:
        return
    with _pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO secrets (ip, box) VALUES (%s, %s)
            ON CONFLICT (ip) DO UPDATE SET box = EXCLUDED.box
            """,
            (ip, box),
        )


def credentials(ip: str) -> tuple[str, str] | None:
    with _credentials_lock:
        return _credentials.get(ip)


def forget_credentials(ip: str) -> None:
    with _credentials_lock:
        _credentials.pop(ip, None)
    with _pool.connection() as conn:
        conn.execute("DELETE FROM secrets WHERE ip = %s", (ip,))


def load_credentials() -> int:
    """вход администратора развернул ключ, раскладываем доступы обратно в память"""
    with _pool.connection() as conn:
        rows = conn.execute("SELECT ip, box FROM secrets").fetchall()

    restored = 0
    for row in rows:
        found = vault.unseal(row["ip"], row["box"])
        if not found:
            continue
        with _credentials_lock:
            _credentials[row["ip"]] = found
        restored += 1
    return restored


def keep_credentials() -> int:
    """режим хранения включили на ходу, шифруем то, что уже лежит в памяти"""
    with _credentials_lock:
        known = dict(_credentials)
    for ip, (username, password) in known.items():
        set_credentials(ip, username, password)
    return len(known)


def wipe_secrets() -> None:
    """переход в режим, где доступы на диске не хранятся"""
    with _pool.connection() as conn:
        conn.execute("DELETE FROM secrets")

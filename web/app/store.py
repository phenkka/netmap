import hashlib
import os
import threading
import zlib
from datetime import datetime, timedelta, timezone

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
ALTER TABLE devices ADD COLUMN IF NOT EXISTS drift TEXT;

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

-- в flat лежит та же конфигурация в виде команд. откат отправляет на
-- устройство именно её, разобранный вывод обратно не применяется
ALTER TABLE configs ADD COLUMN IF NOT EXISTS flat BYTEA;

CREATE TABLE IF NOT EXISTS journal (
    id     BIGSERIAL PRIMARY KEY,
    at     TEXT NOT NULL,
    login  TEXT,
    action TEXT NOT NULL,
    ip     TEXT,
    detail TEXT,
    ok     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS journal_recent ON journal (id DESC);

CREATE TABLE IF NOT EXISTS baselines (
    id     BIGSERIAL PRIMARY KEY,
    name   TEXT NOT NULL,
    vendor TEXT NOT NULL,
    at     TEXT NOT NULL,
    text   BYTEA NOT NULL
);

CREATE TABLE IF NOT EXISTS device_baseline (
    ip          TEXT PRIMARY KEY,
    baseline_id BIGINT NOT NULL REFERENCES baselines (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS checks (
    ip     TEXT NOT NULL,
    code   TEXT NOT NULL,
    state  TEXT NOT NULL,
    detail TEXT,
    at     TEXT NOT NULL,
    PRIMARY KEY (ip, code)
);
"""

# соединений хватает на все потоки обхода и сверх того на запросы из браузера
_pool = ConnectionPool(
    DSN, min_size=1, max_size=20, open=False, kwargs={"row_factory": dict_row}
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


def save_drift(ip: str, state: str | None) -> None:
    with _pool.connection() as conn:
        conn.execute("UPDATE devices SET drift = %s WHERE ip = %s", (state, ip))


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


def save_config(ip: str, text: str, source: str, flat: str | None = None) -> dict | None:
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
            INSERT INTO configs (ip, at, sha256, lines, source, text, flat)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                ip,
                at,
                digest,
                lines,
                source,
                zlib.compress(text.encode("utf-8"), 6),
                zlib.compress(flat.encode("utf-8"), 6) if flat is not None else None,
            ),
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
            SELECT id, ip, at, sha256, lines, source, flat IS NOT NULL AS restorable
              FROM configs
             WHERE ip = %s
             ORDER BY id DESC
            """,
            (ip,),
        ).fetchall()


def restore_all_configs() -> list[dict]:
    with _pool.connection() as conn:
        rows = conn.execute("SELECT * FROM configs ORDER BY id").fetchall()
    return [_unpack(row) for row in rows]


def insert_config(
    ip: str, at: str, sha256: str, lines: int, source: str, text: str, flat: str | None
) -> bool:
    with _pool.connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM configs WHERE ip = %s AND at = %s AND sha256 = %s",
            (ip, at, sha256),
        ).fetchone()
        if exists:
            return False
        conn.execute(
            """
            INSERT INTO configs (ip, at, sha256, lines, source, text, flat)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ip,
                at,
                sha256,
                lines,
                source,
                zlib.compress(text.encode("utf-8"), 6),
                zlib.compress(flat.encode("utf-8"), 6) if flat is not None else None,
            ),
        )
    return True


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
    packed = row.get("flat")
    row["flat"] = zlib.decompress(packed).decode("utf-8") if packed else None
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
    with _credentials_lock:
        known = dict(_credentials)
    for ip, (username, password) in known.items():
        set_credentials(ip, username, password)
    return len(known)


def wipe_secrets() -> None:
    with _pool.connection() as conn:
        conn.execute("DELETE FROM secrets")


def add_entry(
    login: str | None, action: str, ip: str | None, detail: str | None, ok: bool
) -> dict:
    with _pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO journal (at, login, action, ip, detail, ok)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, at
            """,
            (_now(), login, action, ip, detail, ok),
        ).fetchone()
    return {
        "id": row["id"],
        "at": row["at"],
        "login": login,
        "action": action,
        "ip": ip,
        "detail": detail,
        "ok": ok,
    }


def trim_journal(days: int) -> int:
    edge = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )
    with _pool.connection() as conn:
        done = conn.execute("DELETE FROM journal WHERE at < %s", (edge,))
        return done.rowcount


def entries(after: int | None = None, limit: int = 300) -> list[dict]:
    with _pool.connection() as conn:
        if after is not None:
            return conn.execute(
                "SELECT * FROM journal WHERE id > %s ORDER BY id LIMIT %s",
                (after, limit),
            ).fetchall()
        rows = conn.execute(
            "SELECT * FROM journal ORDER BY id DESC LIMIT %s", (limit,)
        ).fetchall()
    return list(reversed(rows))


def save_baseline(name: str, vendor: str, text: str) -> dict:
    with _pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO baselines (name, vendor, at, text)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, vendor, at
            """,
            (name, vendor, _now(), zlib.compress(text.encode("utf-8"), 6)),
        ).fetchone()
    return row


def baselines() -> list[dict]:
    with _pool.connection() as conn:
        return conn.execute(
            """
            SELECT b.id, b.name, b.vendor, b.at, count(d.ip) AS devices
              FROM baselines b
              LEFT JOIN device_baseline d ON d.baseline_id = b.id
             GROUP BY b.id
             ORDER BY b.name
            """
        ).fetchall()


def baseline(baseline_id: int) -> dict | None:
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM baselines WHERE id = %s", (baseline_id,)
        ).fetchone()
    if not row:
        return None
    row["text"] = zlib.decompress(row["text"]).decode("utf-8")
    return row


def forget_baseline(baseline_id: int) -> None:
    with _pool.connection() as conn:
        conn.execute("DELETE FROM baselines WHERE id = %s", (baseline_id,))


def attach_baseline(ip: str, baseline_id: int | None) -> None:
    with _pool.connection() as conn:
        if baseline_id is None:
            conn.execute("DELETE FROM device_baseline WHERE ip = %s", (ip,))
            return
        conn.execute(
            """
            INSERT INTO device_baseline (ip, baseline_id) VALUES (%s, %s)
            ON CONFLICT (ip) DO UPDATE SET baseline_id = EXCLUDED.baseline_id
            """,
            (ip, baseline_id),
        )


def baseline_of(ip: str) -> dict | None:
    with _pool.connection() as conn:
        row = conn.execute(
            """
            SELECT b.*
              FROM device_baseline d
              JOIN baselines b ON b.id = d.baseline_id
             WHERE d.ip = %s
            """,
            (ip,),
        ).fetchone()
    if not row:
        return None
    row["text"] = zlib.decompress(row["text"]).decode("utf-8")
    return row


def attached() -> dict[str, int]:
    with _pool.connection() as conn:
        rows = conn.execute("SELECT ip, baseline_id FROM device_baseline").fetchall()
    return {row["ip"]: row["baseline_id"] for row in rows}


def save_checks(ip: str, results: list[dict]) -> None:
    with _pool.connection() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM checks WHERE ip = %s", (ip,))
        cursor.executemany(
            "INSERT INTO checks (ip, code, state, detail, at) VALUES (%s, %s, %s, %s, %s)",
            [(ip, r["code"], r["state"], r.get("detail"), _now()) for r in results],
        )


def checks_of(ip: str) -> list[dict]:
    with _pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM checks WHERE ip = %s ORDER BY code", (ip,)
        ).fetchall()


def failed_checks() -> dict[str, int]:
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT ip, count(*) AS failed FROM checks WHERE state = 'fail' GROUP BY ip"
        ).fetchall()
    return {row["ip"]: row["failed"] for row in rows}

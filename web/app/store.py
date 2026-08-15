import hashlib
import sqlite3
import threading
import zlib
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "netmap.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    ip         TEXT PRIMARY KEY,
    mac        TEXT,
    banner     TEXT,
    login_banner TEXT,
    status     TEXT NOT NULL DEFAULT 'detected',
    hostname   TEXT,
    vendor     TEXT,
    model      TEXT,
    version    TEXT,
    error      TEXT,
    first_seen TEXT,
    last_seen  TEXT
);

CREATE TABLE IF NOT EXISTS neighbors (
    ip          TEXT NOT NULL,
    local_port  TEXT NOT NULL,
    remote_name TEXT NOT NULL,
    remote_port TEXT NOT NULL,
    capabilities TEXT,
    PRIMARY KEY (ip, local_port, remote_name, remote_port)
);

CREATE TABLE IF NOT EXISTS configs (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ip     TEXT NOT NULL,
    at     TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    lines  INTEGER NOT NULL,
    source TEXT NOT NULL,
    text   BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS configs_by_device ON configs (ip, id DESC);
"""

# учётные данные только в памяти, на диск не пишутся
_credentials: dict[str, tuple[str, str]] = {}
_credentials_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        # снятие конфигураций пишет из пула потоков, без WAL они встают в очередь
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)

        # статус лежит на диске, а пароля после перезапуска нет,
        # подтвердить авторизацию нечем
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
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO devices (ip, mac, banner, login_banner, status, first_seen, last_seen)
            VALUES (?, ?, ?, ?, 'detected', ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                mac = excluded.mac,
                banner = excluded.banner,
                login_banner = excluded.login_banner,
                last_seen = excluded.last_seen
            """,
            (ip, mac, banner, login_banner, _now(), _now()),
        )


def save_identity(ip: str, hostname: str, vendor: str, model: str, version: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE devices
               SET status = 'authorized', hostname = ?, vendor = ?, model = ?,
                   version = ?, error = NULL, last_seen = ?
             WHERE ip = ?
            """,
            (hostname, vendor, model, version, _now(), ip),
        )


def save_error(ip: str, message: str) -> None:
    save_status(ip, "failed", message)


def save_status(ip: str, status: str, message: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE devices SET status = ?, error = ?, last_seen = ? WHERE ip = ?",
            (status, message, _now(), ip),
        )


def devices() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY ip").fetchall()
    return [dict(row) for row in rows]


def device(ip: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM devices WHERE ip = ?", (ip,)).fetchone()
    return dict(row) if row else None


def save_neighbors(ip: str, links: list[dict]) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM neighbors WHERE ip = ?", (ip,))
        conn.executemany(
            "INSERT OR IGNORE INTO neighbors VALUES (?, ?, ?, ?, ?)",
            [
                (
                    ip,
                    n["local_port"],
                    n["remote_name"],
                    n["remote_port"],
                    n.get("capabilities", ""),
                )
                for n in links
            ],
        )


def neighbors() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM neighbors").fetchall()
    return [dict(row) for row in rows]


def neighbors_of(ip: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM neighbors WHERE ip = ? ORDER BY local_port", (ip,)
        ).fetchall()
    return [dict(row) for row in rows]


def save_config(ip: str, text: str, source: str) -> dict | None:
    """пишет новую версию, если конфигурация изменилась, иначе отдаёт None"""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with _connect() as conn:
        last = conn.execute(
            "SELECT sha256 FROM configs WHERE ip = ? ORDER BY id DESC LIMIT 1", (ip,)
        ).fetchone()
        # без сравнения хешей за год накопится 365 одинаковых копий
        if last and last["sha256"] == digest:
            return None

        at = _now()
        cursor = conn.execute(
            """
            INSERT INTO configs (ip, at, sha256, lines, source, text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            # SQLite длинный текст не сжимает, поэтому жмём сами
            (ip, at, digest, text.count("\n") + 1, source, zlib.compress(text.encode("utf-8"), 6)),
        )
    return {
        "id": cursor.lastrowid,
        "ip": ip,
        "at": at,
        "sha256": digest,
        "lines": text.count("\n") + 1,
        "source": source,
    }


def configs(ip: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, ip, at, sha256, lines, source
              FROM configs
             WHERE ip = ?
             ORDER BY id DESC
            """,
            (ip,),
        ).fetchall()
    return [dict(row) for row in rows]


def config(version_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM configs WHERE id = ?", (version_id,)).fetchone()
    return _unpack(row)


def last_config(ip: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM configs WHERE ip = ? ORDER BY id DESC LIMIT 1", (ip,)
        ).fetchone()
    return _unpack(row)


def _unpack(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    version = dict(row)
    version["text"] = zlib.decompress(version["text"]).decode("utf-8")
    return version


def set_credentials(ip: str, username: str, password: str) -> None:
    with _credentials_lock:
        _credentials[ip] = (username, password)


def credentials(ip: str) -> tuple[str, str] | None:
    with _credentials_lock:
        return _credentials.get(ip)


def forget_credentials(ip: str) -> None:
    with _credentials_lock:
        _credentials.pop(ip, None)

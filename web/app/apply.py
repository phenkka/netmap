import asyncio
import difflib

from . import drivers, inventory, journal, ssh, store


def busy(ip: str, driver, username: str, password: str) -> str:
    if not driver.pending_diff_commands:
        return ""
    pending = driver.clean_pending_diff(
        ssh.run_lines(
            ip, username, password, driver.pending_diff_commands, driver.shell_login
        )
    )
    return pending


def _prepare(ip: str) -> tuple:
    driver = inventory.driver_for(ip)
    username, password = inventory.require_credentials(ip)
    return driver, username, password


def _discard(ip: str, driver, username: str, password: str) -> None:
    if not driver.discard_commands:
        return
    try:
        ssh.run_lines(
            ip, username, password, driver.discard_commands, driver.shell_login
        )
    except (ssh.SshError, OSError):
        pass


def send(ip: str, commands: list[str], source: str) -> dict:
    result = {"ip": ip, "ok": False, "detail": "", "version": None}
    try:
        driver, username, password = _prepare(ip)
    except Exception as exc:
        result["detail"] = getattr(exc, "detail", str(exc))
        return result

    try:
        pending = busy(ip, driver, username, password)
        if pending:
            result["detail"] = "на устройстве есть несохранённая правка"
            return result

        output = ssh.run_lines(
            ip, username, password, driver.session(commands), driver.shell_login
        )
        clean, complaint = driver.applied_cleanly(output)
        if not clean:
            _discard(ip, driver, username, password)
        result["ok"] = clean
        result["detail"] = complaint or "команды применены"

        version = inventory.collect_config(ip, source)
        result["version"] = version["id"] if version else None
    except (ssh.SshError, OSError) as exc:
        result["detail"] = str(exc) or "устройство не отвечает"

    return result


async def group(ips: list[str], commands: list[str], login: str | None) -> list[dict]:
    limit = asyncio.Semaphore(ssh.AT_ONCE)
    text = "; ".join(commands)[:400]

    async def one(ip: str) -> dict:
        async with limit:
            result = await asyncio.to_thread(send, ip, commands, "apply")
        journal.record(journal.APPLY, login, ip, f"{text} — {result['detail']}", result["ok"])
        return result

    return await asyncio.gather(*(one(ip) for ip in ips))


def rollback(ip: str, version_id: int, login: str | None) -> dict:
    target = store.config(version_id)
    if not target or target["ip"] != ip:
        return {"ip": ip, "ok": False, "detail": "версия не найдена", "left": ""}
    if not target["flat"]:
        return {
            "ip": ip,
            "ok": False,
            "detail": "эта версия снята до появления отката и в командном виде не хранится",
            "left": "",
        }

    driver, username, password = _prepare(ip)
    pending = busy(ip, driver, username, password)
    if pending:
        journal.record(journal.ROLLBACK, login, ip, "на устройстве несохранённая правка", False)
        return {
            "ip": ip,
            "ok": False,
            "detail": "на устройстве есть несохранённая правка",
            "left": "",
        }

    now = store.last_config(ip)
    output = ssh.run_lines(
        ip,
        username,
        password,
        driver.restore_commands(target["flat"], (now or {}).get("flat") or ""),
        driver.shell_login,
    )
    clean, complaint = driver.applied_cleanly(output)
    if not clean:
        _discard(ip, driver, username, password)

    inventory.collect_config(ip, "rollback")
    now = store.last_config(ip)
    left = _left(target["text"], now["text"] if now else "")

    ok = clean and not left
    detail = complaint or ("конфигурация возвращена" if ok else "часть настроек не совпала")
    journal.record(journal.ROLLBACK, login, ip, f"версия {version_id} — {detail}", ok)
    return {"ip": ip, "ok": ok, "detail": detail, "left": left}


def _left(wanted: str, got: str) -> str:
    if wanted.strip() == got.strip():
        return ""
    return "\n".join(
        difflib.unified_diff(
            wanted.splitlines(),
            got.splitlines(),
            "версия, к которой откатывались",
            "конфигурация после отката",
            lineterm="",
        )
    )

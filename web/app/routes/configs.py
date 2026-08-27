import asyncio
import difflib

from fastapi import APIRouter, HTTPException, Request

from .. import apply, inventory, journal, ssh, store

router = APIRouter(prefix="/api/devices")


@router.post("/{ip}/config")
def take_config(ip: str) -> dict:
    version = inventory.collect_config(ip, "manual")
    last = store.last_config(ip)
    if last:
        last.pop("text")
        last.pop("flat", None)
    return {"changed": bool(version), "version": last}


@router.post("/{ip}/versions/{version_id}/rollback")
async def rollback(ip: str, version_id: int, request: Request) -> dict:
    who = journal.who(request)
    try:
        return await asyncio.to_thread(apply.rollback, ip, version_id, who)
    except ssh.SshError as exc:
        journal.record(journal.ROLLBACK, who, ip, str(exc), False)
        raise HTTPException(400, str(exc))


@router.get("/{ip}/versions")
def versions(ip: str) -> dict:
    return {"versions": store.configs(ip)}


@router.get("/{ip}/versions/{version_id}")
def version(ip: str, version_id: int) -> dict:
    found = store.config(version_id)
    if not found or found["ip"] != ip:
        raise HTTPException(404, "версия не найдена")
    # командный вид нужен откату, а не читателю, и весит столько же
    found["restorable"] = bool(found.pop("flat", None))
    return found


@router.get("/{ip}/diff")
def diff(ip: str, a: int | None = None, b: int | None = None) -> dict:
    history = store.configs(ip)
    if a is None or b is None:
        if len(history) < 2:
            return {"a": None, "b": None, "diff": ""}
        a, b = history[1]["id"], history[0]["id"]

    old, new = store.config(a), store.config(b)
    if not old or not new:
        raise HTTPException(404, "версия не найдена")

    lines = difflib.unified_diff(
        old["text"].splitlines(),
        new["text"].splitlines(),
        f"версия {old['id']}, {old['at']}",
        f"версия {new['id']}, {new['at']}",
        lineterm="",
    )
    return {"a": a, "b": b, "diff": "\n".join(lines)}


@router.get("/{ip}/pending")
def pending(ip: str) -> dict:
    driver = inventory.driver_for(ip)
    if not driver.pending_diff_commands:
        return {"supported": False, "diff": ""}

    username, password = inventory.require_credentials(ip)
    output = ssh.run_lines(
        ip, username, password, driver.pending_diff_commands, driver.shell_login
    )
    return {"supported": True, "diff": driver.clean_pending_diff(output)}
